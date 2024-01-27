#!/usr/bin/env -S docker image build -t tarbinsights . -f

FROM python:3

ENV     STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN     pip install \
          mysqlclient \
          openai \
          pandas \
          requests \
          streamlit \
          SQLAlchemy

COPY    . ./

CMD      ["streamlit", "run", "main.py"]
