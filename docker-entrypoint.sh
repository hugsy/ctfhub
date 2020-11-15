#!/bin/sh

set -e

# Waiting for PostgreSQL to boot up
echo "DB init..."
sleep 10

echo "DB setup: makemigrations..."
echo "DB setup: migrate..."
python3 manage.py makemigrations --noinput
python3 manage.py migrate --noinput

exec "$@"