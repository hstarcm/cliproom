#!/bin/sh
# Derive the nginx request-body bound from the api's global upload cap:
#   NGINX_MAX_BODY_SIZE (explicit override)  ->  use as-is
#   otherwise                                ->  MAX_FILE_MB + 6 MB margin
# (margin covers multipart encoding overhead above the raw file size)
set -e
if [ -n "${NGINX_MAX_BODY_SIZE}" ]; then
  NGINX_CLIENT_MAX_BODY_SIZE="${NGINX_MAX_BODY_SIZE}"
else
  NGINX_CLIENT_MAX_BODY_SIZE=$(( ${MAX_FILE_MB:-10} + 6 ))m
fi
export NGINX_CLIENT_MAX_BODY_SIZE
exec /docker-entrypoint.sh nginx -g "daemon off;"
