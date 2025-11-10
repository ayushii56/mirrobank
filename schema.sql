-- run this on mysql workbench 
USE mirrorbank;

-- Recommended session settings
SET NAMES utf8mb4;
SET time_zone = '+00:00';

-- -------- Clean drop order (dev convenience) --------
SET FOREIGN_KEY_CHECKS = 0;
DROP TRIGGER IF EXISTS trg_tx_after_insert;
DROP TRIGGER IF EXISTS trg_tx_after_update;
DROP TRIGGER IF EXISTS trg_tx_after_delete;

DROP PROCEDURE IF EXISTS mb_check_budget_alerts;
DROP FUNCTION IF EXISTS mb_period_start;

DROP TABLE IF EXISTS budget_alerts;
DROP TABLE IF EXISTS budgets;
DROP TABLE IF EXISTS recommendations;
DROP TABLE IF EXISTS assumptions;
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS goals;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

-- ================== CORE TABLES ======================

-- USERS
CREATE TABLE users (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  name          VARCHAR(120) NOT NULL,
  email         VARCHAR(190) UNIQUE,
  role          ENUM('user','admin') DEFAULT 'user',
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ACCOUNTS
CREATE TABLE accounts (
  id                     BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id                BIGINT NOT NULL,
  name                   VARCHAR(120) NOT NULL,
  type                   ENUM('checking','savings','credit','wallet') NOT NULL,
  balance                DECIMAL(14,2) NOT NULL DEFAULT 0.00,
  low_balance_threshold  DECIMAL(14,2) DEFAULT 1000.00,
  created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_accounts_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_accounts_user ON accounts(user_id);

-- GOALS
CREATE TABLE goals (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id       BIGINT NOT NULL,
  name          VARCHAR(150) NOT NULL,
  target_amount DECIMAL(14,2) NOT NULL,
  target_date   DATE NOT NULL,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_goals_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_goals_user ON goals(user_id);

-- TRANSACTIONS
CREATE TABLE transactions (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id     BIGINT NOT NULL,
  account_id  BIGINT NOT NULL,
  amount      DECIMAL(14,2) NOT NULL,
  tx_type     ENUM('debit','credit') NOT NULL,
  category    VARCHAR(100) NOT NULL,
  merchant    VARCHAR(150),
  notes       VARCHAR(500),
  goal_id     BIGINT NULL,
  ts          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at  TIMESTAMP NULL DEFAULT NULL,
  CONSTRAINT fk_tx_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_tx_account
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
  CONSTRAINT fk_tx_goal
    FOREIGN KEY (goal_id) REFERENCES goals(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_tx_user    ON transactions(user_id);
CREATE INDEX idx_tx_account ON transactions(account_id);
CREATE INDEX idx_tx_ts      ON transactions(ts);
CREATE INDEX idx_tx_category ON transactions(category);

-- BUDGETS
CREATE TABLE budgets (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id       BIGINT NOT NULL,
  category      VARCHAR(100) NOT NULL,
  period        ENUM('weekly','monthly') NOT NULL,
  limit_amount  DECIMAL(14,2) NOT NULL,
  start_date    DATE NOT NULL,
  CONSTRAINT fk_budgets_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE KEY uq_budget (user_id, category, period, start_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- BUDGET ALERTS
CREATE TABLE budget_alerts (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id     BIGINT NOT NULL,
  budget_id   BIGINT NOT NULL,
  level       ENUM('warning','limit_exceeded') NOT NULL,
  message     VARCHAR(300) NOT NULL,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_alerts_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_alerts_budget
    FOREIGN KEY (budget_id) REFERENCES budgets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_alerts_user ON budget_alerts(user_id);

-- RECOMMENDATIONS
CREATE TABLE recommendations (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id     BIGINT NOT NULL,
  type        ENUM('low_balance','overspending','unusual_activity') NOT NULL,
  message     VARCHAR(400) NOT NULL,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_recos_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_recos_user ON recommendations(user_id);

-- ASSUMPTIONS (for forecasting)
CREATE TABLE assumptions (
  id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id             BIGINT NOT NULL,
  income_growth_pct   DECIMAL(6,2) DEFAULT 0.00,
  spending_growth_pct DECIMAL(6,2) DEFAULT 0.00,
  meta_json           JSON NULL,
  updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_assumptions_user
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- AUDIT LOG
CREATE TABLE audit_log (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id     BIGINT NULL,
  action      VARCHAR(60) NOT NULL,
  entity      VARCHAR(60) NOT NULL,
  entity_id   BIGINT NULL,
  details     VARCHAR(600),
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_audit_user ON audit_log(user_id);

-- ================ FUNCTIONS & PROCEDURES =================

-- Helper: start-of-period calculator (VARCHAR param for safety)
DROP FUNCTION IF EXISTS mb_period_start;
DELIMITER $$
CREATE FUNCTION mb_period_start(p_date DATETIME, p_period VARCHAR(16))
RETURNS DATE
DETERMINISTIC
BEGIN
  IF p_period = 'weekly' THEN
    RETURN DATE(DATE_SUB(p_date, INTERVAL WEEKDAY(p_date) DAY));  -- Monday start
  ELSE
    RETURN DATE(DATE_FORMAT(p_date, '%Y-%m-01'));                 -- 1st of month
  END IF;
END$$
DELIMITER ;

-- Procedure: compute budget alerts (≥80% warning, >100% exceeded)
DROP PROCEDURE IF EXISTS mb_check_budget_alerts;
DELIMITER $$
CREATE PROCEDURE mb_check_budget_alerts(
  IN p_user_id BIGINT,
  IN p_category VARCHAR(100),
  IN p_ref_ts DATETIME
)
proc: BEGIN
  DECLARE v_period ENUM('weekly','monthly');
  DECLARE v_limit DECIMAL(14,2);
  DECLARE v_budget_id BIGINT;
  DECLARE v_start DATE;
  DECLARE v_end DATE;
  DECLARE v_spent DECIMAL(14,2);

  -- Find active budget whose start matches the period start
  SELECT id, period, limit_amount
    INTO v_budget_id, v_period, v_limit
  FROM budgets
  WHERE user_id = p_user_id
    AND category = p_category
    AND start_date = mb_period_start(p_ref_ts, period)
  ORDER BY FIELD(period,'monthly','weekly')  -- prefer monthly if both
  LIMIT 1;

  IF v_budget_id IS NULL THEN
    LEAVE proc;
  END IF;

  SET v_start = mb_period_start(p_ref_ts, v_period);
  SET v_end = CASE
                WHEN v_period = 'weekly' THEN DATE_ADD(v_start, INTERVAL 7 DAY)
                ELSE DATE_ADD(LAST_DAY(v_start), INTERVAL 1 DAY)
              END;

  SELECT COALESCE(SUM(amount),0.00)
    INTO v_spent
  FROM transactions
  WHERE user_id = p_user_id
    AND category = p_category
    AND tx_type = 'debit'
    AND ts >= v_start AND ts < v_end;

  IF v_spent >= (0.8 * v_limit) AND v_spent < v_limit THEN
    INSERT INTO budget_alerts(user_id, budget_id, level, message)
    VALUES (p_user_id, v_budget_id, 'warning',
            CONCAT('Budget warning: ', p_category, ' used ₹', FORMAT(v_spent,2),
                   ' of ₹', FORMAT(v_limit,2), ' (≥80%).'));
  END IF;

  IF v_spent > v_limit THEN
    INSERT INTO budget_alerts(user_id, budget_id, level, message)
    VALUES (p_user_id, v_budget_id, 'limit_exceeded',
            CONCAT('Budget exceeded: ', p_category, ' used ₹', FORMAT(v_spent,2),
                   ' of ₹', FORMAT(v_limit,2), '.'));
  END IF;

END proc$$
DELIMITER ;

-- ===================== TRIGGERS ========================

-- INSERT → apply balance impact, audit, alerts, low-balance reco
DROP TRIGGER IF EXISTS trg_tx_after_insert;
DELIMITER $$
CREATE TRIGGER trg_tx_after_insert
AFTER INSERT ON transactions
FOR EACH ROW
BEGIN
  IF NEW.tx_type = 'credit' THEN
    UPDATE accounts SET balance = balance + NEW.amount WHERE id = NEW.account_id;
  ELSE
    UPDATE accounts SET balance = balance - NEW.amount WHERE id = NEW.account_id;
  END IF;

  INSERT INTO audit_log(user_id, action, entity, entity_id, details)
  VALUES (NEW.user_id, 'create', 'transaction', NEW.id,
          CONCAT('Inserted ', NEW.tx_type, ' ₹', NEW.amount, ' on account ', NEW.account_id));

  CALL mb_check_budget_alerts(NEW.user_id, NEW.category, NEW.ts);

  -- Low balance reco (insert only if threshold crossed)
  INSERT INTO recommendations(user_id, type, message)
  SELECT a.user_id, 'low_balance',
         CONCAT('Low balance on ', a.name, ': ₹', FORMAT(a.balance,2),
                ' (threshold ₹', FORMAT(a.low_balance_threshold,2), ').')
  FROM accounts a
  WHERE a.id = NEW.account_id
    AND a.balance < a.low_balance_threshold;
END$$
DELIMITER ;

-- UPDATE → revert old impact, apply new, audit, alerts
DROP TRIGGER IF EXISTS trg_tx_after_update;
DELIMITER $$
CREATE TRIGGER trg_tx_after_update
AFTER UPDATE ON transactions
FOR EACH ROW
BEGIN
  -- Revert OLD
  IF OLD.tx_type = 'credit' THEN
    UPDATE accounts SET balance = balance - OLD.amount WHERE id = OLD.account_id;
  ELSE
    UPDATE accounts SET balance = balance + OLD.amount WHERE id = OLD.account_id;
  END IF;

  -- Apply NEW
  IF NEW.tx_type = 'credit' THEN
    UPDATE accounts SET balance = balance + NEW.amount WHERE id = NEW.account_id;
  ELSE
    UPDATE accounts SET balance = balance - NEW.amount WHERE id = NEW.account_id;
  END IF;

  INSERT INTO audit_log(user_id, action, entity, entity_id, details)
  VALUES (NEW.user_id, 'update', 'transaction', NEW.id,
          CONCAT('Updated tx. Old: ', OLD.tx_type, ' ₹', OLD.amount, ' acc ', OLD.account_id,
                 ' → New: ', NEW.tx_type, ' ₹', NEW.amount, ' acc ', NEW.account_id));

  CALL mb_check_budget_alerts(NEW.user_id, NEW.category, NEW.ts);
END$$
DELIMITER ;

-- DELETE → reverse impact, audit, alerts
DROP TRIGGER IF EXISTS trg_tx_after_delete;
DELIMITER $$
CREATE TRIGGER trg_tx_after_delete
AFTER DELETE ON transactions
FOR EACH ROW
BEGIN
  IF OLD.tx_type = 'credit' THEN
    UPDATE accounts SET balance = balance - OLD.amount WHERE id = OLD.account_id;
  ELSE
    UPDATE accounts SET balance = balance + OLD.amount WHERE id = OLD.account_id;
  END IF;

  INSERT INTO audit_log(user_id, action, entity, entity_id, details)
  VALUES (OLD.user_id, 'delete', 'transaction', OLD.id,
          CONCAT('Deleted ', OLD.tx_type, ' ₹', OLD.amount, ' on account ', OLD.account_id));

  CALL mb_check_budget_alerts(OLD.user_id, OLD.category, OLD.ts);
END$$
DELIMITER ;

-- ====================== SEED DATA ======================

INSERT INTO users(name, email, role) VALUES
('Demo User', 'demo@example.com', 'user');

INSERT INTO accounts(user_id, name, type, balance, low_balance_threshold) VALUES
(1, 'Main Checking', 'checking', 25000.00, 2000.00),
(1, 'Savings', 'savings', 120000.00, 1000.00),
(1, 'Credit Card', 'credit', -4500.00, 0.00);

INSERT INTO goals(user_id, name, target_amount, target_date) VALUES
(1, 'Emergency Fund ₹2L', 200000.00, DATE_ADD(CURDATE(), INTERVAL 300 DAY)),
(1, 'New Laptop',         90000.00,  DATE_ADD(CURDATE(), INTERVAL 120 DAY));

-- Budgets starting this month/week
INSERT INTO budgets(user_id, category, period, limit_amount, start_date) VALUES
(1, 'Groceries',     'monthly', 12000.00, DATE_FORMAT(CURDATE(), '%Y-%m-01')),
(1, 'Food Delivery', 'weekly',   3000.00, DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY));

-- Sample transactions
INSERT INTO transactions(user_id, account_id, amount, tx_type, category, merchant, notes, ts) VALUES
(1, 1, 50000.00, 'credit', 'Salary',        'Acme Corp', 'Monthly salary',     DATE_SUB(NOW(), INTERVAL 20 DAY)),
(1, 1,  1200.00, 'debit',  'Groceries',     'Big Bazaar','Weekly grocery',      DATE_SUB(NOW(), INTERVAL 6 DAY)),
(1, 1,   800.00, 'debit',  'Food Delivery', 'Swiggy',    'Dinner',              DATE_SUB(NOW(), INTERVAL 2 DAY)),
(1, 1,   650.00, 'debit',  'Transport',     'Uber',      'Airport ride',        DATE_SUB(NOW(), INTERVAL 1 DAY));
