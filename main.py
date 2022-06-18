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
  df["DateTime"] = df["Timestamp"].str[:10] + "T12:00:00Z"
  df["YearMonth"] = df["Timestamp"].str[:8] + "15"
  df["Timestamp"] = pd.to_datetime(df["Timestamp"])
  return df

try:
  all_data = load_data()
except Exception as e:
  st.error(f"Problem accessing stats from: {STATSAPI}")
  st.exception(e)
  st.stop()

fday = all_data["Timestamp"].dt.date.min()
lday = all_data["Timestamp"].dt.date.max()

dayrange = st.date_input("Date Range", min_value=fday, max_value=lday, value=(fday, lday))

try:
  data = all_data.loc[(all_data["Timestamp"] >= pd.Timestamp(dayrange[0])) & (all_data["Timestamp"] <= pd.Timestamp(dayrange[1]))]
except IndexError as e:
  st.warning(f"Select a valid date range between {fday} and {lday}")
  st.stop()

data.columns = [c.replace(" ", "_") for c in data.columns]
bywiki = data.groupby(["Wiki"]).agg("sum").reset_index()
bymonth = data.groupby(["YearMonth"]).agg("sum").reset_index()
byday = data.groupby(["DateTime"]).agg("sum").reset_index()
daily_wikis = data.groupby(["Timestamp"]).agg("count")["Wiki"]

tt = [alt.Tooltip(f, format=",") for f in ["TotalLinks", "TotalEdits", "DeadEdits", "LiveLinks", "TagLinks", "ProactiveEdits", "ReactiveEdits", "UnknownEdits"]]

cols = st.columns(3)
cols[0].metric("Wikis", f"{len(bywiki):,}", f"{daily_wikis.values[-1]:,}", delta_color="off")
cols[1].metric("Page Edits", f"{bywiki['TotalEdits'].sum():,}", f"{byday['TotalEdits'].values[-1]:,}")
cols[2].metric("Link Edits", f"{bywiki['TotalLinks'].sum():,}", f"{byday['TotalLinks'].values[-1]:,}")

cols = st.columns(3)
cols[0].metric("Tagged Links", f"{bywiki['TagLinks'].sum():,}", f"{byday['TagLinks'].values[-1]:,}")
cols[1].metric("Fixed Dead Links", f"{bywiki['DeadLinks'].sum():,}", f"{byday['DeadLinks'].values[-1]:,}")
cols[2].metric("Added Archive URLs", f"{bywiki['LiveLinks'].sum()+bywiki['DeadLinks'].sum():,}", f"{byday['LiveLinks'].values[-1]+byday['DeadLinks'].values[-1]:,}")

with st.expander("Edits Summary"):
  st.table(pd.concat([byday.sum(numeric_only=True), byday.tail(1).sum(numeric_only=True)], axis=1, keys=["All_Time", "Last_Day"]).astype(int))

"## Recent Daily Edits on All Wikis"
c = alt.Chart(byday.tail(30)).mark_bar().encode(
  x=alt.X("yearmonthdate(DateTime):T", title="Day"),
  y="TotalLinks:Q",
  tooltip=[alt.Tooltip("yearmonthdate(DateTime)", title="Day")] + tt
)
st.altair_chart(c, use_container_width=True)

with st.expander("Recent Daily Edits"):
  st.write(byday.tail(30))

"## Monthly Links Edits on All Wikis"
c = alt.Chart(bymonth).mark_bar().encode(
  x=alt.X("yearmonth(YearMonth):T", title="Month"),
  y="TotalLinks:Q",
  tooltip=[alt.Tooltip("yearmonth(YearMonth)", title="Month")] + tt
)
st.altair_chart(c, use_container_width=True)

with st.expander("Per Month Edits"):
  bymonth["YearMonth"] = bymonth["YearMonth"].str[:7]
  st.write(bymonth)

"## Monthly Links Edits on Selected Wikis"
selected_wikis = st.multiselect("Select Wikis to compare:", bywiki["Wiki"], default=["enwiki"])
sw = data[data["Wiki"].isin(selected_wikis)].groupby(["Wiki", "YearMonth"]).agg("sum").reset_index()
c = alt.Chart(sw).mark_line().encode(
  x=alt.X("yearmonth(YearMonth):T", title="Month"),
  y="TotalLinks:Q",
  color="Wiki:N",
  strokeDash="Wiki:N"
)
st.altair_chart(c, use_container_width=True)

"## Recent Daily Edits on Each Wiki"
recent = data[data["Timestamp"].dt.date > lday - pd.to_timedelta("30day")]
c = alt.Chart(recent).mark_rect().encode(
  x=alt.X("yearmonthdate(Timestamp):T", title="Day"),
  y="Wiki:O",
  color="TotalLinks:Q",
  tooltip=[alt.Tooltip("yearmonthdate(Timestamp)", title="Day"), "Wiki"] + tt
).properties(
  height=recent["Wiki"].nunique()*15
)
st.altair_chart(c, use_container_width=True)

"## Total Links Edits on Each Wiki"
c = alt.Chart(bywiki.sort_values(by=["TotalLinks"], ascending=False)).mark_bar().encode(
  x="TotalLinks:Q",
  y=alt.Y("Wiki:N", sort="-x"),
  tooltip=["Wiki"] + tt
).properties(
  height=len(bywiki)*15
)
st.altair_chart(c, use_container_width=True)

with st.expander("Per Wiki Edits"):
  st.write(bywiki)
