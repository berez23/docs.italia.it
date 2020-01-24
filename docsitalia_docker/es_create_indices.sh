#!/usr/bin/env sh

set -e

DOCKER_FILE=docsitalia_docker/compose/docker-compose-docsitalia.yml

echo "Creating empty ES indices"
docker-compose -f "${DOCKER_FILE}" up -d web
sleep 5
docker-compose -f "${DOCKER_FILE}" exec -T web python manage.py search_index --create
