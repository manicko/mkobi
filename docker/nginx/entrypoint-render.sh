#!/bin/sh
# Render the edge configuration before nginx starts.
#
# The mounted /etc/nginx/nginx.conf is a template, not the final config: it
# carries ${NGINX_CLIENT_MAX_BODY_SIZE} so the upload byte ceiling resolves from
# the environment at container start. The rendered result replaces the main
# config (/etc/nginx/nginx.conf), and the stock image's own entrypoint is then
# handed control with the original arguments.
set -eu

TEMPLATE=/etc/nginx/nginx.conf.template
RENDERED=/etc/nginx/nginx.conf

envsubst '${NGINX_CLIENT_MAX_BODY_SIZE}' < "$TEMPLATE" > "$RENDERED"

exec /docker-entrypoint.sh "$@"
