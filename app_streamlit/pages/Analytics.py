import pandas as pd
import streamlit as st
from datetime import date, timedelta

from utils.db import run_query

st.set_page_config(page_title="Analytics • MirrorBank", layout="wide")
st.title("📈 Analytics & Insights")

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

# ---------------- Filters ----------------
st.sidebar.header("Filters")
months_back = st.sidebar.slider("Months back", min_value=1, max_value=24, value=6)
days_back = st.sidebar.slider("Days window (for categories & recurring)", 7, 180, 90)

# ---------------- Monthly breakdown ----------------
st.subheader("Monthly Breakdown (Debits, Credits, Net)")

monthly = df_query(
    """
    SELECT DATE_FORMAT(ts, '%Y-%m') AS ym,
           SUM(CASE WHEN tx_type='debit'  THEN amount ELSE 0 END) AS debits,
           SUM(CASE WHEN tx_type='credit' THEN amount ELSE 0 END) AS credits
    FROM transactions
    WHERE user_id=%s
      AND ts >= DATE_SUB(CURDATE(), INTERVAL %s MONTH)
    GROUP BY DATE_FORMAT(ts, '%Y-%m')
    ORDER BY ym
    """,
    (USER_ID, months_back),
)
if monthly.empty:
    st.info("No transactions in the selected period.")
else:
    monthly = to_float(monthly, ["debits", "credits"])
    monthly["net"] = monthly["credits"] - monthly["debits"]

    c1, c2 = st.columns([2, 1])
    with c1:
        chart_df = monthly.set_index("ym")[["debits", "credits", "net"]]
        st.line_chart(chart_df, use_container_width=True)
    with c2:
        kpi_last = monthly.tail(1).iloc[0]
        st.metric("Last Month • Debits", f"₹{float(kpi_last['debits']):,.2f}")
        st.metric("Last Month • Credits", f"₹{float(kpi_last['credits']):,.2f}")
        st.metric("Last Month • Net (Credits − Debits)", f"₹{float(kpi_last['net']):,.2f}")

# ---------------- Category-wise spend ----------------
st.subheader("Top Categories (Debits)")

cats = df_query(
    """
    SELECT category,
           SUM(amount) AS spent
    FROM transactions
    WHERE user_id=%s
      AND tx_type='debit'
      AND ts >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
    GROUP BY category
    HAVING spent > 0
    ORDER BY spent DESC
    LIMIT 12
    """,
    (USER_ID, days_back),
)
if cats.empty:
    st.info("No debit transactions in the selected window.")
else:
    cats = to_float(cats, ["spent"])
    st.bar_chart(cats.set_index("category")["spent"], use_container_width=True)

# ---------------- Trend: average daily spend ----------------
st.subheader("Trend: Average Daily Spend")

avg_daily = df_query(
    """
    SELECT DATE(ts) AS d, SUM(CASE WHEN tx_type='debit' THEN amount ELSE 0 END) AS spent
    FROM transactions
    WHERE user_id=%s
      AND ts >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
    GROUP BY DATE(ts)
    ORDER BY d
    """,
    (USER_ID, days_back),
)
if avg_daily.empty:
    st.info("No daily data for the selected range.")
else:
    avg_daily = to_float(avg_daily, ["spent"])
    st.line_chart(avg_daily.set_index("d")["spent"], use_container_width=True)
    st.caption(f"Average per active day: ₹{avg_daily['spent'].mean():,.2f}")

# ---------------- Recurring spend detection (simple heuristic) ----------------
st.subheader("Possible Recurring Payments (Heuristic)")

recurring = df_query(
    """
    SELECT merchant,
           category,
           COUNT(*)                               AS times,
           AVG(amount)                            AS avg_amount,
           MIN(DATE(ts))                          AS first_seen,
           MAX(DATE(ts))                          AS last_seen
    FROM transactions
    WHERE user_id=%s
      AND tx_type='debit'
      AND merchant IS NOT NULL
      AND ts >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
    GROUP BY merchant, category
    HAVING times >= 3
    ORDER BY times DESC, avg_amount DESC
    """,
    (USER_ID, days_back),
)
if recurring.empty:
    st.info("No likely recurring payments detected in this window.")
else:
    recurring = to_float(recurring, ["avg_amount"])
    st.dataframe(
        recurring[["merchant","category","times","avg_amount","first_seen","last_seen"]],
        use_container_width=True,
    )

# ---------------- Recommendations feed ----------------
st.subheader("System Recommendations")

recs = df_query(
    """
    SELECT type, message, created_at
    FROM recommendations
    WHERE user_id=%s
    ORDER BY created_at DESC
    LIMIT 50
    """,
    (USER_ID,),
)
if recs.empty:
    st.caption("No recommendations yet. Add transactions to trigger insights (e.g., low balance, overspending).")
else:
    st.dataframe(recs, use_container_width=True)
