# tests/mirror_check.sh's SSH client for the publishing door's checks: the door's own pinned
# Alpine with openssh-client (ssh, sftp, ssh-keygen, ssh-keyscan). Test only, never deployed.
ARG ALPINE_IMAGE=alpine:3.24.4@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf
FROM ${ALPINE_IMAGE}
RUN apk add --no-cache openssh-client
ENTRYPOINT ["sleep", "86400"]
