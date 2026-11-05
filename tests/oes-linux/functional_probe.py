#!/usr/bin/env python3
"""Low-volume functional checks for an isolated OES fixture, never a load test."""

import argparse
import hashlib
import http.client
import json
import queue
import threading
import time
import uuid
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(args, evidence):
    notifications = queue.Queue()

    class Callback(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if self.path != "/callback" or not 0 < length <= 16384:
                self.send_error(400)
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
            except (UnicodeError, ValueError):
                self.send_error(400)
                return
            notifications.put(payload)
            body = b'{"result":"0"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def log_message(self, *_):
            pass

    def request(path, extra=None, bad_signature=False, timeout=None):
        tick = int(time.time())
        material = f"{args.user:06d}{tick}{args.password}".encode()
        key = hashlib.md5(material).hexdigest()[:16]
        if bad_signature:
            key = ("0" if key[0] != "0" else "1") + key[1:]
        params = {"user": args.user, "tick": tick, "key": key}
        params.update(extra or {})
        connection = http.client.HTTPConnection(
            args.host, args.port, timeout=timeout or args.timeout
        )
        try:
            connection.request("GET", path + "?" + urlencode(params),
                               headers={"Connection": "close"})
            response = connection.getresponse()
            body = response.read(16385)
            require(response.status == 200, f"{path}: HTTP {response.status}")
            require(len(body) <= 16384, f"{path}: oversized response")
            payload = json.loads(body)
            require(isinstance(payload, dict), f"{path}: expected JSON object")
            return payload
        finally:
            connection.close()

    def result(payload, expected, label):
        require(str(payload.get("result")) == str(expected),
                f"{label}: expected result={expected}, got {payload!r}")

    def successful_order(payload, custom_id, label):
        result(payload, 0, label)
        require(payload.get("custom_order_id") == custom_id,
                f"{label}: custom order ID mismatch")
        require(int(payload.get("order_id", "0")) > 0,
                f"{label}: missing Kernel order ID")
        code = str(payload.get("resp_code"))
        # These fixture strings are produced only by the mock Dispatcher.
        # "error test" is its fixed sample description, even with result=0.
        if code == "1":
            require(payload.get("resp_desc") == "Order response error test",
                    f"{label}: missing Dispatcher response description")
            require(payload.get("t") == "Test tag in order response",
                    f"{label}: missing Dispatcher response TLV")
        elif code == "2":
            require(payload.get("resp_desc") == "Order report error test",
                    f"{label}: missing Dispatcher report description")
            require(payload.get("r") == "Test tag in report",
                    f"{label}: missing Dispatcher report TLV")
        else:
            raise AssertionError(f"{label}: missing Dispatcher evidence: {payload!r}")

    server = ThreadingHTTPServer(("127.0.0.1", args.callback_port), Callback)
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + args.wait_ready
        last_error = None
        while time.monotonic() < deadline:
            try:
                before = request("/account", timeout=2)
                result(before, 0, "initial account query")
                break
            except (OSError, ValueError, http.client.HTTPException, AssertionError) as error:
                last_error = str(error)
                time.sleep(1)
        else:
            raise AssertionError(f"Portal/Kernel readiness failed: {last_error}")
        evidence["account_before"] = before

        denied = request("/account", bad_signature=True)
        evidence["invalid_signature"] = denied
        result(denied, 11, "invalid signature rejection")

        prefix = "th" + uuid.uuid4().hex[:16]
        sync_id = prefix + "s"
        sync_params = {"custom_order_id": sync_id, "service": 0,
                       "function": 0, "money": "1.000"}
        sync_response = request("/api", sync_params)
        evidence["synchronous_order"] = sync_response
        successful_order(sync_response, sync_id, "synchronous order")

        query_response = request("/query", {"custom_order_id": sync_id})
        evidence["order_query"] = query_response
        successful_order(query_response, sync_id, "order query")
        require(query_response["order_id"] == sync_response["order_id"],
                "query returned a different Kernel order ID")

        duplicate = request("/api", sync_params)
        evidence["duplicate_order"] = duplicate
        result(duplicate, -3, "duplicate order rejection")
        require(duplicate.get("order_id") == sync_response["order_id"],
                "duplicate order returned a different Kernel order ID")

        async_id = prefix + "a"
        accepted = request("/api", {"custom_order_id": async_id, "service": 0,
                                   "function": 1, "money": "1.000", "notify": 1})
        evidence["asynchronous_acceptance"] = accepted
        result(accepted, -1, "asynchronous acceptance")
        callback_deadline = time.monotonic() + args.timeout
        while time.monotonic() < callback_deadline:
            try:
                callback = notifications.get(timeout=max(0.01, callback_deadline - time.monotonic()))
            except queue.Empty:
                break
            if callback.get("custom_order_id") == async_id:
                evidence["asynchronous_callback"] = callback
                successful_order(callback, async_id, "asynchronous callback")
                require(callback["order_id"] == accepted["order_id"],
                        "callback returned a different Kernel order ID")
                break
        else:
            callback = None
        require("asynchronous_callback" in evidence, "matching callback was not received")

        after = request("/account")
        evidence["account_after"] = after
        result(after, 0, "final account query")
        debit = Decimal(before["balance"]) - Decimal(after["balance"])
        require(debit == Decimal("0.040"),
                f"expected two 0.020 debits and no duplicate debit, observed {debit}")
        evidence["balance_debit"] = str(debit)
        evidence["successful_orders_submitted"] = 2
        evidence["distinct_completed_orders"] = [sync_id, async_id]
        evidence["expected_balance_milliunits"] = int(Decimal(after["balance"]) * 1000)
        evidence["checks"] = ["portal_kernel_account", "invalid_signature_rejected",
                              "portal_kernel_dispatcher_sync", "order_query",
                              "duplicate_rejected", "async_callback",
                              "exact_balance_debit"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    parser.add_argument("--port", type=int, default=19011)
    parser.add_argument("--callback-port", type=int, default=19012)
    parser.add_argument("--user", type=int, default=0)
    parser.add_argument("--password", default="oes-functional-test-only",
                        help="isolated fixture password only; never a production credential")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--wait-ready", type=float, default=20)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = {"started_unix": int(time.time()), "status": "FAIL"}
    try:
        run(args, evidence)
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["error"] = f"{type(error).__name__}: {error}"
    evidence["finished_unix"] = int(time.time())
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
