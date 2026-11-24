#!/bin/sh
set -eu

: "${DATABASE_URL:?Set DATABASE_URL for the container}"
alembic upgrade head
exec "$@"
