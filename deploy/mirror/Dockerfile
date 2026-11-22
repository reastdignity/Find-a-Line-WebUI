# Find-a-Line's data server ("the mirror", docs/mirror-hosting/spec.md, section 4): nginx in its
# unprivileged image with the mirror's config, landing page, robots.txt and start script copied
# in. compose.yaml next to this file builds and runs it (read-only root, /tmp a tmpfs).
#
# The base image is pinned by tag and digest (the digest of the multi-platform index): a pinned
# image gets no automatic updates, and compose tools that check for updates skip it. To update it
# (a monthly item): pick the newest tag of the stable Alpine line
# (https://hub.docker.com/r/nginx/nginx-unprivileged/tags, e.g. 1.30.<n>-alpine3.<m>), look up its
# digest with
#   docker buildx imagetools inspect nginx/nginx-unprivileged:<tag>
# (the "Digest:" line), change the ARG below, then `docker compose build --pull` and
# tests/mirror_check.sh (the job `mirror` of .github/workflows/mirror.yml); README.md, "Updating".
ARG NGINX_IMAGE=nginx/nginx-unprivileged:1.30.7-alpine3.24@sha256:0c53a1f2890c3526bfd201440f0fd3970e5b78f80630f58284aad0d34b5ec7bd

FROM ${NGINX_IMAGE}

USER root
# The mount points: <root>/public (read-only) and <root>/logs (written by uid 101). The image's
# own server config and entry scripts are not used.
RUN install -d -o 101 -g 101 -m 0755 /var/log/mirror \
    && install -d -m 0755 /srv/public /usr/share/findaline-mirror \
    && rm -f /etc/nginx/conf.d/default.conf

COPY --chmod=0644 nginx.conf /etc/nginx/nginx.conf
COPY --chmod=0644 robots.txt /usr/share/findaline-mirror/robots.txt
COPY --chmod=0644 landing/index.html /usr/share/findaline-mirror/index.html.in
COPY --chmod=0755 start.sh /usr/local/bin/mirror-start

# The log's file names and the cleanup use the container's day: UTC
ENV TZ=UTC
USER 101
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/mirror-start"]
CMD ["serve"]
