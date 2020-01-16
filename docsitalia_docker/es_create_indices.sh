#!/usr/bin/env sh

set -e

echo "Creating empty ES indices"
docker-compose up -d web
sleep 5
docker-compose exec -T web python manage.py search_index --create
