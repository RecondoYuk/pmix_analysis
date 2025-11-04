# app.py
import os
import io
import pandas as pd
import numpy as np
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Menu Mix Dashboard", layout="wide")

# ---------- Data loading & feature engineering ----------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)  # read CSV
    df["BusinessDate"] = pd.to_datetime(df["BusinessDate"], errors="coerce")  # parse date
    df = df.dropna(subset=["BusinessDate"]).copy()  # keep rows with valid dates

    # clean text fields
    for c in ["ProfitCenterName", "Product Class", "Revenue Category", "Item Group", "ItemName"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    # time features
    df["Year"] = df["BusinessDate"].dt.year
    df["Month"] = df["BusinessDate"].dt.to_period("M").dt.to_timestamp()
    iso = df["BusinessDate"].dt.isocalendar()
    df["ISO_Year"] = iso["year"].astype(int)
    df["ISO_Week"] = iso["week"].astype(int)
    df["WeekLabel"] = df["ISO_Year"].astype(str) + "-W" + df["ISO_Week"].astype(str).str.zfill(2)
    df["WeekStart"] = df["BusinessDate"] - pd.to_timedelta(df["BusinessDate"].dt.weekday, unit="D")
    df["DayOfWeek"] = df["BusinessDate"].dt.day_name()

    # Ski Season: Nov 10 → Apr 20 (cross-year)
    def ski_season_label(d):
        m, day, y = d.month, d.day, d.year
        if (m > 11) or (m == 11 and day >= 10) or (m == 12):
            start_year = y
        elif (m < 4) or (m == 4 and day <= 20):
            start_year = y - 1
        else:
            return None  # off-season
        start = pd.Timestamp(year=start_year, month=11, day=10)
        end = pd.Timestamp(year=start_year + 1, month=4, day=20)
        return f"{start_year}-{start_year+1}" if (d >= start) and (d <= end) else None

    df["SkiSeason"] = df["BusinessDate"].apply(ski_season_label)
    df["InSkiSeason"] = df["SkiSeason"].notna()

    # numeric cast
    for m in ["ItemsSold", "NetRevenue", "AvgNetPrice"]:
        if m in df.columns:
            df[m] = pd.to_numeric(df[m], errors="coerce")
    return df

def filter_df(df: pd.DataFrame, filters: dict, date_range):
    q = df.copy()
    for col, values in filters.items():
        if values:
            q = q[q[col].isin(values)]
    if date_range is not None:
        start, end = date_range
        if start is not None:
            q = q[q["BusinessDate"] >= pd.to_datetime(start)]
        if end is not None:
            q = q[q["BusinessDate"] <= pd.to_datetime(end)]
    return q

def aggregate(q: pd.DataFrame, time_slice: str, compare_by: str, metric: str):
    if time_slice == "Month":
        time_key, sort_col = "Month", "Month"
    elif time_slice == "Week":
        time_key, sort_col = "WeekStart", "WeekStart"
    elif time_slice == "Day of Week":
        time_key, sort_col = "DayOfWeek", "DayOfWeek"
        ordered_days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        q["DayOfWeek"] = pd.Categorical(q["DayOfWeek"], categories=ordered_days, ordered=True)
    elif time_slice == "Ski Season":
        time_key, sort_col = "SkiSeason", "SkiSeason"
        q = q[q["SkiSeason"].notna()].copy()
    else:
        time_key, sort_col = "Month", "Month"

    cols = [time_key] + ([compare_by] if compare_by else [])
    g = (q.groupby(cols, dropna=False)[metric].sum(min_count=1).reset_index())
    g = g.sort_values(by=[sort_col, compare_by] if compare_by else [sort_col])
    return g, time_key

def make_fig(agg: pd.DataFrame, time_key: str, compare_by: str, metric: str, chart_type: str, top_n: int):
    data = agg.copy()
    if compare_by:
        totals = data.groupby(compare_by, dropna=False)[metric].sum().reset_index()
        keep = set(totals.sort_values(metric, ascending=False).head(top_n)[compare_by].astype(str))
        data = data[data[compare_by].astype(str).isin(keep)]

    title = f"{metric} by {time_key}" + (f" and {compare_by}" if compare_by else "")
    if chart_type == "Bar":
        fig = px.bar(data, x=time_key, y=metric, color=compare_by if compare_by else None, barmode="group", title=title)
    else:
        fig = px.line(data, x=time_key, y=metric, color=compare_by if compare_by else None, markers=True, title=title)
    fig.update_layout(xaxis_title=time_key, yaxis_title=metric, legend_title=compare_by or "Legend")
    return fig, data

def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")

# ---------- Load data ----------
default_path = "menu_mix_daily_enriched.csv"
uploaded = st.sidebar.file_uploader("Upload CSV (optional; expects BusinessDate, ItemName, ItemsSold, NetRevenue...)", type=["csv"])
df = load_data(uploaded if uploaded is not None else default_path)

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")
min_date = pd.to_datetime(df["BusinessDate"].min()).date()
max_date = pd.to_datetime(df["BusinessDate"].max()).date()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

def ms(col, label=None):
    if col in df.columns:
        opts = sorted(df[col].dropna().unique(), key=lambda x: str(x))
        return st.sidebar.multiselect(label or col, opts)
    return []

filters = {
    "ProfitCenterName": ms("ProfitCenterName", "Profit Center Name"),
    "Product Class": ms("Product Class"),
    "Revenue Category": ms("Revenue Category"),
    "Item Group": ms("Item Group"),
    "ItemName": ms("ItemName", "Item Name"),
}

numeric_candidates = [c for c in ["NetRevenue","ItemsSold","AvgNetPrice"] if c in df.columns]
metric = st.sidebar.selectbox("Metric", numeric_candidates, index=0 if "NetRevenue" in numeric_candidates else 0)
time_slice = st.sidebar.radio("Time slice", ["Month", "Week", "Day of Week", "Ski Season"], index=0)

compare_options = [("ItemName","Item Name"), ("Item Group","Item Group"), ("Revenue Category","Revenue Category"),
                   ("Product Class","Product Class"), ("ProfitCenterName","Profit Center Name")]
compare_options = [opt for opt in compare_options if opt[0] in df.columns]
compare_by_label = st.sidebar.selectbox("Compare by", [label for _, label in compare_options], index=0)
compare_by = [col for col, label in compare_options if label == compare_by_label][0]

top_n = st.sidebar.slider("Top N (comparison dimension)", 3, 50, 20, 1)
chart_type = st.sidebar.radio("Chart type", ["Bar", "Line"], index=0)

# ---------- Apply filters & KPIs ----------
q = filter_df(df, filters, date_range)
kpi1 = float(q["NetRevenue"].sum()) if "NetRevenue" in q.columns else np.nan
kpi2 = float(q["ItemsSold"].sum()) if "ItemsSold" in q.columns else np.nan
kpi3 = float(q["AvgNetPrice"].mean()) if "AvgNetPrice" in q.columns else np.nan

c1, c2, c3 = st.columns(3)
c1.metric("Total Net Revenue", f"${kpi1:,.0f}" if pd.notna(kpi1) else "N/A")
c2.metric("Total Items Sold", f"{kpi2:,.0f}" if pd.notna(kpi2) else "N/A")
c3.metric("Avg Net Price", f"${kpi3:,.2f}" if pd.notna(kpi3) else "N/A")

st.markdown("---")

# ---------- Aggregate + visualize ----------
agg, time_key = aggregate(q, time_slice=time_slice, compare_by=compare_by, metric=metric)
fig, view = make_fig(agg, time_key=time_key, compare_by=compare_by, metric=metric, chart_type=chart_type, top_n=top_n)

st.subheader("Visualization")
st.plotly_chart(fig, use_container_width=True)

st.subheader("Aggregated Data View")
st.dataframe(view)

# ---------- Export ----------
st.markdown("### Export")
st.download_button("⬇️ Download FILTERED RAW rows (CSV)", data=to_csv_bytes(q), file_name="filtered_rows.csv", mime="text/csv")
st.download_button("⬇️ Download AGGREGATED view (CSV)", data=to_csv_bytes(view), file_name="aggregated_view.csv", mime="text/csv")

try:
    img_bytes = fig.to_image(format="png", width=1400, height=700, scale=2)
    st.download_button("⬇️ Download chart as PNG", data=img_bytes, file_name="chart.png", mime="image/png")
except Exception:
    st.info("Install 'kaleido' to enable PNG export (see requirements.txt).")
