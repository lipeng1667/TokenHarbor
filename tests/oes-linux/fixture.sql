-- Synthetic OES functional-test data only.
-- Apply to the dedicated, isolated test MariaDB instance as an administrator.
-- This deliberately fails if the database already exists: do not silently reset
-- previous runs or apply this fixture to a production database server.
-- Provision the restricted oes_test database login separately at runtime.

CREATE DATABASE oes_functional CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE oes_functional;

-- Every field consumed through CONCAT_WS must be NOT NULL, otherwise the legacy
-- parser shifts fields when MySQL skips a NULL argument. Text must not contain
-- commas, because the loader parses the concatenated value as comma-separated.
CREATE TABLE oes_company (
    id INT NOT NULL PRIMARY KEY,
    pass VARCHAR(63) NOT NULL,
    pseudo_key VARCHAR(63) NOT NULL,
    priority INT NOT NULL,
    balance BIGINT NOT NULL,
    credit BIGINT NOT NULL,
    concurrent INT NOT NULL,
    notify_concurrent INT NOT NULL,
    notify_ip VARCHAR(15) NOT NULL,
    notify_port INT NOT NULL,
    notify_url VARCHAR(127) NOT NULL,
    status INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE oes_auth_ip (
    company_id INT NOT NULL,
    start_addr VARCHAR(15) NOT NULL,
    ranges BIGINT UNSIGNED NOT NULL,
    concurrent INT NOT NULL,
    PRIMARY KEY (company_id, start_addr)
) ENGINE=InnoDB;

CREATE TABLE oes_price (
    company_id INT NOT NULL,
    service_id INT NOT NULL,
    function_id INT NOT NULL,
    bill_rate INT NOT NULL,
    bill INT NOT NULL,
    comm_rate INT NOT NULL,
    comm INT NOT NULL,
    mask CHAR(26) NOT NULL,
    PRIMARY KEY (company_id, service_id, function_id)
) ENGINE=InnoDB;

CREATE TABLE oes_stat_dispatcher (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    time BIGINT UNSIGNED NOT NULL,
    dispatcher_id INT NOT NULL,
    order_count BIGINT NOT NULL,
    order_fail BIGINT NOT NULL,
    report_count BIGINT NOT NULL,
    report_fail BIGINT NOT NULL,
    report_waiting BIGINT NOT NULL
) ENGINE=InnoDB;

-- Business credentials below are intentionally public synthetic test values.
-- They are not the database-login password and must never be used in production.
-- Monetary amounts are thousandths of one currency unit (the source calls them li).
INSERT INTO oes_company
    (id, pass, pseudo_key, priority, balance, credit, concurrent,
     notify_concurrent, notify_ip, notify_port, notify_url, status)
VALUES
    (0, 'oes-functional-test-only', 'oes-test-pseudo-only', 1, 1000000, 0,
     8, 2, '127.0.0.1', 19012, '/callback', 0);

INSERT INTO oes_auth_ip (company_id, start_addr, ranges, concurrent)
VALUES (0, '127.0.0.1', 1, 8);

-- -2 means fixed charge/commission. Each successful order costs 20 li;
-- commission is zero. All 26 possible response fields are visible as plain text.
INSERT INTO oes_price
    (company_id, service_id, function_id, bill_rate, bill, comm_rate, comm, mask)
VALUES
    (0, 0, 0, -2, 20, -2, 0, '11111111111111111111111111'),
    (0, 0, 1, -2, 20, -2, 0, '11111111111111111111111111');
