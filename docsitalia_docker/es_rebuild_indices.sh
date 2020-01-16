#!/usr/bin/env sh

set -e

echo "\n========\nRecreating ES indices and reindexing the content\n========\n"
docker-compose up -d web celery-web
sleep 5
docker-compose exec -T web python manage.py search_index --rebuild
