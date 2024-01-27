#!/usr/bin/env python3

import datetime
import random
import re

import requests

import altair as alt
import streamlit as st
import pandas as pd

from openai import OpenAI


TITLE = "TARB IABot Dataset"
ICON = "https://archive.org/favicon.ico"

st.set_page_config(page_title=TITLE, page_icon=ICON, layout="wide", initial_sidebar_state="expanded")
st.title(TITLE)

GLOBAL_TBL = """
### The `externallinks_global` Table

This table contains the URL metadata for all wikis. It has the following fields.

* url_id: primary key int - a unique identifier for a distinct URL IABot has discovered on wiki
* paywall_id: indexed int - a number that allows for joining to the externallinks_paywall table
* url: indexed varchar(767) - the actual URL
* archive_url: not indexed blob - the archive URL for the URL, can be null
* has_archive: indexed tinyint - 1 if the archive URL field is populated, 0 otherwise
* live_state: indexed tinyint - condition of the URL with the following values:
  0 - dead
  1 - dying
  2 - dying
  3 - alive
  4 - no assessment
  5 - subscription - the URL can't be accessed correctly without some form of registration or subscription
  6 - permadead - permanently dead
  7 - permalive - permanently alive
* last_deadCheck: indexed timestamp - when the URL's live state was last checked
* archivable: indexed tinyint - can the URL be captured by the Wayback Machine? 1 = yes, 0 = no
* archived: indexed tinyint - does an archive URL exist?
  0 - no
  1 - yes
  2 - not answered
* archive_failure: not indexed blob - this is populated with an error message should the Wayback Machine have failed to have captured the URL
* access_time: indexed timestamp - the time the URL was last known to be accessed or added to Wikipedia
* archive_time: indexed timestamp -  the time of the archive snapshot of the archive URL, NULL if has_archive = 0
"""

PAYWALL_TBL = """
### The `externallinks_paywall` Table

This table should be joined with the `externallinks_global` table for accurate queries involving the live state of URLs or when returning URLs from a domain search query. It has the following fields.

* paywall_id: primary key int - this is a unique identifier for a distinct domain name
* domain: indexed varchar(255) - the actual domain name (e.g., "cnn.com" or "google.com")
* paywall_status: indexed tinyint - the condition of the domain
  0 - no status - the default status
  1 - permadead - the whole domain is permanently dead
  2 - permalive - the whole domain is permanently alive
"""

LANG_TBL = """
### The `externallinks_*` Tables

This is a set of tables, one for each wiki, where the wildcard `*` represents various Wiki identifiers (e.g., `enwiki` and `arwiki`). These tables can be joined with the `externallinks_global` table on the `url_id` field. These various language wiki edition tables have the same schema as described below.

* pageid - indexed bigint - a numerical article/page ID provided by the wiki
* url_id - indexed bigint - a number that allows for joining to the externallinks_global table
"""

INFO = """
This is a read-only interactive explorer of the database that powers the IABot to fix proken links.
Read the documentation below to learn more about the database schema for crafting your SQL queries.
To prevent from any abuse of the system we are currently requiring an access token to enable custom queries.
We plan to make periodic SQL dumps available for download.

Email us at info@archive.org for any questions or feedback."""

DOCS = f"""
## A Database of URLs Referenced in Wikipedia Articles

Welcome to a nearly complete and nearly up-to-date database of URLs found in the 320 Wikipedia language editions.

The schema has a fairly simple layout. There are three tables to consider:

* `externallinks_paywall` - This table name is not intuitive as it was initially proposed for tracking paywalled domains. It has since expanded to include `permaliving` entire domains, as well as `permadead`, tracking subscriptions, and tracking URLs by their domain names. Each entry is a specific domain, and is agnostic to what level said domain is in, ie `cnn.com` is different from `www.cnn.com`.
* `externallinks_global` - The primary central table the bot relies on for maintaining URL states, and metadata. It tracks URLs, the archive URL it intends to use for rescuing links, whether or not it's already checked the Wayback Machine if an archive URL exists, when the URL was supposedly accessed, or at least added to Wikipedia, and the time of any archive snapshot currently cached. All URLs on the table are distinct/unique.
* `externallinks_<wikicode>`: The `<wikicode>` is the wiki identifier, like `enwiki` for English Wikipedia. For every wiki the bot runs on, it has a table for that specific wiki. All it does is track which URLs from the `externallinks_global` table exist on a given article. All URLs per page are distinct/unique.

---

{GLOBAL_TBL}

{PAYWALL_TBL}

{LANG_TBL}

---

The database URLs are populated by parsing the wikitext on Wikimedia wikis.
URLs generated by a template are usually not included in the database.
However, if the URL generating template lies within a citation template under the URL parameter, the bot will be able to resolve the template into a URL, and absorb it.

The bot only retrieves archive URLs from the Wayback Machine, or from pre-existing archive URLs found on the wiki.
Users are also able to alter what archive URL to use for any respective URL by `https://iabot.wmcloud.org/index.php?page=manageurlsingle`.

The replication DB is maintained/updated in near real-time to the bot's production DB.
The bot maintains its database of pages and URLs as it cycles through a wiki's articles from start to finish.
On particularly large wikis, this means it can take months for a page to be visited and subsequent data to be updated.
This can be expedited by simply running the bot on-demand by visiting `https://iabot.wmcloud.org/index.php?page=runbotsingle`.

URL states update no sooner than 3 days from the last time of scan.
They are only updated if the URL is encountered in a page the bot is actively assessing.

The DB only maintains a wiki's page by its numerical ID.
To lookup the page ID, you can click on the "Page Information" link on the article.
If the classic "Vector" skin is being used, the older theme deprecated in 2022/2023, the link can be found on the left side panel under "Tools".
If using the latest skin/theme, the "Tools" is a dropdown found in the top right of the article.
"""

SAMPLES = {
  "Database table summary": (
    "A comprehensive list of tables along with their corresponding row counts and sizes in bytes.",
    """
    SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA != "information_schema";
    """
  ),
  "Dead URLs from an article": (
    "Dead URLs in the Easter Island article on the English Wikipedia.",
    """
    SELECT url
    FROM externallinks_global
    JOIN externallinks_enwiki
    ON externallinks_enwiki.url_id = externallinks_global.url_id
    WHERE live_state = 0
    AND pageid = 53418;
    """
  ),
  "Non-alive URLs and domains from an artcile": (
    "Non-alive URLs (i.e., including all dead statuses and domain-level statuses).",
    """
    SELECT url
    FROM externallinks_global
    JOIN externallinks_enwiki
    ON externallinks_enwiki.url_id = externallinks_global.url_id
    JOIN externallinks_paywall
    ON externallinks_global.paywall_id = externallinks_paywall.paywall_id
    WHERE (live_state IN (0, 6) OR paywall_status = 2)
    AND pageid = 53418;
    """
  ),
  "Total URLs count": (
    "Unique number of URLs known to the IABot from all wikis.",
    """
    SELECT COUNT(*)
    FROM externallinks_global;
    """
  ),
}

EXAMPLES = [
  "How many dead links are there on the NASA page from the Portuguese wiki?",
  "List the URLs linked from the Easter Island page."
]

SQLRE = re.compile(r"```(sql)?\s*(.*?)\s*```", re.DOTALL | re.MULTILINE)
PGIRE = re.compile(r"get_page_id\(.*?\)")
ss = st.session_state
conn = st.connection("mysql", type="sql")


def sqlq(qry, ttl=600):
  return conn.query(qry, ttl=ttl, show_spinner="Running SQL query...")


def get_page_id(title, lang="en"):
  try:
    res = requests.get(f"https://{lang}.wikipedia.org/w/api.php?action=query&format=json&titles={title.replace(' ', '%20')}").json()
    return list(res["query"]["pages"])[0]
  except:
    return None


def replacer(m):
  return id if (id := eval(m.group(0))) else "-1"


def get_sql_block(md):
  m = SQLRE.search(md)
  if not m:
    return None
  return PGIRE.sub(replacer, m.group(2))


def prompt_tempate(question):
  return f"""You are a polite assistant who is an expert in writing accurate and efficnet SQL queries.
You know about the InternetArchiveBot dataset stored in a MariaDB database with tables named "externallinks_global", "externallinks_paywall", and "externallinks_*", where the wildcard `*` represents a set of identifier of Wikimedia wikis.
An example table name would be `externallinks_enwiki`, representing the English Wikipedia, where `*` being `enwiki`.
This database is used by the InternetArchiveBot (IABot) to fix broken links on Wikimedia wikis.
The tables have numerous fields as described below in the section (between a pair of three hyphens "---").

---

{GLOBAL_TBL}

{PAYWALL_TBL}

{LANG_TBL}

---

The database also contains a stored fuction `get_page_id(title, lang)` to get the article/page ID of a given title from a specified language wiki (e.g., `get_page_id("Solar System", "en")` returns 26903).

Based on the MariaDB database description above, write a read-only SQL query to answer the following question:

{question}

NOTE:

* Convert any columns with the `blob` type to `urf8` if they are part of the final result.
* Do not assume additional fields exist if given a question that can't be answered with the above mentioned fields.
* If you need to use any of the `externallinks_*` tables for your answer and no wiki was specified in the question, you may assume the default wiki to be the English Wikipedia (i.e., `enwiki`).
* If the question is unclear or it cannot be answered using the above MariaDB table then ask for more details and describe limitations, but DO NOT attempt to produce a vague query, instead, simply explain why the query can't be answered.
"""


st.info(INFO)

with st.expander("Documentation"):
  st.markdown(DOCS)

with st.sidebar:
  mode = st.radio("Query Mode", ["Sample Queries", "Custom Query", "Query CoPilot"])

qry = ""
ttl = 0

if mode == "Sample Queries":
  smpl = st.radio("Select a sample query", SAMPLES, captions=[c[0] for c in SAMPLES.values()])
  qry = SAMPLES[smpl][1]
  ttl = 3600

if mode == "Custom Query":
  if ss.get("TOKEN") != st.secrets.get("ACCESS_TOKEN"):
    tkn = st.text_input("Access token", type="password", key="tkn", placeholder="Enter a valid access token to enable custom queries.", help="Email us at info@archive.org for an access token.")
    if tkn.strip():
      if tkn != st.secrets.get("ACCESS_TOKEN"):
        st.error("Invalid access token!")
      else:
        ss.TOKEN = tkn
        st.rerun()
    st.stop()
  qry = st.text_area("Enter a custom SQL query", value=ss.get("cq"), height=200, key="cq", placeholder="DESCRIBE externallinks_global;")

if mode == "Query CoPilot":
  client = OpenAI()
  cc = st.container(height=400, border=True)
  if "history" not in ss:
    ss["history"] = [{"role": "assistant", "content": "Ask a question about the dataset and let the AI Copilot write SQL queries for you."}]
  for msg in ss.history:
    cc.chat_message(msg["role"]).write(msg["content"])
  if prompt := st.chat_input(f"Example: {random.choice(EXAMPLES)}"):
    ss.history.append({"role": "user", "content": prompt})
    cc.chat_message("user").write(prompt)
    if prompt.startswith("/id "):
      res = "Failed to retrieve the page ID!"
      if pgid := get_page_id(prompt[4:].strip()):
        res = f"Page ID: `{pgid}`"
      cc.chat_message("assistant").write(res)
    else:
      with cc.chat_message("assistant"):
        ph = st.empty()
        res = ""
        for r in client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt_tempate(prompt)}], stream=True):
          res += (r.choices[0].delta.content or "")
          ph.write(res + "▌")
        ph.write(res)
    ss.history.append({"role": "assistant", "content": res})
    qry = get_sql_block(res)

if not qry:
  st.stop()

if mode != "Custom Query":
  st.code(qry, language="sql")

try:
  st.dataframe(sqlq(qry, ttl=ttl), use_container_width=True)
except Exception as e:
  st.error(e)
