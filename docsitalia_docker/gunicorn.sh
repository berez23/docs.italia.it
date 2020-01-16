#!/usr/bin/env sh

set -e

docker/dirs.sh
if [ "$1" = "collect" ]; then
  cp -a media /home/documents/
  python manage.py collectstatic --no-input -c
  python manage.py migrate
fi
gunicorn --error-logfile="-" --timeout=3000  readthedocs.wsgi:application $*
