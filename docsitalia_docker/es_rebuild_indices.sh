#!/usr/bin/env sh

set -e

DOCKER_FILE=docsitalia_docker/compose/docker-compose-docsitalia.yml

echo "\n========\nRecreating ES indices and reindexing the content\n========\n"
docker-compose -f "${DOCKER_FILE}" up -d web celery-web
sleep 5
docker-compose -f "${DOCKER_FILE}" exec -T web python manage.py search_index --rebuild
