#!/usr/bin/env python3

import datetime
import requests

import altair as alt
import streamlit as st
import pandas as pd


TITLE = "TARB Insights"
ICON = "https://archive.org/favicon.ico"
STATSAPI = "https://iabot.toolforge.org/api.php?action=statistics&format=flat"

st.set_page_config(page_title=TITLE, page_icon=ICON)
st.title(TITLE)

@st.cache(ttl=3600, max_entries=1)
def load_data():
  df =  pd.DataFrame(requests.get(STATSAPI).json()["statistics"])
  df["Timestamp"]= pd.to_datetime(df["Timestamp"])
  df["YearMonth"] = df["Timestamp"].dt.strftime("%Y-%m-15")
  return df

try:
  all_data = load_data()
except Exception as e:
  st.error(f"Problem accessing stats from: {STATSAPI}")
  st.exception(e)
  st.stop()

fday = all_data["Timestamp"].dt.date.min()
lday = all_data["Timestamp"].dt.date.max() + datetime.timedelta(days=1)

dayrange = st.slider("Date Range", min_value=fday, max_value=lday, value=(fday, lday))
# dayrange = st.date_input("Date Range", min_value=fday, max_value=lday, value=(fday, lday))

data = all_data.loc[(all_data["Timestamp"] >= pd.Timestamp(dayrange[0])) & (all_data["Timestamp"] < pd.Timestamp(dayrange[1]))]

data.columns = [c.replace(" ", "_") for c in data.columns]
bywiki = data.groupby(["Wiki"]).agg("sum").reset_index()
bymonth = data.groupby(["YearMonth"]).agg("sum").reset_index()
byday = data.groupby(["Timestamp"]).agg("sum").reset_index()
daily_wikis = data.groupby(["Timestamp"]).agg("count")["Wiki"]

cols = st.columns(3)
cols[0].metric("Wikis", f"{len(bywiki):,}", f"{daily_wikis.values[-1]:,}", delta_color="off")
cols[1].metric("Page Edits", f"{bywiki['TotalEdits'].sum():,}", f"{byday['TotalEdits'].values[-1]:,}")
cols[2].metric("Link Edits", f"{bywiki['TotalLinks'].sum():,}", f"{byday['TotalLinks'].values[-1]:,}")

with st.expander("Edits Summary"):
  st.table(pd.concat([byday.sum(numeric_only=True), byday.tail(1).sum(numeric_only=True)], axis=1, keys=["All_Time", "Last_Day"]).astype(int))

"## Monthly Links Edits on All Wikis"
c = alt.Chart(bymonth).mark_bar().encode(
  x="yearmonth(YearMonth):T",
  y="TotalLinks:Q",
  tooltip=["yearmonth(YearMonth)", alt.Tooltip("TotalLinks", format=",")]
)
st.altair_chart(c, use_container_width=True)

with st.expander("Per Month Edits"):
  bymonth["YearMonth"] = bymonth["YearMonth"].str[:7]
  st.write(bymonth)

"## Monthly Links Edits on Selected Wikis"
selected_wikis = st.multiselect("Select Wikis to compare:", bywiki["Wiki"], default=["enwiki"])
sw = data[data["Wiki"].isin(selected_wikis)].groupby(["Wiki", "YearMonth"]).agg("sum").reset_index()
c = alt.Chart(sw).mark_line().encode(
  x="yearmonth(YearMonth):T",
  y="TotalLinks:Q",
  color="Wiki:N",
  strokeDash="Wiki:N"
)
st.altair_chart(c, use_container_width=True)

"## Total Links Edits on Each Wiki (Top 20)"
tt = ["Wiki"] + [alt.Tooltip(f, format=",") for f in ["TotalLinks", "TotalEdits", "DeadEdits", "LiveLinks", "TagLinks", "ProactiveEdits", "ReactiveEdits", "UnknownEdits"]]
c = alt.Chart(bywiki.sort_values(by=["TotalLinks"], ascending=False).head(20)).mark_bar().encode(
  x="TotalLinks:Q",
  y=alt.Y("Wiki:N", sort="-x"),
  tooltip=tt
)
st.altair_chart(c, use_container_width=True)

with st.expander("Per Wiki Edits"):
  st.write(bywiki)
