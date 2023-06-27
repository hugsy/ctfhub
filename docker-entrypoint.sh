#!/bin/sh

set -e

cd /code

echo "[CTFHub] Database initialization..."
while psql -h db 2>&1 | grep -q 'could not connect to server'; do
    >&2 echo "Waiting for PostgreSQL to boot up"
    sleep 1
done

echo "[CTFHub] Database setup: makemigrations..."
python3 manage.py makemigrations --noinput

echo "[CTFHub] Database setup: migrate..."
python3 manage.py migrate --noinput

exec "$@"
