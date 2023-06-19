#!/bin/sh

set -e

echo "[CTFPad] Database initialization..."
while psql -h db 2>&1 | grep -q 'could not connect to server'; do
    >&2 echo "Waiting for PostgreSQL to boot up"
    sleep 1
done

echo "[CTFPad] Database setup: makemigrations..."
python3 manage.py makemigrations --noinput

echo "[CTFPad] Database setup: migrate..."
python3 manage.py migrate --noinput

exec "$@"
