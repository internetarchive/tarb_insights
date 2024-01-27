#!/usr/bin/env python3

import datetime
import requests

import altair as alt
import streamlit as st
import pandas as pd


TITLE = "TARB Insights"
ICON = "https://archive.org/favicon.ico"
STATSAPI = "https://iabot.wmcloud.org/api.php?action=statistics&format=flat&only-year={}"
STRYEAR = 2016
ENDYEAR = datetime.date.today().year

st.set_page_config(page_title=TITLE, page_icon=ICON, layout="wide", initial_sidebar_state="collapsed")
st.title(TITLE)

def load_yearly_data(year):
  df =  pd.DataFrame(requests.get(STATSAPI.format(year)).json()["statistics"])
  df["DateTime"] = df["Timestamp"].str[:10] + "T12:00:00Z"
  df["YearMonth"] = df["Timestamp"].str[:8] + "15"
  df["Timestamp"] = pd.to_datetime(df["Timestamp"])
  return df

@st.cache_data(show_spinner=False)
def cached_yearly_data(year):
  return load_yearly_data(year)

@st.cache_data(ttl=3600, max_entries=1)
def load_data():
  return pd.concat([cached_yearly_data(y) for y in range(STRYEAR, ENDYEAR)] + [load_yearly_data(ENDYEAR)])

try:
  all_data = load_data()
except Exception as e:
  st.error(f"Problem accessing stats from: {STATSAPI}")
  st.exception(e)
  st.stop()

fday = all_data["Timestamp"].dt.date.min()
lday = all_data["Timestamp"].dt.date.max()

qp = st.query_params
sday = datetime.datetime.strptime(qp.start, "%Y-%m-%d").date() if "start" in qp else fday
eday = datetime.datetime.strptime(qp.end, "%Y-%m-%d").date() if "end" in qp else lday

dayrange = st.slider("Date Range", min_value=fday, max_value=lday, value=(sday, eday), key="range")

qp.start=dayrange[0]
qp.end=dayrange[1]

try:
  data = all_data.loc[(all_data["Timestamp"] >= pd.Timestamp(dayrange[0])) & (all_data["Timestamp"] <= pd.Timestamp(dayrange[1]))]
except IndexError as e:
  st.warning(f"Select a valid date range between {fday} and {lday}")
  st.stop()

data.columns = [c.replace(" ", "_") for c in data.columns]
bywiki = data.groupby(["Wiki"]).agg("sum", numeric_only=True).reset_index()
bymonth = data.groupby(["YearMonth"]).agg("sum", numeric_only=True).reset_index()
byday = data.groupby(["DateTime"]).agg("sum", numeric_only=True).reset_index()
daily_wikis = data.groupby(["DateTime"]).agg("count")["Wiki"]

tt = [alt.Tooltip(f, format=",") for f in ["TotalLinks", "TotalEdits", "DeadLinks", "DeadEdits", "LiveLinks", "TagLinks", "ProactiveEdits", "ReactiveEdits", "UnknownEdits"]]

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


TABS = ["TotalLinks", "TotalEdits", "DeadLinks", "DeadEdits", "Data"]


"## Recent Daily Edits on All Wikis"

def recent_daily_edits_all_wikis(attr):
  return alt.Chart(byday.tail(30)).mark_bar().encode(
    x=alt.X("yearmonthdate(DateTime):T", title="Day"),
    y=f"{attr}:Q",
    tooltip=[alt.Tooltip("yearmonthdate(DateTime)", title="Day")] + tt
  )

tbs = st.tabs(TABS)
for i, f in enumerate(TABS[:-1]):
  tbs[i].altair_chart(recent_daily_edits_all_wikis(f), use_container_width=True)
tbs[len(TABS)-1].write(byday.tail(30))


"## Monthly Links Edits on All Wikis"

def monthly_edits_all_wikis(attr):
  return alt.Chart(bymonth).mark_bar().encode(
    x=alt.X("yearmonth(YearMonth):T", title="Month"),
    y=f"{attr}:Q",
    tooltip=[alt.Tooltip("yearmonth(YearMonth)", title="Month")] + tt
  )

tbs = st.tabs(TABS)
for i, f in enumerate(TABS[:-1]):
  tbs[i].altair_chart(monthly_edits_all_wikis(f), use_container_width=True)
bymonth["YearMonth"] = bymonth["YearMonth"].str[:7]
tbs[len(TABS)-1].write(bymonth)


"## Monthly Links Edits on Selected Wikis"

selected_wikis = st.multiselect("Select Wikis to compare:", bywiki["Wiki"], default=["enwiki"])
sw = data[data["Wiki"].isin(selected_wikis)].groupby(["Wiki", "YearMonth"]).agg("sum", numeric_only=True).reset_index()

def monthly_edits_selected_wikis(attr):
  return alt.Chart(sw).mark_line().encode(
    x=alt.X("yearmonth(YearMonth):T", title="Month"),
    y=f"{attr}:Q",
    color="Wiki:N",
    strokeDash="Wiki:N"
  )

tbs = st.tabs(TABS)
for i, f in enumerate(TABS[:-1]):
  tbs[i].altair_chart(monthly_edits_selected_wikis(f), use_container_width=True)
tbs[len(TABS)-1].write(sw)


"## Recent Daily Edits on Each Wiki"

recent = data[data["Timestamp"].dt.date > lday - pd.to_timedelta("30day")]

def recent_daily_edits_each_wiki(attr):
  return alt.Chart(recent).mark_rect().encode(
    x=alt.X("yearmonthdate(DateTime):T", title="Day"),
    y="Wiki:O",
    color=alt.Color(f"{attr}:Q", scale=alt.Scale(type="symlog")),
    tooltip=[alt.Tooltip("yearmonthdate(DateTime)", title="Day"), "Wiki"] + tt
  ).properties(
    height=recent["Wiki"].nunique()*21
  )

tbs = st.tabs(TABS)
for i, f in enumerate(TABS[:-1]):
  tbs[i].altair_chart(recent_daily_edits_each_wiki(f), use_container_width=True)
tbs[len(TABS)-1].write(recent)


"## Total Links Edits on Each Wiki"

def total_edits_each_wiki(attr):
  return alt.Chart(bywiki.sort_values(by=[attr], ascending=False)).mark_bar().encode(
    x=f"{attr}:Q",
    y=alt.Y("Wiki:N", sort="-x"),
    tooltip=["Wiki"] + tt
  ).properties(
    height=len(bywiki)*21
  )

tbs = st.tabs(TABS)
for i, f in enumerate(TABS[:-1]):
  tbs[i].altair_chart(total_edits_each_wiki(f), use_container_width=True)
tbs[len(TABS)-1].write(bywiki)
