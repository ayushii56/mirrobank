import pandas as pd
import streamlit as st
from datetime import date, timedelta

from utils.db import run_query

st.set_page_config(page_title="Budgets • MirrorBank", layout="wide")
st.title("📊 Budgets & Alerts")

USER_ID = 1
PERIODS = ["weekly", "monthly"]

# ---------------- Helpers ----------------
def df_query(sql, params=None):
    rows = run_query(sql, params, fetch=True)
    return pd.DataFrame(rows or [])

def start_of_week(d: date) -> date:
    # Monday as start of week
    return d - timedelta(days=d.weekday())

def start_of_month(d: date) -> date:
    return d.replace(day=1)

# ---------------- Current Budgets with Progress ----------------
st.subheader("Active Budgets (with progress)")

budgets = df_query(
    """
    SELECT
      b.id, b.category, b.period, b.limit_amount, b.start_date,
      CASE
        WHEN b.period='weekly'  THEN DATE_ADD(b.start_date, INTERVAL 7 DAY)
        ELSE DATE_ADD(LAST_DAY(b.start_date), INTERVAL 1 DAY)
      END AS end_date,
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
    WHERE b.user_id = %s
    ORDER BY b.start_date DESC, b.category
    """,
    (USER_ID,),
)

if budgets.empty:
    st.info("No budgets yet. Create one using the form on the right.")
else:
    # Ensure numeric columns are float (MySQL DECIMAL may arrive as strings)
    budgets["limit_amount"] = pd.to_numeric(budgets["limit_amount"], errors="coerce").fillna(0.0)
    budgets["spent"] = pd.to_numeric(budgets["spent"], errors="coerce").fillna(0.0)

    budgets["remaining"] = budgets["limit_amount"] - budgets["spent"]
    budgets["progress_%"] = (budgets["spent"] / budgets["limit_amount"]).replace([float("inf")], 0.0) * 100.0
    budgets["progress_%"] = budgets["progress_%"].fillna(0.0).round(2)

    st.dataframe(
        budgets[["id","category","period","start_date","end_date","limit_amount","spent","remaining","progress_%"]],
        use_container_width=True,
    )

# ---------------- Add Budget ----------------
with st.sidebar:
    st.header("➕ Create Budget")

    category = st.text_input("Category", value="Groceries")
    period = st.selectbox("Period", PERIODS, index=1)  # default monthly
    limit_amount = st.number_input("Limit Amount (₹)", min_value=0.0, value=3000.0, step=100.0, format="%.2f")

    # sensible default start date
    today = date.today()
    default_start = start_of_month(today) if period == "monthly" else start_of_week(today)
    start_date_input = st.date_input("Start Date", value=default_start, format="YYYY-MM-DD")

    if st.button("Create Budget"):
        if not category.strip():
            st.error("Please enter a category.")
        elif limit_amount <= 0:
            st.error("Budget limit must be greater than 0.")
        else:
            ok = run_query(
                """
                INSERT INTO budgets (user_id, category, period, limit_amount, start_date)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (USER_ID, category.strip(), period, float(limit_amount), str(start_date_input)),
                fetch=False,
            )
            if ok:
                st.success("Budget created.")
                st.rerun()
            else:
                st.error("Could not create budget. If one already exists with the same (user, category, period, start_date), update it instead.")

# ---------------- Manage Existing Budget ----------------
st.divider()
st.subheader("Manage a Budget")

if budgets.empty:
    st.caption("Add a budget to enable management.")
else:
    labels = [f"#{r.id} • {r.category} • {r.period} • starts {r.start_date}" for _, r in budgets.iterrows()]
    idx = st.selectbox("Pick a budget", options=list(range(len(labels))), format_func=lambda i: labels[i])
    sel = budgets.iloc[idx]

    c1, c2, c3 = st.columns(3)
    c1.metric("Limit", f"₹{float(sel['limit_amount']):,.2f}")
    c2.metric("Spent", f"₹{float(sel['spent']):,.2f}")
    c3.metric("Progress", f"{float(sel['progress_%']):.1f}%")

    with st.expander("✏️ Update Limit"):
        new_limit = st.number_input("New Limit (₹)", value=float(sel["limit_amount"]), step=100.0, format="%.2f")
        if st.button("Save Limit"):
            ok = run_query("UPDATE budgets SET limit_amount=%s WHERE id=%s", (float(new_limit), int(sel["id"])), fetch=False)
            if ok:
                st.success("Limit updated.")
                st.rerun()
            else:
                st.error("Update failed.")

    with st.expander("🗑️ Delete Budget (danger)"):
        st.warning("This will remove the budget and its alerts.")
        confirm = st.text_input("Type DELETE to confirm", key="delbud")
        if st.button("Delete Budget"):
            if confirm.strip().upper() == "DELETE":
                ok = run_query("DELETE FROM budgets WHERE id=%s", (int(sel["id"]),), fetch=False)
                if ok:
                    st.success("Budget deleted.")
                    st.rerun()
                else:
                    st.error("Delete failed.")
            else:
                st.error("Type DELETE to confirm.")

# ---------------- Alerts ----------------
st.divider()
st.subheader("Recent Budget Alerts")

alerts = df_query(
    """
    SELECT ba.id, b.category, b.period, ba.level, ba.message, ba.created_at
    FROM budget_alerts ba
    JOIN budgets b ON b.id = ba.budget_id
    WHERE ba.user_id = %s
    ORDER BY ba.created_at DESC
    LIMIT 50
    """,
    (USER_ID,),
)

if alerts.empty:
    st.info("No alerts yet. Alerts are generated automatically when transactions are inserted or updated.")
else:
    st.dataframe(alerts, use_container_width=True)
