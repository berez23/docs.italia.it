#!/usr/bin/env sh

set -e

DB_CONTAINER=db
DB_NAME=rtd
DB_USER=docs

if [ $# != 1 ]; then
  echo "Destination dump file required"
  exit 1
fi

echo "Dumping database to '$1'"
docker-compose up -d "${DB_CONTAINER}"
sleep 5
docker-compose exec -T "${DB_CONTAINER}" pg_dump -U "${DB_USER}" -Ox "${DB_NAME}" > $1
