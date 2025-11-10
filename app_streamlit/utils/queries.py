# app_streamlit/utils/queries.py
import pandas as pd
from .db import run_query

USER_ID = 1  # adjust when you add auth

def _df(sql, params=None):
    rows = run_query(sql, params, fetch=True)
    return pd.DataFrame(rows or [])

# ----- Home / shared pulls -----
def fetch_accounts():
    return _df("""
        SELECT id, name, type, balance, low_balance_threshold
        FROM accounts
        WHERE user_id=%s
        ORDER BY id
    """, (USER_ID,))

def fetch_last_30_day_summary():
    return _df("""
        SELECT DATE(ts) AS day,
               SUM(CASE WHEN tx_type='debit'  THEN amount ELSE 0 END) AS debits,
               SUM(CASE WHEN tx_type='credit' THEN amount ELSE 0 END) AS credits
        FROM transactions
        WHERE user_id=%s
          AND ts >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        GROUP BY DATE(ts)
        ORDER BY day
    """, (USER_ID,))

def fetch_category_totals(limit=10):
    return _df(f"""
        SELECT category,
               SUM(CASE WHEN tx_type='debit' THEN amount ELSE 0 END) AS spent
        FROM transactions
        WHERE user_id=%s
        GROUP BY category
        HAVING spent > 0
        ORDER BY spent DESC
        LIMIT {int(limit)}
    """, (USER_ID,))

def fetch_recent_transactions(limit=20):
    return _df(f"""
        SELECT ts, tx_type, amount, category, merchant, notes
        FROM transactions
        WHERE user_id=%s
        ORDER BY ts DESC
        LIMIT {int(limit)}
    """, (USER_ID,))

# ----- Accounts CRUD -----
def add_account(name, a_type, balance, threshold):
    return run_query("""
        INSERT INTO accounts (user_id, name, type, balance, low_balance_threshold)
        VALUES (%s, %s, %s, %s, %s)
    """, (USER_ID, name, a_type, float(balance), float(threshold)), fetch=False)

def update_account(acc_id, name, threshold):
    return run_query("""
        UPDATE accounts SET name=%s, low_balance_threshold=%s WHERE id=%s AND user_id=%s
    """, (name, float(threshold), int(acc_id), USER_ID), fetch=False)

def delete_account(acc_id):
    return run_query("DELETE FROM accounts WHERE id=%s AND user_id=%s",
                     (int(acc_id), USER_ID), fetch=False)

# ----- Transactions -----
def add_transaction(account_id, amount, tx_type, category, merchant, notes, ts_str):
    return run_query("""
        INSERT INTO transactions (user_id, account_id, amount, tx_type, category, merchant, notes, ts)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (USER_ID, int(account_id), float(amount), tx_type, category,
          merchant, notes, ts_str), fetch=False)

def update_transaction(tx_id, account_id, amount, tx_type, category, merchant, notes, ts_str):
    return run_query("""
        UPDATE transactions
        SET account_id=%s, amount=%s, tx_type=%s, category=%s, merchant=%s, notes=%s, ts=%s, updated_at=NOW()
        WHERE id=%s AND user_id=%s
    """, (int(account_id), float(amount), tx_type, category, merchant, notes, ts_str, int(tx_id), USER_ID), fetch=False)

def delete_transaction(tx_id):
    return run_query("DELETE FROM transactions WHERE id=%s AND user_id=%s",
                     (int(tx_id), USER_ID), fetch=False)

# ----- Budgets -----
def fetch_budgets_with_progress():
    return _df("""
        SELECT
          b.id, b.category, b.period, b.limit_amount, b.start_date,
          CASE WHEN b.period='weekly' THEN DATE_ADD(b.start_date, INTERVAL 7 DAY)
               ELSE DATE_ADD(LAST_DAY(b.start_date), INTERVAL 1 DAY) END AS end_date,
          COALESCE((
            SELECT SUM(t.amount) FROM transactions t
            WHERE t.user_id = b.user_id
              AND t.category = b.category
              AND t.tx_type = 'debit'
              AND t.ts >= b.start_date
              AND t.ts <  (CASE WHEN b.period='weekly'
                                THEN DATE_ADD(b.start_date, INTERVAL 7 DAY)
                                ELSE DATE_ADD(LAST_DAY(b.start_date), INTERVAL 1 DAY)
                           END)
          ),0) AS spent
        FROM budgets b
        WHERE b.user_id=%s
        ORDER BY b.start_date DESC, b.category
    """, (USER_ID,))

def create_budget(category, period, limit_amount, start_date):
    return run_query("""
        INSERT INTO budgets (user_id, category, period, limit_amount, start_date)
        VALUES (%s, %s, %s, %s, %s)
    """, (USER_ID, category, period, float(limit_amount), str(start_date)), fetch=False)

def update_budget_limit(budget_id, new_limit):
    return run_query("UPDATE budgets SET limit_amount=%s WHERE id=%s AND user_id=%s",
                     (float(new_limit), int(budget_id), USER_ID), fetch=False)

def delete_budget(budget_id):
    return run_query("DELETE FROM budgets WHERE id=%s AND user_id=%s",
                     (int(budget_id), USER_ID), fetch=False)

def fetch_budget_alerts(limit=50):
    return _df(f"""
        SELECT ba.id, b.category, b.period, ba.level, ba.message, ba.created_at
        FROM budget_alerts ba
        JOIN budgets b ON b.id = ba.budget_id
        WHERE ba.user_id = %s
        ORDER BY ba.created_at DESC
        LIMIT {int(limit)}
    """, (USER_ID,))

# ----- Goals -----
def fetch_goals_with_contrib():
    return _df("""
        SELECT g.id, g.name, g.target_amount, g.target_date, g.created_at,
               COALESCE(SUM(CASE WHEN t.tx_type='credit' THEN t.amount ELSE 0 END), 0) AS contributed
        FROM goals g
        LEFT JOIN transactions t ON t.goal_id = g.id
        WHERE g.user_id=%s
        GROUP BY g.id, g.name, g.target_amount, g.target_date, g.created_at
        ORDER BY g.target_date ASC, g.id ASC
    """, (USER_ID,))

def create_goal(name, target_amount, target_date):
    return run_query("""
        INSERT INTO goals (user_id, name, target_amount, target_date)
        VALUES (%s, %s, %s, %s)
    """, (USER_ID, name, float(target_amount), str(target_date)), fetch=False)

def update_goal(goal_id, name, target_amount, target_date):
    return run_query("""
        UPDATE goals SET name=%s, target_amount=%s, target_date=%s
        WHERE id=%s AND user_id=%s
    """, (name, float(target_amount), str(target_date), int(goal_id), USER_ID), fetch=False)

def delete_goal(goal_id):
    return run_query("DELETE FROM goals WHERE id=%s AND user_id=%s",
                     (int(goal_id), USER_ID), fetch=False)

def contribute_to_goal(goal_id, account_id, amount, notes=None):
    return run_query("""
        INSERT INTO transactions (user_id, account_id, amount, tx_type, category, merchant, notes, goal_id, ts)
        VALUES (%s, %s, %s, 'credit', 'Goal Savings', NULL, %s, %s, NOW())
    """, (USER_ID, int(account_id), float(amount), notes, int(goal_id)), fetch=False)
