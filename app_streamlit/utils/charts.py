# app_streamlit/utils/charts.py
import pandas as pd
import streamlit as st

def _to_float(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df

def line_debits_credits(df, x_col="day", y_cols=("debits", "credits")):
    """
    Expects columns: day, debits, credits (numbers or strings)
    Renders a line chart with Streamlit.
    """
    if df.empty or x_col not in df.columns:
        st.info("No data to plot.")
        return
    df = df.copy()
    df = _to_float(df, list(y_cols))
    st.line_chart(df.set_index(x_col)[list(y_cols)], use_container_width=True)

def bar_top_categories(df, x_col="category", y_col="spent"):
    """
    Expects columns: category, spent
    Renders a bar chart for top spending categories.
    """
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        st.info("No category data to plot.")
        return
    df = df.copy()
    df = _to_float(df, [y_col])
    st.bar_chart(df.set_index(x_col)[y_col], use_container_width=True)

def line_single_series(df, x_col, y_col):
    """
    Generic line plot: one series over time.
    """
    if df.empty or x_col not in df.columns or y_col not in df.columns:
        st.info("Nothing to plot yet.")
        return
    df = df.copy()
    df = _to_float(df, [y_col])
    st.line_chart(df.set_index(x_col)[y_col], use_container_width=True)
