# The publishing door's Husarnet sidecar (compose.yaml next to this file: service `husarnet`; the
# user's U75): Husarnet's own package from Husarnet's own apt repository on a current Debian slim
# base, instead of the image husarnet/husarnet (2.0.180 on Ubuntu 22.04 of 2023). Its entry point and
# healthcheck are husarnet.sh (why not the image's own: there). README.md of deploy/mirror, "The
# publishing account".
#
# What is pinned: the Debian base by tag and digest (the multi-platform index), Husarnet's signing
# key by its fingerprint (the build stops on another key), the package's version. The Debian
# packages are not pinned: a rebuild takes the newest of that Debian release (security fixes
# included). Husarnet's stable repository (install.husarnet.com, read 2026-11-19) serves 1:2.0.180 as
# its newest version, the same daemon as the image's; both of its programs are statically linked,
# so a fresh base renews the system around the daemon (bash, iproute2, procps, glibc), not the
# libraries built into it.
#
# To update (monthly, with the door's base): the newest tag of the Debian stable slim line,
# `docker buildx imagetools inspect debian:<tag>` (the "Digest:" line), change DEBIAN_IMAGE; look at
# the repository's newest version (its Packages list) and change HUSARNET_VERSION only after
# checking husarnet.sh's reasons against that version's sources; then
# `docker compose build --pull husarnet` and tests/mirror_check.sh.
ARG DEBIAN_IMAGE=debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
ARG HUSARNET_VERSION=1:2.0.180
ARG HUSARNET_KEY_FINGERPRINT=87D016FBEC48A791AA4AF675197D62F68A4C7BD6

# Husarnet's signing key, fetched and checked by its fingerprint in a stage of its own (gnupg and
# curl stay out of the sidecar's image)
FROM ${DEBIAN_IMAGE} AS key
ARG HUSARNET_KEY_FINGERPRINT
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL --proto '=https' -o /husarnet.gpg https://install.husarnet.com/repo.gpg \
    && fingerprints=$(gpg --show-keys --with-colons /husarnet.gpg | awk -F: '$1 == "pub" { want = 1 } $1 == "fpr" && want { print $10; want = 0 }') \
    && if [ "$fingerprints" != "$HUSARNET_KEY_FINGERPRINT" ]; then \
           echo "Husarnet's key file holds [$fingerprints], not $HUSARNET_KEY_FINGERPRINT: stop" >&2; exit 1; \
       fi

FROM ${DEBIAN_IMAGE}
ARG HUSARNET_VERSION
COPY --from=key /husarnet.gpg /usr/share/keyrings/husarnet.gpg
# The package without its Recommends (sudo, systemd, an emoji font); its postinst installs a systemd
# service only where systemd runs, so nothing here
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && echo "deb [signed-by=/usr/share/keyrings/husarnet.gpg] https://install.husarnet.com/deb/ all husarnet" \
        > /etc/apt/sources.list.d/husarnet.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "husarnet=${HUSARNET_VERSION}" \
    && rm -rf /var/lib/apt/lists/*
COPY --chmod=0755 husarnet.sh /usr/local/bin/husarnet.sh

ENTRYPOINT ["/usr/local/bin/husarnet.sh", "start"]
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --start-interval=2s --retries=3 \
    CMD ["/usr/local/bin/husarnet.sh", "health"]
