import pandas as pd
import streamlit as st
from utils.db import run_query

st.set_page_config(page_title="Accounts • MirrorBank", layout="wide")
st.title("🏦 Accounts")

# ---------- Helpers ----------
def df_query(sql, params=None):
    rows = run_query(sql, params, fetch=True)
    return pd.DataFrame(rows or [])

ACCOUNT_TYPES = ["checking", "savings", "credit", "wallet"]

# ---------- Load data ----------
accounts = df_query("""
    SELECT id, name, type, balance, low_balance_threshold, created_at
    FROM accounts
    ORDER BY id
""")

# ---------- Summary ----------
left, right = st.columns([2, 1])
with left:
    st.subheader("All Accounts")
    if accounts.empty:
        st.info("No accounts yet. Add your first account on the right.")
    else:
        st.dataframe(accounts, use_container_width=True)

with right:
    st.subheader("Add Account")
    with st.form("add_account"):
        name = st.text_input("Account Name", placeholder="Main Checking")
        a_type = st.selectbox("Type", ACCOUNT_TYPES, index=0)
        start_balance = st.number_input("Starting Balance (₹)", value=0.0, step=100.0, format="%.2f")
        low_thresh = st.number_input("Low Balance Alert Threshold (₹)", value=1000.0, step=100.0, format="%.2f")
        submitted = st.form_submit_button("➕ Create Account")

    if submitted:
        if not name.strip():
            st.error("Please enter an account name.")
        else:
            ok = run_query(
                """
                INSERT INTO accounts (user_id, name, type, balance, low_balance_threshold)
                VALUES (1, %s, %s, %s, %s)
                """,
                (name.strip(), a_type, float(start_balance), float(low_thresh)),
                fetch=False,
            )
            if ok:
                st.success("Account created.")
                st.rerun()
            else:
                st.error("Could not create account. Check DB connection/permissions.")

st.divider()

# ---------- Edit / Delete ----------
st.subheader("Manage Accounts")

if accounts.empty:
    st.caption("Add an account to enable management tools.")
else:
    # Select account to manage
    acc_names = [f"#{row.id} • {row.name} ({row.type})" for _, row in accounts.iterrows()]
    idx = st.selectbox("Pick an account", options=list(range(len(acc_names))), format_func=lambda i: acc_names[i])
    sel = accounts.iloc[idx]

    colA, colB, colC = st.columns(3)
    with colA:
        st.metric("Current Balance", f"₹{float(sel.balance):,.2f}")
    with colB:
        st.metric("Low Threshold", f"₹{float(sel.low_balance_threshold):,.2f}")
    with colC:
        st.metric("ID", str(int(sel.id)))

    with st.expander("✏️ Update Threshold / Rename"):
        new_name = st.text_input("Rename Account", value=sel.name, key="rename")
        new_thresh = st.number_input("Low Balance Threshold (₹)", value=float(sel.low_balance_threshold), step=100.0, format="%.2f", key="thresh")
        if st.button("Save Changes"):
            ok = run_query(
                "UPDATE accounts SET name=%s, low_balance_threshold=%s WHERE id=%s",
                (new_name.strip(), float(new_thresh), int(sel.id)),
                fetch=False,
            )
            if ok:
                st.success("Account updated.")
                st.rerun()
            else:
                st.error("Update failed.")

    with st.expander("💸 Adjust Balance (no transaction record)"):
        st.caption("For quick corrections. For audit trails, use the Transactions page instead.")
        new_bal = st.number_input("Set Balance to (₹)", value=float(sel.balance), step=100.0, format="%.2f")
        if st.button("Set Balance"):
            ok = run_query("UPDATE accounts SET balance=%s WHERE id=%s", (float(new_bal), int(sel.id)), fetch=False)
            if ok:
                st.success("Balance updated.")
                st.rerun()
            else:
                st.error("Balance update failed.")

    with st.expander("🗑️ Delete Account (danger)"):
        st.warning("Deleting an account also deletes its transactions (cascade).")
        confirm = st.text_input("Type DELETE to confirm")
        if st.button("Delete Account"):
            if confirm.strip().upper() == "DELETE":
                ok = run_query("DELETE FROM accounts WHERE id=%s", (int(sel.id),), fetch=False)
                if ok:
                    st.success("Account deleted.")
                    st.rerun()
                else:
                    st.error("Delete failed.")
            else:
                st.error("Type DELETE to confirm.")
