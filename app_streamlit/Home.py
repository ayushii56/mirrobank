
import pandas as pd
import streamlit as st

# DB helper
from utils.db import run_query

st.set_page_config(page_title="MirrorBank — Dashboard", layout="wide")
st.title("💳 MirrorBank — Dashboard")

USER_ID = 1

# ---------------- Helpers ----------------
def df_query(sql, params=None):
    rows = run_query(sql, params, fetch=True)
    return pd.DataFrame(rows or [])

def to_float(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df

# ---------------- Core pulls ----------------
accounts_df = df_query(
    """
    SELECT id, name, type, balance, low_balance_threshold
    FROM accounts
    WHERE user_id=%s
    ORDER BY id
    """,
    (USER_ID,),
)

last_30_days = df_query(
    """
    SELECT DATE(ts) AS day,
           SUM(CASE WHEN tx_type='debit'  THEN amount ELSE 0 END) AS debits,
           SUM(CASE WHEN tx_type='credit' THEN amount ELSE 0 END) AS credits
    FROM transactions
    WHERE user_id=%s
      AND ts >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
    GROUP BY DATE(ts)
    ORDER BY day
    """,
    (USER_ID,),
)

recent_tx = df_query(
    """
    SELECT ts, tx_type, amount, category, merchant, notes
    FROM transactions
    WHERE user_id=%s
    ORDER BY ts DESC
    LIMIT 20
    """,
    (USER_ID,),
)

category_totals = df_query(
    """
    SELECT category,
           SUM(CASE WHEN tx_type='debit' THEN amount ELSE 0 END) AS spent
    FROM transactions
    WHERE user_id=%s
    GROUP BY category
    HAVING spent > 0
    ORDER BY spent DESC
    LIMIT 10
    """,
    (USER_ID,),
)

# ---------------- Quick Analytics (new) ----------------
# 1) Last month debits, credits, net
last_month = df_query(
    """
    SELECT
      DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 MONTH), '%Y-%m') AS ym,
      SUM(CASE WHEN tx_type='debit'  THEN amount ELSE 0 END) AS debits,
      SUM(CASE WHEN tx_type='credit' THEN amount ELSE 0 END) AS credits
    FROM transactions
    WHERE user_id=%s
      AND DATE_FORMAT(ts, '%Y-%m') = DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 MONTH), '%Y-%m')
    """,
    (USER_ID,),
)
last_month = to_float(last_month, ["debits", "credits"])
lm_deb = float(last_month["debits"].iloc[0]) if not last_month.empty else 0.0
lm_cre = float(last_month["credits"].iloc[0]) if not last_month.empty else 0.0
lm_net = lm_cre - lm_deb

# 2) Top spend category in last 30 days
top_cat = df_query(
    """
    SELECT category, SUM(amount) AS spent
    FROM transactions
    WHERE user_id=%s AND tx_type='debit'
      AND ts >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
    GROUP BY category
    ORDER BY spent DESC
    LIMIT 1
    """,
    (USER_ID,),
)
top_cat_name = top_cat["category"].iloc[0] if not top_cat.empty else "—"
top_cat_spent = float(pd.to_numeric(top_cat["spent"], errors="coerce").fillna(0.0).iloc[0]) if not top_cat.empty else 0.0

# 3) Average daily debits in last 30 days
avg_daily = df_query(
    """
    SELECT DATE(ts) AS d, SUM(CASE WHEN tx_type='debit' THEN amount ELSE 0 END) AS spent
    FROM transactions
    WHERE user_id=%s
      AND ts >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
    GROUP BY DATE(ts)
    ORDER BY d
    """,
    (USER_ID,),
)
avg_daily = to_float(avg_daily, ["spent"])
avg_daily_spend = float(avg_daily["spent"].mean()) if not avg_daily.empty else 0.0

# ---------------- KPIs ----------------
total_balance = float(pd.to_numeric(accounts_df["balance"], errors="coerce").fillna(0.0).sum()) if not accounts_df.empty else 0.0
num_accounts = int(len(accounts_df))
debits_30 = float(pd.to_numeric(last_30_days["debits"], errors="coerce").fillna(0.0).sum()) if not last_30_days.empty else 0.0

k1, k2, k3 = st.columns(3)
k1.metric("Total Balance", f"₹{total_balance:,.2f}")
k2.metric("Accounts", str(num_accounts))
k3.metric("Debits (30 days)", f"₹{debits_30:,.2f}")

# ---------------- Quick Analytics Card (new) ----------------
st.subheader("Quick Analytics")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Last Month Net (Cr − Dr)", f"₹{lm_net:,.2f}", help=f"Credits ₹{lm_cre:,.2f} • Debits ₹{lm_deb:,.2f}")
with c2:
    st.metric("Top Spend (30d)", f"{top_cat_name}", help=f"₹{top_cat_spent:,.2f}")
with c3:
    st.metric("Avg Daily Debits (30d)", f"₹{avg_daily_spend:,.2f}")

# ---------------- Accounts Table ----------------
st.subheader("Accounts")
if accounts_df.empty:
    st.info("No accounts found.")
else:
    st.dataframe(accounts_df, use_container_width=True)

# ---------------- Charts ----------------
st.subheader("Spending & Credits — Last 30 Days")
if last_30_days.empty:
    st.info("No 30-day data found.")
else:
    chart_df = last_30_days.copy()
    chart_df["debits"] = pd.to_numeric(chart_df["debits"], errors="coerce").fillna(0.0)
    chart_df["credits"] = pd.to_numeric(chart_df["credits"], errors="coerce").fillna(0.0)
    chart_df = chart_df.set_index("day")[["debits", "credits"]]
    st.line_chart(chart_df, use_container_width=True)

st.subheader("Top Spending Categories")
if category_totals.empty:
    st.info("No category spending found.")
else:
    ct = category_totals.copy()
    ct["spent"] = pd.to_numeric(ct["spent"], errors="coerce").fillna(0.0)
    st.bar_chart(ct.set_index("category")["spent"], use_container_width=True)

# ---------------- Recent Transactions ----------------
st.subheader("Recent Transactions")
if recent_tx.empty:
    st.info("No transactions yet.")
else:
    st.dataframe(recent_tx, use_container_width=True)

st.caption("MirrorBank — Your Smart Finance Dashboard")
