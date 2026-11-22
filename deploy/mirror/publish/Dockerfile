# The mirror's publishing door (docs/mirror-hosting/spec.md, S17; README.md of deploy/mirror, "The
# publishing account"): OpenSSH on Alpine, one account `publish` (uid 1000), key only, and a
# command gate (gate.sh): the key can run the SFTP server and sha256sum of a file under /mirror,
# nothing else. compose.yaml next to this file builds and runs it (read-only root, uid 1000).
#
# The base image is pinned by tag and digest (the digest of the multi-platform index); the
# packages are not pinned: a build takes the newest openssh of that Alpine branch (security fixes
# included), so two builds on one digest may differ. To update (monthly, with the file server's
# base): pick the newest tag of the Alpine branch, `docker buildx imagetools inspect alpine:<tag>`
# (the "Digest:" line), change the ARG, then `docker compose build --pull` and
# tests/mirror_check.sh.
ARG ALPINE_IMAGE=alpine:3.24.4@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf

FROM ${ALPINE_IMAGE}

# The account: uid and gid 1000, in group 101 too (the file server's group, which owns
# <root>/logs) so that it reads the request log; "*" in its password field: no password, but not
# locked, so sshd lets it log in with its key. No host key in the image: the host's, mounted.
RUN apk add --no-cache openssh-server openssh-sftp-server \
    && addgroup -g 1000 publish \
    && addgroup -g 101 mirror \
    && adduser -D -H -u 1000 -G publish -h /mirror -s /bin/sh publish \
    && addgroup publish mirror \
    && sed -i 's/^publish:!/publish:*/' /etc/shadow \
    && rm -f /etc/ssh/ssh_host_* /etc/motd \
    && install -d -m 0755 /keys /keys/host /mirror

COPY --chmod=0644 sshd_config /etc/ssh/sshd_config
COPY --chmod=0755 gate.sh /usr/local/bin/gate

USER 1000:1000
EXPOSE 2222
ENTRYPOINT ["/usr/sbin/sshd", "-D", "-e", "-f", "/etc/ssh/sshd_config"]
