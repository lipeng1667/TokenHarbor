# OES functional-test database

`fixture.sql` contains synthetic data for a dedicated MariaDB test instance. It
must not be applied to an existing production server. It creates `oes_functional`
without `IF NOT EXISTS`, so applying it again fails instead of resetting prior
results. There are no production credentials or records in this fixture.

Provision the database login separately when preparing the isolated instance.
Use a generated password for `oes_test` at `127.0.0.1`; grant only `SELECT` on
`oes_functional.*`, `UPDATE` on `oes_functional.oes_company`, and `INSERT` on
`oes_functional.oes_stat_dispatcher`. Keep the runtime database password out of
Git, process arguments and captured command output. Do not use the business
password below as the database password.

Both Portal and Kernel need the following `[database]` values, with the actual
test port and generated password supplied at runtime:

```ini
if_enable_db = 1
db_host = 127.0.0.1
db_port = TEST_DATABASE_PORT
db_name = oes_functional
db_user = oes_test
db_pass = GENERATED_TEST_DATABASE_PASSWORD
table_company = oes_company
```

Place `okernel.conf` and `httpportal.conf` beside their actual executable files,
or create symlinks there to the active run's private configuration files. The
legacy configuration loader resolves these relative filenames from the
executable directory, not the process working directory. Merely changing the
working directory to a node's state directory does not select its configuration.
For the test deployment, the binary-directory symlinks may point through
`state/current` to the corresponding node configuration; update `state/current`
before starting either node, and verify both targets are readable by the test
service identity. Missing configuration can leave the database host empty and
cause startup failure. Keep the generated configurations outside Git.

Portal also uses `table_ipauth = oes_auth_ip`. Kernel uses
`table_price = oes_price`, `table_stat = oes_stat_dispatcher`,
`db_pool_size = 1`, `db_update_interval = 1`, and `db_update_delay = 0`.
Use TCP address `127.0.0.1`, not `localhost`, so the selected nonstandard port is
used instead of a default local Unix socket. Test ports belong to the isolated
network namespace; they must not expose the database on the public host network.

The business test contract is:

| Item | Value |
| --- | --- |
| Business user | `0` |
| Synthetic business password | `oes-functional-test-only` |
| Synthetic pseudonymization key | `oes-test-pseudo-only` |
| Initial balance | `1000000` li |
| Credit | `0` |
| Allowed source | `127.0.0.1`, one address |
| Service and functions | Service `0`, functions `0` and `1` |
| Fixed successful-order charge | `20` li |
| Commission | `0` |
| Callback | `http://127.0.0.1:19012/callback` |

OES parses SQL results through comma-separated `CONCAT_WS` strings. All consumed
fields are non-null and synthetic text contains no commas. All 26 response-mask
characters are `1`, allowing the mock Dispatcher's response fields to reach the
functional probe. Dispatcher routing is registered through its login to Kernel;
there is no dispatcher routing table in the SQL used by these modules.

## Evidence to capture

1. Portal and Kernel must each log `Load user data from database` followed by
   `total 1 users`. Portal must load IP authentication, and Kernel must load price
   data. Their `get_db_config` function only reports success after connecting,
   running its SELECT and fetching results.
2. Query the isolated database's process list as its test administrator and check
   for an `oes_test` connection to `oes_functional`. Kernel's startup message
   `Createing database pool ... 1 connections` only reports requested pool size;
   it does not prove a successful connection.
3. Record the initial balance, run the HTTP end-to-end probe with Dispatcher
   failure rate zero, then poll for the expected balance after completed orders.
   For N distinct completed successful orders, expect `1000000 - 20 * N` li.
   Repeated status queries do not create additional orders. A later failed report
   can refund a previously charged order, so assert final status too.
4. Kernel writes dispatcher counters when its minute marker changes. Allow up to
   70 seconds for at least one statistics row; capture `order_count`,
   `order_fail`, `report_count`, `report_fail` and `report_waiting`. Avoid treating
   the sum of `report_waiting` over rows as a current queue count.
5. Inspect the test error SQL log for failed writes. SQL failure text is not
   necessarily emitted to the console: `dblog_callback` stores failed SQL in the
   configured error log.

Useful read-only verification queries, executed only against the test instance:

```sql
SELECT VERSION(), DATABASE();
SELECT id, balance, credit, status FROM oes_functional.oes_company;
SELECT USER, HOST, DB, COMMAND
FROM information_schema.PROCESSLIST
WHERE USER = 'oes_test' AND DB = 'oes_functional';
SELECT dispatcher_id, SUM(order_count) AS orders,
       SUM(order_fail) AS order_failures,
       SUM(report_count) AS reports,
       SUM(report_fail) AS report_failures
FROM oes_functional.oes_stat_dispatcher GROUP BY dispatcher_id;
```

## Source basis and limits

- `oes_source/publicroute.c:36` implements synchronous MySQL configuration reads.
- `oes_source/httpportal/dataload.c:32` defines the company and IP-auth SELECTs.
- `oes_source/okernel/dataload.c:14` defines company/price reads and balance/stat
  writes; `:371` flushes balances; `:396` flushes dispatcher counters.
- `oes_source/okernel/dataload.c:831` creates the asynchronous connection pool.
- `oes_source/okernel/tcplink.c:805` schedules database updates.
- `oes_source/okernel/orderproc.c:57` applies fixed prices and balance checks.
- `module/dblog.c:35` implements worker connections and queued SQL execution.
- `module/config.c:251` resolves relative configuration paths using the
  executable directory unless `CONFIG_FLAG_CURRENT_PATH` is explicitly supplied.

The inspected C API usage consists of conventional `mysql_init`,
`mysql_real_connect`, query/result, and thread-initialization calls. No accessed
internal `MYSQL` structure fields or `my_bool` dependency was found in these
paths. MariaDB client/server compatibility must still be established by the
actual build and functional run. This fixture is a minimal test schema inferred
from the source SQL, not a recovered or migration-ready production schema.
