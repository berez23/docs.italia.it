#!/usr/bin/env sh

set -e

DB_CONTAINER=db
DB_NAME=rtd
DB_USER=docs

if [ $# != 1 ]; then
  echo "Database dump file (.sql, .bz2, .gz) required"
  exit 1
fi

echo "Restoring database from '$1'"
docker-compose up -d "${DB_CONTAINER}"
sleep 10
docker-compose exec -T "${DB_CONTAINER}" dropdb -U "${DB_USER}" "${DB_NAME}" --if-exists
docker-compose exec -T "${DB_CONTAINER}" createdb -U "${DB_USER}" -O "${DB_USER}" "${DB_NAME}"
ext=${1##*\.}
case "$ext" in
sql) docker-compose exec -T "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}" < "${1}"
;;
bz2) bzip2 -cd $1 | docker-compose exec -T "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}"
;;
gz) gzip -cd $1 | docker-compose exec -T "${DB_CONTAINER}" psql -U "${DB_USER}" -d "${DB_NAME}"
;;
*) echo " $1 : Database dump file extension not valid. Valid extensions: .sql, .bz2, .gz"
;;
esac
