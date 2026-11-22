#!/bin/sh
# Entry point of the stand-in for SWAG (compose.test.yaml): turns the mirror's SWAG conf into a
# plain-HTTP server on port 8080 that answers any host name, with this folder's copies of SWAG's
# proxy.conf and resolver.conf, then starts nginx. Every other line of the conf is used as it is,
# so the stand-in refuses methods and bodies, and keeps no access log, exactly as SWAG would.
set -eu
SWAG_CONF=/etc/standin/findaline-mirror.subdomain.conf
mkdir -p /tmp/standin
echo "resolver 127.0.0.11 valid=30s;" > /tmp/standin/resolver.conf
sed -e '/^[[:space:]]*#/d' \
    -e 's/^\([[:space:]]*\)listen 443 ssl;/\1listen 8080 default_server;/' \
    -e '/listen \[::\]:443 ssl;/d' \
    -e '/include \/config\/nginx\/ssl\.conf;/d' \
    -e 's/^\([[:space:]]*\)server_name [^;]*;/\1server_name _;/' \
    -e 's#/config/nginx/proxy\.conf#/etc/standin/swag-proxy.conf#' \
    -e 's#/config/nginx/resolver\.conf#/tmp/standin/resolver.conf#' \
    -e 's#/config/log/nginx/error\.log#/dev/stderr#' \
    "$SWAG_CONF" > /tmp/standin/site.conf
if grep -q '/config/' /tmp/standin/site.conf; then
    echo "standin: a /config/ path of SWAG is left in the conf:" >&2
    grep -n '/config/' /tmp/standin/site.conf >&2
    exit 1
fi
grep -q 'listen 8080 default_server;' /tmp/standin/site.conf || { echo "standin: no listen line turned" >&2; exit 1; }
exec nginx -c /etc/standin/standin.conf -g 'daemon off;'
