#!/usr/bin/env python3
"""Run two OES orders inside an already isolated, resource-limited service."""
import argparse
import json
import os
import pwd
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path)
    parser.add_argument("state", type=Path)
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit("Run through the non-root isolated service, never as root")
    os.umask(0o077)
    runtime_user = pwd.getpwuid(os.geteuid()).pw_name
    stage, state = args.stage, args.state
    harness, sysroot = stage / "harness", stage / "sysroot"
    run_dir = state / "runs" / (time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3))
    run_dir.mkdir(parents=True)
    print(f"RUN_DIR={run_dir}", flush=True)
    env = dict(os.environ, LD_LIBRARY_PATH=str(sysroot / "usr/lib/x86_64-linux-gnu"))
    db_dir, db_socket = run_dir / "database", run_dir / "database.sock"
    mysql = [str(sysroot / "usr/bin/mariadb"), "--no-defaults", "--protocol=socket",
             f"--socket={db_socket}", f"--user={runtime_user}", "--batch", "--skip-column-names"]
    processes, streams = {}, []
    evidence = {"status": "FAIL", "started_unix": int(time.time()),
                "run_dir": str(run_dir), "uid": os.geteuid(),
                "network_namespace": os.readlink("/proc/self/ns/net"),
                "ipc_namespace": os.readlink("/proc/self/ns/ipc"), "shutdown": {}}

    def log(message):
        print(message, flush=True)

    def execute(command, *, cwd=None, stdin=None, timeout=20, check=True):
        return subprocess.run(command, cwd=cwd, input=stdin, env=env, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout, check=check)

    def sql(statement):
        result = execute(mysql, stdin=statement, timeout=10)
        return result.stdout.strip()

    def start(name, command, cwd):
        stream = (run_dir / f"{name}.stdout.log").open("w")
        streams.append(stream)
        processes[name] = subprocess.Popen(command, cwd=cwd, env=env,
                                           stdin=subprocess.DEVNULL, stdout=stream,
                                           stderr=subprocess.STDOUT)
        return processes[name]

    def assert_alive():
        for name, proc in processes.items():
            if proc.poll() is not None:
                raise RuntimeError(f"{name} exited early with code {proc.returncode}")

    def wait_port(port, timeout=20):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            assert_alive()
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.25)
        raise TimeoutError(f"Port {port} did not become ready")

    def stop(name):
        proc = processes.get(name)
        if proc is None:
            return
        forced = False
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=25)
            except subprocess.TimeoutExpired:
                forced = True
                proc.kill()
                proc.wait(timeout=5)
        evidence["shutdown"][name] = {"returncode": proc.returncode, "forced": forced}
        del processes[name]

    try:
        # A read-only executable directory is separate from the noexec state dir.
        for name in ("httpportal", "okernel", "dispatcher"):
            result = execute(["ldd", str(stage / "bin" / name)])
            if "not found" in result.stdout:
                raise RuntimeError(f"Unresolved dynamic dependency: {name}")
            (run_dir / f"{name}.ldd.txt").write_text(result.stdout)
        evidence["dynamic_dependencies"] = "PASS"
        log("Dynamic dependencies: PASS (three executables)")

        init = [str(sysroot / "usr/bin/mariadb-install-db"), "--no-defaults",
                f"--basedir={sysroot / 'usr'}", f"--datadir={db_dir}",
                "--auth-root-authentication-method=socket",
                f"--auth-root-socket-user={runtime_user}",
                "--skip-test-db", "--skip-name-resolve",
                "--innodb-buffer-pool-size=64M", "--innodb-log-file-size=16M"]
        result = execute(init, timeout=60, check=False)
        (run_dir / "database-init.log").write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(f"Database initialization failed ({result.returncode})")
        start("database", [str(sysroot / "usr/sbin/mariadbd"), "--no-defaults",
              f"--basedir={sysroot / 'usr'}", f"--datadir={db_dir}",
              f"--socket={db_socket}", f"--pid-file={run_dir / 'database.pid'}",
              f"--log-error={run_dir / 'database-error.log'}",
              f"--plugin-dir={sysroot / 'usr/lib/mysql/plugin'}",
              "--bind-address=127.0.0.1", "--port=19306", "--skip-name-resolve",
              "--innodb-buffer-pool-size=64M", "--innodb-log-file-size=16M",
              "--max-connections=12", "--table-open-cache=64", "--thread-cache-size=2",
              "--performance-schema=OFF", "--skip-log-bin"], run_dir)
        wait_port(19306)
        evidence["database_version"] = sql("SELECT VERSION();")
        sql((harness / "fixture.sql").read_text())
        db_password = secrets.token_hex(24)
        sql("CREATE USER 'oes_test'@'127.0.0.1' IDENTIFIED BY '" + db_password + "';\n"
            "GRANT SELECT ON oes_functional.* TO 'oes_test'@'127.0.0.1';\n"
            "GRANT UPDATE ON oes_functional.oes_company TO 'oes_test'@'127.0.0.1';\n"
            "GRANT INSERT ON oes_functional.oes_stat_dispatcher TO 'oes_test'@'127.0.0.1';\n")
        # Enable query evidence after account provisioning to keep secrets out.
        sql(f"SET GLOBAL general_log_file='{run_dir / 'database-queries.log'}'; SET GLOBAL general_log=ON;")
        for name in ("okernel", "httpportal"):
            node = run_dir / name
            node.mkdir()
            template = (harness / "configs" / f"{name}.conf").read_text()
            if template.count("__OES_TEST_DB_PASSWORD__") != 1:
                raise RuntimeError(f"Invalid credential placeholder in {name} config")
            rendered_config = template.replace("__OES_TEST_DB_PASSWORD__", db_password)
            rendered_config = rendered_config.replace("__OES_TEST_NODE_DIR__", str(node))
            (node / f"{name}.conf").write_text(rendered_config)
        del db_password
        # module/config.c resolves files next to /proc/self/exe, not cwd.
        # Root-owned links in stage/bin point into this private state tree.
        current = state / "current"
        if current.is_symlink():
            current.unlink()
        elif current.exists():
            raise RuntimeError("The reserved current path is not a symlink")
        current.symlink_to(run_dir, target_is_directory=True)
        for name in ("okernel", "httpportal"):
            if (stage / "bin" / f"{name}.conf").resolve() != (run_dir / name / f"{name}.conf").resolve():
                raise RuntimeError(f"Executable-relative configuration link is incorrect: {name}")
        log("Isolated database initialized; synthetic fixture loaded")

        start("okernel", [str(stage / "bin/okernel"), "-c"], run_dir / "okernel")
        wait_port(19009)
        start("dispatcher", [str(stage / "bin/dispatcher"), "-i", "0", "-s", "0",
                             "-e", "0", "-debug", "127.0.0.1", "19009"], run_dir)
        start("httpportal", [str(stage / "bin/httpportal"), "-c"], run_dir / "httpportal")
        wait_port(19011)
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            assert_alive()
            info = execute([str(stage / "bin/okernel"), "-info"], cwd=run_dir / "okernel", check=False)
            (run_dir / "kernel-topology.txt").write_text(info.stdout)
            if "Total 1 portals online" in info.stdout and "Total 1 dispatchers online" in info.stdout:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Kernel did not report one Portal and one Dispatcher")
        evidence["topology"] = {"portal": 1, "dispatcher": 1}
        for name in ("okernel", "httpportal"):
            text = (run_dir / f"{name}.stdout.log").read_text(errors="replace")
            if not re.search(r"Load user data from database[^\n]*total 1 users", text):
                raise RuntimeError(f"{name} did not load the fixture user from the database")
        connections = sql("SELECT USER,DB,COMMAND FROM information_schema.PROCESSLIST WHERE USER='oes_test';")
        if not connections:
            raise RuntimeError("No live application database pool connection")
        (run_dir / "database-connections.tsv").write_text(connections + "\n")
        evidence["database_user_loads"] = ["okernel", "httpportal"]
        log("Topology and database connections: PASS")

        probe = execute(["python3", str(harness / "functional_probe.py"), "--output",
                         str(run_dir / "functional-results.json")], timeout=90, check=False)
        (run_dir / "probe.stdout.log").write_text(probe.stdout)
        print(probe.stdout, flush=True)
        if probe.returncode:
            raise RuntimeError("HTTP/protocol functional probe failed; see functional-results.json")
        functional = json.loads((run_dir / "functional-results.json").read_text())
        evidence["functional_checks"] = functional["checks"]
        expected = functional["expected_balance_milliunits"]
        deadline = time.monotonic() + 75
        log("Waiting for the normal database statistics flush (no extra orders)")
        while time.monotonic() < deadline:
            assert_alive()
            balance = int(sql("SELECT balance FROM oes_functional.oes_company WHERE id=0;"))
            stats = sql("SELECT COUNT(*),COALESCE(SUM(order_count),0),COALESCE(SUM(order_fail),0) FROM oes_functional.oes_stat_dispatcher WHERE dispatcher_id=0;")
            rows, orders, failures = map(int, stats.split("\t"))
            if balance == expected and rows > 0 and orders == 2 and failures == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError(f"Database writes incomplete: balance={balance}, statistics={stats}")
        evidence["database_balance"] = balance
        evidence["database_statistics"] = {"rows": rows, "orders": orders, "failed_orders": failures}
        (run_dir / "database-statistics.tsv").write_text(sql("SELECT time,dispatcher_id,order_count,order_fail,report_count,report_fail,report_waiting FROM oes_functional.oes_stat_dispatcher;") + "\n")
        evidence["process_memory"] = {}
        for name, proc in processes.items():
            status = Path(f"/proc/{proc.pid}/status").read_text()
            evidence["process_memory"][name] = [line for line in status.splitlines() if line.startswith(("VmRSS:", "VmHWM:"))]
        for name in ("httpportal", "dispatcher", "okernel"):
            stop(name)
        final_balance = int(sql("SELECT balance FROM oes_functional.oes_company WHERE id=0;"))
        if final_balance != expected:
            raise RuntimeError(f"Unexpected balance after graceful shutdown: {final_balance}")
        dispatcher_log = (run_dir / "dispatcher.stdout.log").read_text(errors="replace")
        for order_id in functional["distinct_completed_orders"]:
            if order_id not in dispatcher_log:
                raise RuntimeError(f"Dispatcher log is missing completed order {order_id}")
        evidence["dispatcher_log_order_ids"] = functional["distinct_completed_orders"]
        evidence["written_files"] = {}
        for node, pattern in (("httpportal", "portal_log_*.txt"),
                              ("okernel", "kernel_log_*.txt"),
                              ("okernel", "kernel_cdr_*.dat"),
                              ("okernel", "order_of_user_0.dat")):
            files = [path for path in (run_dir / node).glob(pattern)
                     if path.is_file() and path.stat().st_size > 0]
            if not files:
                raise RuntimeError(f"Missing persisted test output: {node}/{pattern}")
            for path in files:
                evidence["written_files"][str(path.relative_to(run_dir))] = path.stat().st_size
        for path in (run_dir / "okernel").glob("dbupdate_err_*.sql"):
            if path.stat().st_size:
                raise RuntimeError("Kernel recorded failed database updates")
        stop("database")
        if any(item["forced"] or item["returncode"] != 0 for item in evidence["shutdown"].values()):
            raise RuntimeError("A process failed to shut down normally")
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["error"] = f"{type(error).__name__}: {error}"
        log(evidence["error"])
    finally:
        for name in ("httpportal", "dispatcher", "okernel", "database"):
            try:
                stop(name)
            except Exception as error:
                evidence["status"] = "FAIL"
                evidence.setdefault("cleanup_errors", []).append(f"{name}: {error}")
        for stream in streams:
            stream.close()
        evidence["finished_unix"] = int(time.time())
        rendered = json.dumps(evidence, indent=2, ensure_ascii=False) + "\n"
        (run_dir / "deployment-results.json").write_text(rendered)
        print(rendered, flush=True)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
