import pandas as pd
import streamlit as st
from datetime import date

from utils.db import run_query

st.set_page_config(page_title="Goals • MirrorBank", layout="wide")
st.title("🎯 Financial Goals")

USER_ID = 1

# ---------------- Helpers ----------------
def df_query(sql, params=None):
    rows = run_query(sql, params, fetch=True)
    return pd.DataFrame(rows or [])

# ---------------- Load data ----------------
goals = df_query(
    """
    SELECT g.id, g.name, g.target_amount, g.target_date, g.created_at,
           COALESCE(SUM(CASE WHEN t.tx_type='credit' THEN t.amount ELSE 0 END), 0) AS contributed
    FROM goals g
    LEFT JOIN transactions t ON t.goal_id = g.id
    WHERE g.user_id = %s
    GROUP BY g.id, g.name, g.target_amount, g.target_date, g.created_at
    ORDER BY g.target_date ASC, g.id ASC
    """,
    (USER_ID,),
)

# Ensure numeric for math
if not goals.empty:
    goals["target_amount"] = pd.to_numeric(goals["target_amount"], errors="coerce").fillna(0.0)
    goals["contributed"] = pd.to_numeric(goals["contributed"], errors="coerce").fillna(0.0)
    goals["remaining"] = (goals["target_amount"] - goals["contributed"]).clip(lower=0.0)
    # avoid divide-by-zero
    goals["progress_%"] = (goals["contributed"] / goals["target_amount"].replace(0, pd.NA)).fillna(0.0) * 100.0
    goals["progress_%"] = goals["progress_%"].round(2)

# ---------------- List / Overview ----------------
st.subheader("Your Goals")

if goals.empty:
    st.info("No goals yet. Add one from the sidebar.")
else:
    show_cols = ["id","name","target_amount","contributed","remaining","progress_%","target_date","created_at"]
    st.dataframe(goals[show_cols], use_container_width=True)

# ---------------- Sidebar: Add Goal ----------------
with st.sidebar:
    st.header("➕ Add Goal")
    g_name = st.text_input("Goal name", placeholder="Emergency Fund, New Laptop, Trip…")
    g_target = st.number_input("Target amount (₹)", min_value=0.0, step=500.0, value=10000.0, format="%.2f")
    g_date = st.date_input("Target date", value=date.today())
    if st.button("Create Goal"):
        if not g_name.strip():
            st.error("Please enter a goal name.")
        elif g_target <= 0:
            st.error("Target amount must be greater than 0.")
        else:
            ok = run_query(
                "INSERT INTO goals (user_id, name, target_amount, target_date) VALUES (%s, %s, %s, %s)",
                (USER_ID, g_name.strip(), float(g_target), str(g_date)),
                fetch=False,
            )
            if ok:
                st.success("Goal created.")
                st.rerun()
            else:
                st.error("Could not create goal. Check DB connection/permissions.")

# ---------------- Contribute to Goal (records a credit tx) ----------------
st.divider()
st.subheader("Add Contribution")

if goals.empty:
    st.caption("Create a goal first to contribute.")
else:
    # accounts for funding
    accounts = df_query("SELECT id, name FROM accounts ORDER BY id")
    if accounts.empty:
        st.warning("No accounts found. Create one in Accounts page first.")
    else:
        goal_labels = [f"#{r.id} • {r.name} (target ₹{float(r.target_amount):,.0f})" for _, r in goals.iterrows()]
        acct_labels = [f"#{r.id} • {r.name}" for _, r in accounts.iterrows()]
        g_idx = st.selectbox("Goal", options=list(range(len(goal_labels))), format_func=lambda i: goal_labels[i])
        a_idx = st.selectbox("From Account", options=list(range(len(acct_labels))), format_func=lambda i: acct_labels[i])

        amount = st.number_input("Contribution amount (₹)", min_value=0.0, step=500.0, value=2000.0, format="%.2f")
        notes = st.text_input("Notes (optional)", placeholder="Monthly saving")
        if st.button("Add Contribution"):
            if amount <= 0:
                st.error("Amount must be greater than 0.")
            else:
                goal_id = int(goals.iloc[g_idx]["id"])
                account_id = int(accounts.iloc[a_idx]["id"])
                ok = run_query(
                    """
                    INSERT INTO transactions (user_id, account_id, amount, tx_type, category, merchant, notes, goal_id, ts)
                    VALUES (%s, %s, %s, 'credit', 'Goal Savings', NULL, %s, %s, NOW())
                    """,
                    (USER_ID, account_id, float(amount), notes if notes.strip() else None, goal_id),
                    fetch=False,
                )
                if ok:
                    st.success("Contribution recorded.")
                    st.rerun()
                else:
                    st.error("Failed to add contribution.")

# ---------------- Manage Existing Goal ----------------
st.divider()
st.subheader("Manage Goal")

if goals.empty:
    st.caption("Add a goal to enable management.")
else:
    labels = [f"#{r.id} • {r.name} • target ₹{float(r.target_amount):,.0f} by {r.target_date}" for _, r in goals.iterrows()]
    idx = st.selectbox("Pick a goal", options=list(range(len(labels))), format_func=lambda i: labels[i])
    sel = goals.iloc[idx]

    col1, col2, col3 = st.columns(3)
    col1.metric("Target", f"₹{float(sel['target_amount']):,.2f}")
    col2.metric("Contributed", f"₹{float(sel['contributed']):,.2f}")
    col3.metric("Progress", f"{float(sel['progress_%']):.1f}%")

    with st.expander("✏️ Edit Goal"):
        new_name = st.text_input("Name", value=sel["name"])
        new_target = st.number_input("Target amount (₹)", value=float(sel["target_amount"]), step=500.0, format="%.2f")
        new_date = st.date_input("Target date", value=pd.to_datetime(sel["target_date"]).date())
        if st.button("Save Goal"):
            ok = run_query(
                "UPDATE goals SET name=%s, target_amount=%s, target_date=%s WHERE id=%s",
                (new_name.strip(), float(new_target), str(new_date), int(sel["id"])),
                fetch=False,
            )
            if ok:
                st.success("Goal updated.")
                st.rerun()
            else:
                st.error("Update failed.")

    with st.expander("🗑️ Delete Goal (danger)"):
        st.warning("Existing transactions will keep their amounts; their goal link will become NULL.")
        confirm = st.text_input("Type DELETE to confirm", key="delgoal")
        if st.button("Delete Goal"):
            if confirm.strip().upper() == "DELETE":
                ok = run_query("DELETE FROM goals WHERE id=%s", (int(sel["id"]),), fetch=False)
                if ok:
                    st.success("Goal deleted.")
                    st.rerun()
                else:
                    st.error("Delete failed.")
            else:
                st.error("Type DELETE to confirm.")
