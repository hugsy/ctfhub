# https://hub.docker.com/_/python?tab=description
FROM python:3.10-buster

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV DEBUG 0

RUN \
    apt-get update && apt-get upgrade -y && \
    apt-get install -y libpq-dev python3-dev postgresql-client && \
    apt-get autoclean && apt-get autoremove

WORKDIR /code

COPY requirements.txt .
RUN \
    python3 -m pip install --upgrade pip && \
    python3 -m pip install -r requirements.txt --no-cache-dir

ENTRYPOINT ["bash", "/code/docker-entrypoint.sh"]
