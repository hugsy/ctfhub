#!/bin/sh

set -e

echo "DB init..."
until psql -h db -U root -c '\l' &>/dev/null; do
  >&2 echo "Waiting for PostgreSQL to boot up"
  sleep 1
done

echo "DB setup: makemigrations..."
echo "DB setup: migrate..."
python3 manage.py makemigrations --noinput
python3 manage.py migrate --noinput
