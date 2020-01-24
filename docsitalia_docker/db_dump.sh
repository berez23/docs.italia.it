#!/usr/bin/env sh

set -e

DB_CONTAINER=db
DB_NAME=rtd
DB_USER=docs
DOCKER_FILE=docsitalia_docker/compose/docker-compose-docsitalia.yml

if [ $# != 1 ]; then
  echo "Destination dump file required"
  exit 1
fi

echo "Dumping database to '$1'"
docker-compose -f "${DOCKER_FILE}" up -d "${DB_CONTAINER}"
sleep 5
docker-compose -f "${DOCKER_FILE}" exec -T "${DB_CONTAINER}" pg_dump -U "${DB_USER}" -Ox "${DB_NAME}" > $1
