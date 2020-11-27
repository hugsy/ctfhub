#!/bin/sh

set -e

echo "DB init..."
while psql -h db 2>&1 | grep -q 'could not connect to server'; do
  >&2 echo "Waiting for PostgreSQL to boot up"
  sleep 1
done

echo "DB setup: makemigrations..."
echo "DB setup: migrate..."
python3 manage.py makemigrations --noinput
python3 manage.py migrate --noinput

exec "$@"
