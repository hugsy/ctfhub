# https://hub.docker.com/_/python?tab=description
FROM python:3.9-buster

ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV DEBUG 1
ENV CODIMD_URL http://codimd:3000
RUN mkdir /code
WORKDIR /code
COPY requirements.txt .

RUN \
 apt-get update && \
 apt-get upgrade -y && \
 apt-get install -y libpq-dev python3-dev && \
 python3 -m pip install --upgrade pip && \
 python3 -m pip install -r requirements.txt --no-cache-dir && \
 apt-get autoclean && \
 apt-get autoremove


COPY . .
RUN chmod +x /code/docker-entrypoint.sh

# CMD ["python3", "manage.py", "runserver"]
ENTRYPOINT ["/code/docker-entrypoint.sh"]
