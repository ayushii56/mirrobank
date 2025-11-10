import pandas as pd
import streamlit as st
from datetime import datetime, date, time

from utils.db import run_query

st.set_page_config(page_title="Transactions • MirrorBank", layout="wide")
st.title("💸 Transactions")

# ---------------- Helpers ----------------
def df_query(sql, params=None):
    rows = run_query(sql, params, fetch=True)
    return pd.DataFrame(rows or [])

CATEGORY_SUGGESTIONS = [
    "Groceries", "Food Delivery", "Transport", "Shopping",
    "Bills", "Rent", "EMI", "Entertainment", "Healthcare", "Salary", "Other"
]
TX_TYPES = ["debit", "credit"]

# ---------------- Load reference data ----------------
accounts = df_query("SELECT id, name FROM accounts ORDER BY id")
if accounts.empty:
    st.warning("No accounts found. Create one in the Accounts page first.")
    st.stop()

acct_id_by_label = {f"#{row.id} • {row.name}": int(row.id) for _, row in accounts.iterrows()}

# ---------------- Add New Transaction ----------------
with st.sidebar:
    st.header("➕ Add Transaction")
    with st.form("add_tx"):
        account_label = st.selectbox("Account", list(acct_id_by_label.keys()))
        tx_type = st.selectbox("Type", TX_TYPES, index=0)
        amount = st.number_input("Amount (₹)", min_value=0.0, step=100.0, format="%.2f")
        category = st.selectbox("Category", CATEGORY_SUGGESTIONS, index=0)
        merchant = st.text_input("Merchant (optional)")
        notes = st.text_input("Notes (optional)")

        d = st.date_input("Date", value=date.today())
        t = st.time_input("Time", value=datetime.now().time())
        ts_str = datetime.combine(d, t).strftime("%Y-%m-%d %H:%M:%S")

        submit_tx = st.form_submit_button("Add")

    if submit_tx:
        if amount <= 0:
            st.error("Amount must be greater than 0.")
        else:
            ok = run_query(
                """
                INSERT INTO transactions (user_id, account_id, amount, tx_type, category, merchant, notes, ts)
                VALUES (1, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    acct_id_by_label[account_label],
                    float(amount),
                    tx_type,
                    category,
                    merchant if merchant.strip() else None,
                    notes if notes.strip() else None,
                    ts_str,
                ),
                fetch=False,
            )
            if ok:
                st.success("Transaction added.")
                st.rerun()
            else:
                st.error("Failed to add transaction. Check DB connection/permissions.")

# ---------------- Filters ----------------
st.subheader("Search & Filter")
c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])

with c1:
    account_filter = st.multiselect(
        "Accounts",
        options=list(acct_id_by_label.keys()),
        default=list(acct_id_by_label.keys()),
    )
with c2:
    type_filter = st.multiselect("Type", TX_TYPES, default=TX_TYPES)
with c3:
    date_from = st.date_input("From", value=date.today().replace(day=1))
with c4:
    date_to = st.date_input("To", value=date.today())

category_query = st.text_input("Category contains (optional)")
merchant_query = st.text_input("Merchant contains (optional)")

# Build WHERE dynamically
where = ["ts BETWEEN %s AND %s"]
params = [f"{date_from} 00:00:00", f"{date_to} 23:59:59"]

if account_filter:
    ids = [acct_id_by_label[a] for a in account_filter]
    where.append(f"account_id IN ({', '.join(['%s']*len(ids))})")
    params.extend(ids)

if type_filter and len(type_filter) < len(TX_TYPES):
    where.append(f"tx_type IN ({', '.join(['%s']*len(type_filter))})")
    params.extend(type_filter)

if category_query.strip():
    where.append("category LIKE %s")
    params.append(f"%{category_query.strip()}%")

if merchant_query.strip():
    where.append("merchant LIKE %s")
    params.append(f"%{merchant_query.strip()}%")

sql = f"""
    SELECT id, ts, account_id, tx_type, amount, category, merchant, notes
    FROM transactions
    WHERE {' AND '.join(where)}
    ORDER BY ts DESC
    LIMIT 500
"""

tx_df = df_query(sql, params)

# Enrich account names
acct_lookup = {v: k for k, v in acct_id_by_label.items()}
if not tx_df.empty:
    tx_df["account"] = tx_df["account_id"].map(acct_lookup)

st.subheader("Results")
if tx_df.empty:
    st.info("No transactions match your filters.")
else:
    show_cols = ["id", "ts", "account", "tx_type", "amount", "category", "merchant", "notes"]
    st.dataframe(tx_df[show_cols], use_container_width=True)

# ---------------- Edit / Delete ----------------
st.divider()
st.subheader("Edit or Delete a Transaction")

if tx_df.empty:
    st.caption("Run a search or add a transaction to manage it here.")
else:
    tx_labels = [f"#{r.id} • {r.ts} • {r.tx_type} ₹{float(r.amount):,.2f} • {r.category}" for _, r in tx_df.iterrows()]
    chosen = st.selectbox("Pick a transaction", options=list(range(len(tx_labels))), format_func=lambda i: tx_labels[i])
    row = tx_df.iloc[chosen]

    colA, colB, colC, colD = st.columns(4)
    with colA:
        new_type = st.selectbox("Type", TX_TYPES, index=TX_TYPES.index(row["tx_type"]))
    with colB:
        new_amount = st.number_input("Amount (₹)", value=float(row["amount"]), step=100.0, format="%.2f")
    with colC:
        new_category = st.text_input("Category", value=row["category"])
    with colD:
        new_account = st.selectbox("Account", list(acct_id_by_label.keys()),
                                   index=list(acct_id_by_label.values()).index(int(row["account_id"])))

    m1, m2 = st.columns(2)
    with m1:
        new_merchant = st.text_input("Merchant", value=row["merchant"] or "")
    with m2:
        new_notes = st.text_input("Notes", value=row["notes"] or "")

    dcol, tcol = st.columns(2)
    # Parse current ts
    cur_dt = pd.to_datetime(row["ts"])
    with dcol:
        new_date = st.date_input("Date", value=cur_dt.date())
    with tcol:
        new_time = st.time_input("Time", value=cur_dt.time())
    new_ts = datetime.combine(new_date, new_time).strftime("%Y-%m-%d %H:%M:%S")

    colU, colDel = st.columns([1, 1])
    with colU:
        if st.button("💾 Update Transaction"):
            ok = run_query(
                """
                UPDATE transactions
                SET account_id=%s, amount=%s, tx_type=%s, category=%s, merchant=%s, notes=%s, ts=%s, updated_at=NOW()
                WHERE id=%s
                """,
                (
                    acct_id_by_label[new_account],
                    float(new_amount),
                    new_type,
                    new_category.strip() or "Other",
                    new_merchant.strip() or None,
                    new_notes.strip() or None,
                    new_ts,
                    int(row["id"]),
                ),
                fetch=False,
            )
            if ok:
                st.success("Transaction updated.")
                st.rerun()
            else:
                st.error("Update failed.")

    with colDel:
        danger = st.text_input("Type DELETE to confirm remove", key="txdel")
        if st.button("🗑️ Delete Transaction"):
            if danger.strip().upper() == "DELETE":
                ok = run_query("DELETE FROM transactions WHERE id=%s", (int(row["id"]),), fetch=False)
                if ok:
                    st.success("Transaction deleted.")
                    st.rerun()
                else:
                    st.error("Delete failed.")
            else:
                st.error("Type DELETE to confirm.")
