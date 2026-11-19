# The publishing door's Husarnet sidecar (compose.yaml next to this file: service `husarnet`; the
# user's U75, U80): Husarnet's own package from Husarnet's own NIGHTLY apt repository on a current
# Debian slim base. Its entry point and healthcheck are husarnet.sh. README.md of deploy/mirror, "The
# publishing account".
#
# Why the nightly: Husarnet 3.0 moved its control plane to a new protocol (2025-12-08); its daemon is
# so far only the nightly line (nightly.husarnet.com), not a release. The stable repository
# (install.husarnet.com) still serves 2.0.180 of October 2023, which works through a compatibility
# layer Husarnet means to shut down. HUSARNET_VERSION 1:2.0.349 is the nightly of 2026-11-14 (read
# 2026-11-19). Both programs of the package are statically linked.
#
# What is pinned: the Debian base by tag and digest (the multi-platform index), Husarnet's signing
# key by its fingerprint (the build stops on another key; the stable and the nightly repository use
# the same key), the package's version. The Debian packages are not pinned: a rebuild takes the
# newest of that Debian release (security fixes included). jq is for husarnet.sh (the daemon's JSON).
#
# To update (monthly, with the door's base): the newest tag of the Debian stable slim line,
# `docker buildx imagetools inspect debian:<tag>` (the "Digest:" line), change DEBIAN_IMAGE; look at
# the nightly repository's newest version (its Packages list) and change HUSARNET_VERSION only after
# checking husarnet.sh's reasons against that version's sources (a nightly may change them); then
# `docker compose build --pull husarnet` and tests/mirror_check.sh.
ARG DEBIAN_IMAGE=debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
ARG HUSARNET_VERSION=1:2.0.349
ARG HUSARNET_KEY_FINGERPRINT=87D016FBEC48A791AA4AF675197D62F68A4C7BD6

# Husarnet's signing key, fetched and checked by its fingerprint in a stage of its own (gnupg and
# curl stay out of the sidecar's image)
FROM ${DEBIAN_IMAGE} AS key
ARG HUSARNET_KEY_FINGERPRINT
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL --proto '=https' -o /husarnet.gpg https://nightly.husarnet.com/repo.gpg \
    && fingerprints=$(gpg --show-keys --with-colons /husarnet.gpg | awk -F: '$1 == "pub" { want = 1 } $1 == "fpr" && want { print $10; want = 0 }') \
    && if [ "$fingerprints" != "$HUSARNET_KEY_FINGERPRINT" ]; then \
           echo "Husarnet's key file holds [$fingerprints], not $HUSARNET_KEY_FINGERPRINT: stop" >&2; exit 1; \
       fi

FROM ${DEBIAN_IMAGE}
ARG HUSARNET_VERSION
COPY --from=key /husarnet.gpg /usr/share/keyrings/husarnet.gpg
# The package without its Recommends (sudo, systemd, an emoji font); its postinst adds a group
# `husarnet`, makes /var/lib/husarnet (hidden by the state folder's bind) and installs a systemd
# service only where systemd runs, so not here
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && echo "deb [signed-by=/usr/share/keyrings/husarnet.gpg] https://nightly.husarnet.com/deb/ all husarnet" \
        > /etc/apt/sources.list.d/husarnet.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "husarnet=${HUSARNET_VERSION}" jq \
    && rm -rf /var/lib/apt/lists/*
COPY --chmod=0755 husarnet.sh /usr/local/bin/husarnet.sh

ENTRYPOINT ["/usr/local/bin/husarnet.sh", "start"]
HEALTHCHECK --interval=60s --timeout=10s --start-period=120s --start-interval=2s --retries=3 \
    CMD ["/usr/local/bin/husarnet.sh", "health"]
