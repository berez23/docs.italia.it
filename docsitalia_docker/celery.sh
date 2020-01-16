#!/usr/bin/env sh

set -e

docker/dirs.sh
celery worker $*
