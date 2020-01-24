#!/usr/bin/env sh

set -e

docsitalia_docker/dirs.sh
celery worker $*
