# tests/mirror_check.sh's stand-in for the door's Husarnet sidecar (test/compose.door-check.yaml): the
# door's own image (DOOR_IMAGE, built from publish/Dockerfile, so no base of its own to keep in step)
# with socat, which holds a tun interface hnet0 the way Husarnet's daemon does: the interface goes
# when the process does, so a namespace left behind by a restarted stand-in has lost it, as with the
# real sidecar. It carries fc94:dead:beef::1234/16, an address like the door's Husarnet one (D36). It
# never contacts Husarnet and takes no join code.
ARG DOOR_IMAGE
FROM ${DOOR_IMAGE}
USER 0:0
RUN apk add --no-cache socat
ENTRYPOINT ["sh", "-c", "socat -u TUN,tun-name=hnet0,iff-up /dev/null & p=$!; for i in 1 2 3 4 5 6 7 8 9 10; do ip link show hnet0 > /dev/null 2>&1 && break; sleep 0.5; done; ip -6 addr add fc94:dead:beef::1234/16 dev hnet0; trap 'kill $p; exit 0' TERM; wait $p"]
