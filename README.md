# TARB Insights

This is a [Streamlit](https://streamlit.io/) application to visualize [Wikipedia InternetArchiveBot](https://meta.wikimedia.org/wiki/InternetArchiveBot/API#action=statistics) and [Turn All References Blue (TARB)](https://archive.org/details/mark-graham-presentation) project statistics.

To run it locally (in Docker), clone this repository and build a docker image:

```
$ docker image build -t tarbinsights .
```

Run a container from the freshly built Docker image:

```
$ docker container run --rm -it -p 8501:8501 tarbinsights
```

Access http://localhost:8501/ in a web browser for interactive insights.
