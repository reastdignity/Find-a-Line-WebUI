# The mirror: Find-a-Line's data server

A static file server for the elevation tiles that Find-a-Line installations cannot read from their owner on
demand (docs/mirror-hosting/spec.md, section 4). It runs on a home server or NAS behind an existing reverse proxy
(SWAG, linuxserver/swag), as a Docker Compose project of its own: `findaline-mirror`, one service `files`
(nginx in its unprivileged image, pinned by digest). It publishes no port; SWAG is the only way in.

```
PC: tools/mirror_publish.py + rclone ──▶ <root>/staging ──▶ <root>/public (served, read-only)
                                                            <root>/logs   (the request log, 14 days)
container findaline-mirror-files-1 ── network findaline-mirror_mirror (internal) ── SWAG ── https://mirror.findaline.lukawski.org
```

What the server does, in short:
- serves `/`, `/robots.txt`, `/v1/datasets.json` and the tiles, indexes and cards under `/v1/tiles/` (exactly
  these names; everything else, folders, dot-files, `.part` files, symlinks, `/v1/cubes/`, `/v1/cache/`: 404; a
  query string 400; methods other than GET and HEAD 405; several byte ranges in one request 416);
- limits every visitor's address: 4 MB/s per request, 4 requests at once, 20 requests a second (a burst of 40),
  and all visitors together to 8 requests at once; the site's server (`MIRROR_TRUSTED_ADDRESSES`) gets 16 MB/s,
  4 at once for the whole class, outside the visitors' total, no request rate. Every answer counts against an
  address's request rate, refusals and 404s too. A refusal by a limit is a 429 with `Retry-After: 10`. The limits
  count addresses one by one: an IPv6 visitor would be counted per single address (a /64 holds very many), so the
  name has no AAAA record and SWAG does not listen on IPv6 for it;
- writes one line per request into `<root>/logs/access-YYYY-MM-DD.log` (UTC days) and deletes each file 14 or
  more days old, every hour.

The limits are constants of `nginx.conf`, not settings. `tests/mirror_check.sh` checks every behaviour.

## Requirements

- Docker with Compose v2 (`docker compose`). The steps below are plain `docker compose` commands; on a platform
  that runs compose projects through a plugin (Unraid with a compose plugin, for example), register this folder
  as the project and use the plugin's buttons for the same steps.
- SWAG already running, with a certificate it renews (HTTP or DNS validation).
- **Storage** for `<root>`: `public/`, `staging/`, `trash/` and `logs/` on **one file system** (the publish tool
  moves datasets by renaming, which must be atomic), on a path that does **not pass a FUSE layer** (a user-share
  path of some NAS systems does; use the pool's or the disk's own path), on storage that **never spins down**
  (the client's start check allows 30 s for the first answer). Room for the datasets plus 10 GB (the publish tool
  checks it).
- A DNS A record for `mirror.findaline.lukawski.org` pointing at the home address (no AAAA record: the limits
  count IPv4 addresses).

## Install

1. Copy this folder (`deploy/mirror/`) to the server, e.g. next to its other compose projects.
2. Make the folders. `logs/` must belong to uid 101 (the server's user); if Docker made it, it would belong to
   root and the server could not write its log. The compose file refuses to create missing folders.
   ```sh
   ROOT=/path/to/findaline-mirror        # the same as MIRROR_ROOT below
   install -d -m 0755 "$ROOT" "$ROOT/public" "$ROOT/staging" "$ROOT/trash"
   install -d -o 101 -g 101 -m 0750 "$ROOT/logs"
   ```
   The files under `public/` must be readable by uid 101 (world-readable, as the publishing door writes them).
   `staging/`, `public/` and `trash/` are then given to the publishing account (uid 1000), which reads `logs/`
   through group 101: "The publishing account" below. Use binds of these host folders, as `compose.yaml` does:
   a named volume (or a volume's subpath) given to the file server instead gets the image's folder at the first
   start, with its owner and mode (`/srv/public` root, 0755), and the first publish then stops at its move with
   a refused folder; such a volume needs its owners set again after that first start.
3. Settings: `cp .env.example .env`, then set `MIRROR_ROOT`, `MIRROR_CONTACT` (the contact for abuse and
   takedown requests, shown on the landing page), `MIRROR_TRUSTED_ADDRESSES` (the site server's IPv4 address;
   at most four single addresses, or empty), and `MIRROR_SUBNET` only if `172.29.42.0/24` collides with another
   Docker network of the machine (`docker network inspect $(docker network ls -q) --format '{{.Name}}
   {{range .IPAM.Config}}{{.Subnet}}{{end}}'`). The start script refuses a network, a fifth address or anything
   else in `MIRROR_TRUSTED_ADDRESSES`, an empty contact and an odd subnet: `docker compose logs files` says why.
4. Start it (the image is built here, from this folder; a compose tool that pulls but does not build needs
   `docker compose build` first):
   ```sh
   docker compose up -d --build --wait
   docker compose ps            # files: running (healthy)
   ```
   On a kernel without swap accounting compose warns "Your kernel does not support swap limit capabilities or the
   cgroup is not mounted. Memory limited without swap.": no fault; `MIRROR_MEMORY` then limits the memory alone.
5. Attach SWAG to the project's network (next section), copy the SWAG conf, add the host name to SWAG's
   certificate (the section after), and check from outside (`tests/mirror_check.sh --live`, "Checks").
6. The publishing door ("The publishing account").

## SWAG

SWAG reaches the mirror over the project's own network, `findaline-mirror_mirror`, which is `internal` (no route
out of the host): SWAG joins it as its second network, so the mirror's only neighbour is SWAG. The mirror
believes the visitor's address (`X-Real-IP`, which SWAG's `proxy.conf` sets) from any sender on this network:
**attach nothing else to it**.

The default way attaches the **running** SWAG container to that network with one command. It needs no alias:
SWAG's conf reaches the mirror by the mirror's own alias on that network, `findaline-mirror-files`.
```sh
docker network connect findaline-mirror_mirror swag          # "swag": SWAG's container name
cp swag/findaline-mirror.subdomain.conf /path/to/swag/config/nginx/proxy-confs/
docker restart swag                                           # or SWAG_AUTORELOAD
```
If `docker network connect` answers `endpoint with name swag already exists in network findaline-mirror_mirror`
(exit 1), SWAG is already attached: nothing to do. Whether it is attached is told by the check line of
"Checking it" below, not by that command's exit code.
The attachment lasts until SWAG's container is recreated (an image update recreates it): **run the
`docker network connect` again after every update of SWAG**, or let a scheduled job of the host do it (end of
this section; the same "already exists" answer means the
recreation kept it), and check it (below). This way does not stop SWAG when the mirror is away: the conf names
the mirror through a variable and SWAG's resolver, so SWAG starts and serves its other sites whether the mirror is
there or not (tried with the test stack's stand-in: taken off the mirror's network and restarted, it started and
answered the mirror's name with 502). **One case does stop it:** a container attached by `docker network connect`
that is stopped while that network is removed (the mirror's `docker compose down` while SWAG is stopped, e.g.
during SWAG's update) refuses to start ("failed to set up container networking: network ... not found"), and
re-creating the network does not help (it gets a new id). Then
`docker network disconnect -f findaline-mirror_mirror swag` and `docker start swag` start it again (then attach it
anew). So: **disconnect SWAG (`docker network disconnect findaline-mirror_mirror swag`) before taking the mirror's
project down.** (Seen with a stand-in container on Docker 29.)

**SWAG's resolver.** SWAG writes `/config/nginx/resolver.conf` only at its first start, from the container's
`/etc/resolv.conf` of that moment. A SWAG first started on Docker's default bridge network names an outside DNS
server there, which cannot resolve `findaline-mirror-files`: the mirror then answers 502 through SWAG, while
`docker exec swag curl http://findaline-mirror-files:8080/...` passes (curl uses the system resolver, which is
Docker's 127.0.0.11 once SWAG is attached). Check the file; if it does not name `127.0.0.11`, make it hold only
that line, `resolver 127.0.0.11 valid=30s;` (only that one: nginx asks its resolvers in turn), and restart SWAG:
```sh
docker exec swag cat /config/nginx/resolver.conf          # must name 127.0.0.11
```
Do so only while SWAG is attached to a user-defined network (127.0.0.11 exists only there). The default way above
loses that attachment at every update of SWAG until `docker network connect` is run again; in that window
127.0.0.11 does not exist in SWAG, so every site whose upstream is a host name set through a variable (resolved
by nginx at request time, as SWAG's sample confs do) answers 502, not only the mirror; upstreams written as IP
addresses, or names in a plain `proxy_pass`, are unaffected. So run the `docker network connect` right after
every update of SWAG, or let the scheduled job do it. (Not tried with the test stack.)

`swag/findaline-mirror.subdomain.conf` answers `mirror.findaline.lukawski.org`, passes requests on with SWAG's
own `proxy.conf`, refuses every method but GET and HEAD and any body over 1 KB itself (405 and 413, never 403,
which fail2ban's jails count), writes no access log for this host and only critical lines to the error log (both
would hold the tile's path and the visitor's address). It sets no `proxy_ignore_headers` and no `proxy_buffering`:
the mirror sends `X-Accel-Buffering: no`, without which SWAG would take a whole file into its temporary files at
once and the mirror's connection caps would count nothing. Keep it so when editing SWAG's configuration.

**Checking it** (after every update of SWAG, and whenever the mirror does not answer):
```sh
docker inspect swag --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' \
  | grep -q findaline-mirror_mirror && echo attached || echo "NOT ATTACHED: run docker network connect again"
docker exec swag curl -s -o /dev/null -w '%{http_code}\n' http://findaline-mirror-files:8080/robots.txt   # 200
docker exec swag curl -sk -o /dev/null -w '%{http_code}\n' --resolve mirror.findaline.lukawski.org:443:127.0.0.1 https://mirror.findaline.lukawski.org/robots.txt   # 200: through SWAG's nginx
```
The second line goes to the mirror directly and uses the container's system resolver, so it passes even when
SWAG's own nginx cannot resolve the mirror (its resolver above); the third goes through SWAG's nginx, as a visitor's
request does.
While SWAG is not attached, a visitor of `https://mirror.findaline.lukawski.org` gets 502 from SWAG: the mirror is
unreachable (an outage, never an exposure: nothing of the mirror is reachable any other way), and SWAG's other
sites are untouched.

**The other way: the network in SWAG's own compose file.** Where SWAG runs from a compose file, the mirror's
network can be named there as an external network, so every recreation of SWAG attaches it by itself:
```yaml
services:
  swag:
    networks: [default, findaline-mirror]
networks:
  findaline-mirror:
    external: true
    name: findaline-mirror_mirror
```
Its risk: **SWAG, and every site behind it, cannot start while that network is missing**, for instance after the
mirror's project was taken down (`docker compose down` removes the network) or before it was first started. Where
SWAG runs from a platform's container template on Docker's default `bridge`, the template cannot add the mirror's
network on some Docker releases: the default bridge and a user-defined network together are refused at creation
("conflicting options: cannot attach both user-defined and non-user-defined network-modes"), so SWAG is not created
at all, and a lone `--network=findaline-mirror_mirror` in the template's extra parameters (where the template writes
no network option of its own for the default bridge) replaces the bridge: the mirror's network is internal, no port
is published, and every site behind SWAG is unreachable. A later Docker release accepted the pair in a trial: try it
on the server's own version first. Where the template cannot carry it, a scheduled job of the host attaches SWAG
again when an update has dropped it, every few minutes (the mirror answers 502 until it runs; the other sites are
untouched):
```sh
docker inspect swag >/dev/null 2>&1 || exit 0
docker network inspect findaline-mirror_mirror >/dev/null 2>&1 || exit 0
docker inspect swag --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' | grep -q findaline-mirror_mirror && exit 0
docker network connect findaline-mirror_mirror swag
```
Switch the job off while the mirror's project is taken down (it would attach SWAG again after the disconnect above).

## Certificate: a planned maintenance stop

The mirror's name must be in SWAG's certificate: added to `EXTRA_DOMAINS` (or its first label to `SUBDOMAINS`
when SWAG's `URL` is the parent domain), then SWAG recreated. **This is not a quiet step.** When any of its
validation settings changed (the names among them), SWAG's start script **revokes and deletes the existing
certificate first** (a failed revoke is ignored), and only then asks for a new one. SWAG's web server does not
run meanwhile, so **every site behind SWAG is down** for that time; if the new certificate cannot be issued, SWAG
prints an error and waits, and every site stays down until a restart succeeds (a restart asks again, without a
second revoke).

So do it as a planned maintenance stop:
1. The DNS record of `mirror.findaline.lukawski.org` in place and answering with the home address (check it from
   outside the home network).
2. The validation's way in checked from outside: for HTTP validation, port 80 of the router reaches SWAG's port
   80; for DNS validation, the DNS plugin's credentials cover the new name.
3. Add the name, recreate SWAG, watch `docker logs -f swag` until it says the certificate exists and nginx starts.
4. Check the other sites, then the mirror (`tests/mirror_check.sh --live`).

**No trial with SWAG's staging switch on a live SWAG**: switching `STAGING` on is itself one of the changed
settings, so it revokes and deletes the production certificate, and switching it back does it again.

## The publishing account

The PC that publishes (`tools/mirror_publish.py`, through rclone over SFTP) reaches `<root>` through a door of its
own: a second compose project, `findaline-mirror-publish` in `publish/`, one service `sftp` (OpenSSH on Alpine,
built from `publish/Dockerfile`). The mirror's own project stays as it is (one service, no published port).

**The way from the PC.** The door's port is published on one address of the server, `PUBLISH_ADDRESS`: the address
the publishing PC reaches. That is the server's LAN address when the PC is on the same LAN, or the server's address
on a VPN or WireGuard link of your own between the PC and the server (made and kept outside this project).
**Never `0.0.0.0` or `::`** (every address of the server), and no port of the router forwarded to the door: SSH is
not opened to the internet.

What the door is:
- one account, `publish` (uid 1000, also in group 101, the file server's group), key only: no password, no
  keyboard-interactive login, no root, no TTY, no forwarding of any kind, no user rc. sshd runs as that account,
  on a read-only root, with no capability;
- a command gate (`publish/gate.sh`, sshd's `ForceCommand`): the key can run the SFTP server and `sha256sum` of
  one regular file whose resolved path lies under the mirror folder, nothing else (no shell; a symlink out of the
  folder, a device, `..`, two paths, shell syntax are refused);
- its port published on `PUBLISH_ADDRESS` only (`PUBLISH_PORT`, 2222 by default), on a network of its own, never
  the mirror's internal one. sshd listens on every address of its container, so also on the container's address
  on that network (`findaline-mirror-publish_publish`); that address is reached from the home server itself, not
  from the LAN or the link. Docker's documentation: "all ports of containers on bridge networks are accessible from the Docker
  host", and "By default, remote hosts are not allowed direct access to container IP addresses in Docker's Linux
  bridge networks. They can only access ports published to host IP addresses."
  (docs.docker.com/engine/network/port-publishing/, read 2026-11-21); the daemon option `allow-direct-routing`,
  the network option `com.docker.network.bridge.trusted_host_interfaces` and the daemon's environment variable
  `DOCKER_INSECURE_NO_IPTABLES_RAW` lift that: set none of them. Docker Engine 28.0.0 fixed "a security issue
  that was allowing remote hosts to connect directly to a container on its published ports" (moby/moby#49325)
  and blocked "Direct routed access to container ports that are not exposed using `p`/`-publish`"
  (moby/moby#48724); 28.0.3 added `DOCKER_INSECURE_NO_IPTABLES_RAW=1`, which allows "other hosts on the local
  network to route to ports published to host addresses" (moby/moby#49621); 28.2.0 added `allow-direct-routing`
  "to disable filtering of packets from outside the host addressed directly to containers" (moby/moby#49832)
  (docs.docker.com/engine/release-notes/28/, read 2026-11-21). Tried on Engine 29.10 with its defaults: a LAN
  host with a route to the `publish` network got no answer from the container's address on port 2222, and the
  published address answered it; with `allow-direct-routing` set, the same direct request got through. An older
  engine may let a LAN host with a route to that network reach sshd there (the key is still required). Check the
  engine:
  `docker version --format '{{.Server.Version}}'` (28.2 or newer);
- `<root>` mounted whole at `/mirror` (one mount: the publish tool's swap is two renames, and a rename across two
  mounts fails: tried with `public` as a mount of its own in the check script's self-test, the rename fails; the
  research for this door saw rclone 1.76 then exit 1 with "Failure" and leave the files in `staging`),
  `authorized_keys` and the door's host key mounted read-only, nothing else of the host. Files it writes get
  mode 644 and folders 755, so the file server (uid 101) reads them; it reads `<root>/logs` through group 101
  (`tools/mirror_publish.py stats`). On the host they belong to uid 1000, whichever user that is there (on many
  systems the first person's account): that user can change the published files. The key's holder can also leave
  a setuid file of uid 1000 in the mirror's folders (SFTP keeps the mode a chmod sets); it matters only if another
  user of the home server runs it. Whoever wants that closed mounts the file system of `<root>` with `nosuid`.
- no links made over SFTP: the SFTP server refuses symlink and hard link requests (rclone makes none).

The door's own log (Docker's json-file log of `findaline-mirror-publish-sftp-1`, `docker compose logs` in
`publish/`) is kept: sshd writes there the publishing PC's address (on the LAN or on your link) and the key's
fingerprint at each login, and refused attempts. That holds for an IPv4 `PUBLISH_ADDRESS`; with an IPv6 one,
Docker passes the connection on through its proxy (the door's network is IPv4 only), and the log names the
network's gateway instead of the PC (seen in the build's review). It is the record of when the publishing key was used. It is
bounded by the json-file size cap of `publish/compose.yaml` (3 files of 1 MB) and goes with the container when it
is removed.

What the key can still read, accepted: the container's own read-only files (an Alpine system, no secret) and the
door's host key (sshd runs as the account and needs it). Whoever holds the publishing key could therefore copy the
door's host key and pose as the door at its address; and whoever holds it decides what every installation
downloads (spec S17). So:
- **the key pair is made on the PC that publishes, used for publishing only, and never placed on the VPS or in
  the repository**:
  ```sh
  ssh-keygen -t ed25519 -C findaline-publish -f <keys folder on the PC>/findaline-publish
  ```
  (a passphrase is possible; rclone then needs it as `key_file_pass`, obscured, in its config:
  `rclone obscure <passphrase>` prints that form).
  Only its public half, `findaline-publish.pub`, goes to the server: copy it there by any way you trust (a USB
  stick, your own copy to the server), into the folder you run the install's `install -m 0644
  findaline-publish.pub ...` from. On the server, `ssh-keygen -l -f findaline-publish.pub` must show the same
  fingerprint as on the PC. The private half never leaves the PC.

**Install** (on the server; `ROOT` as in the mirror's install, `KEYS` a folder outside the copy of this folder; your
link up first, when the PC uses one):
```sh
KEYS=/path/to/findaline-mirror-keys
install -d -m 0755 "$KEYS"
cd publish && cp .env.example .env    # MIRROR_ROOT (the mirror's), PUBLISH_KEYS="$KEYS", PUBLISH_ADDRESS, PUBLISH_PORT
docker compose build                  # the image findaline-mirror-publish-sftp
# The door's host key, made once (owned by the account, mode 600); note its fingerprint
docker run --rm --user 0 --network none -v "$KEYS:/v" --entrypoint ssh-keygen findaline-mirror-publish-sftp -q -t ed25519 -N '' -C findaline-mirror-publish -f /v/ssh_host_ed25519_key
chown 1000:1000 "$KEYS/ssh_host_ed25519_key" && chmod 600 "$KEYS/ssh_host_ed25519_key"
docker run --rm --network none -v "$KEYS:/v:ro" --entrypoint ssh-keygen findaline-mirror-publish-sftp -l -f /v/ssh_host_ed25519_key.pub
# The publishing key's public half, from the PC (owned by root, mode 644)
install -m 0644 findaline-publish.pub "$KEYS/authorized_keys"
# The folders the account writes
chown -R 1000:1000 "$ROOT/staging" "$ROOT/public" "$ROOT/trash"       # logs/ stays 101:101, 0750
docker compose up -d --wait
docker compose port sftp 2222        # must show PUBLISH_ADDRESS (<address>:<port>)
docker version --format '{{.Server.Version}}'                         # 28.2 or newer (above)
```
If `docker compose port sftp 2222` shows `0.0.0.0:<port>` or `[::]:<port>`, the door listens on every address:
stop it at once (`docker compose down`), put the address the PC reaches into `PUBLISH_ADDRESS` and start it again.
Both images are built on the server from this folder (no registry): a compose tool that pulls but does not build
needs `docker compose build` first, for the file server's image (`compose.yaml`) and for the door's
(`publish/compose.yaml`).

**An address that comes up after Docker.** When `PUBLISH_ADDRESS` belongs to an interface that comes up after
Docker (a VPN's or a WireGuard link's), the door cannot start until that address exists: Docker refuses to start the
container ("failed to bind host port <address>:<port>/tcp: cannot assign requested address"), and it does not try
again by itself once the address is there, restart policy or not: "A restart policy only takes effect after a
container starts successfully. In this case, starting successfully means that the container is up for at least 10
seconds and Docker has started monitoring it." (docs.docker.com/engine/containers/start-containers-automatically/,
read 2026-11-21). Seen with Docker Engine 29.10 (in docker:dind, 2026-11-21): the daemon started while the address
was missing left the door Exited with that error, still Exited a minute after the address came back, and running
at once after `docker start`; with the address there before the daemon started, the door came up by itself. The
mirror's own project is not affected (it publishes no port). So after every reboot of the server, and after the
link was down while Docker started, check the door in `publish/` once the link is up:
```sh
docker compose ps -a             # sftp: running (healthy); Exited or Created: the address was missing
docker compose up -d             # starts it, now that the address exists
docker compose port sftp 2222    # PUBLISH_ADDRESS (<address>:<port>) again
```
Where the system lets you order its services, bring the link up before Docker: then the door starts with Docker.

**The rclone remote on the PC**, in a config file of its own (rclone writes into the config file it is given, e.g.
settings it detects; keep the file private, out of the repository). The values in angle brackets are yours:
```ini
[findaline-mirror]
type = sftp
host = <PUBLISH_ADDRESS>
port = <PUBLISH_PORT>
user = publish
key_file = <keys folder on the PC>/findaline-publish
known_hosts_file = <a known_hosts file on the PC>
shell_type = unix
hashes = sha256
sha256sum_command = sha256sum
md5sum_command = none
sha1sum_command = none
```
- `host` is the address the door is published on; an IPv6 address goes in brackets: rclone 1.76 refuses a bare
  IPv6 address ("dial tcp: address ::1:2299: too many colons in address"; `[::1]` dials).
- `known_hosts_file` holds one line, `[<address>]:<port> ssh-ed25519 AAAA...`, the content of the server's
  `$KEYS/ssh_host_ed25519_key.pub` after the address (public; bring it to the PC as you brought the other key the
  other way, or copy its text from the server's screen); the address as in `host`, without brackets of its own,
  inside the line's brackets: `[192.0.2.10]:2222`, `[fd00::1]:2222` (rclone 1.76 cannot parse
  `[[fd00::1]]:2222`), and in the same written form (an expanded IPv6 address in one and a compressed one in the
  other do not match). Before using it, on the PC: `ssh-keygen -l -f <a known_hosts file on the PC>` must show the
  fingerprint noted at the install (`SHA256:...`, the line printed after the host key was made); a different one
  means it is not the door's key. Without the file rclone checks no host key at all.
- `shell_type`, `hashes` and `sha256sum_command` must be set: rclone's detection would set the hashes to `none`
  behind the gate.
- The remote's top folder is the mirror folder as the container shows it: `findaline-mirror:/mirror` (so
  `--to findaline-mirror:/mirror`, `--from findaline-mirror:/mirror/logs`).

**If the door does not answer** (a publish stops at the connection), in this order:
- your link is up (when the PC uses one), and the PC reaches `PUBLISH_ADDRESS`;
- on the server in `publish/`: `docker compose ps -a` shows `sftp` running (healthy); if it is Exited or Created,
  `docker compose up -d` (after a reboot whose link came up after Docker: above), then
  `docker compose port sftp 2222` shows `PUBLISH_ADDRESS` again.

**Checking it**, from the PC (works before the first publish too):
```sh
rclone --config <file> lsd findaline-mirror:/mirror                                  # logs, public, staging, trash
echo door-check | rclone --config <file> rcat findaline-mirror:/mirror/staging/door-check.txt
rclone --config <file> hashsum sha256 findaline-mirror:/mirror/staging/door-check.txt  # the server's hash
echo door-check | sha256sum                                                           # the same value
rclone --config <file> deletefile findaline-mirror:/mirror/staging/door-check.txt
```
The hash must come from the server (the publish tool's check of every copied file needs it): "hash unsupported:
hash type not supported" means the `hashes` and `sha256sum_command` lines above are missing. Hashing
`public/v1` instead works only after the first publish (before it the folder does not exist: "directory not
found"). `tests/mirror_check.sh` checks the door (the D lines) on a PC or in CI.

**Updating**: monthly, with the file server's image: the base is pinned by digest (`ARG ALPINE_IMAGE` in
`publish/Dockerfile`); the packages are not pinned, so a rebuild takes the newest OpenSSH of that Alpine branch.
Edit the digest, then `docker compose build --pull` and `docker compose up -d --wait` in `publish/`. The host key
and `authorized_keys` stay in `PUBLISH_KEYS`, so the PC's `known_hosts` stays valid.

## Settings

| Setting | What it is |
| --- | --- |
| `MIRROR_ROOT` | the host folder holding `public/`, `logs/`, `staging/`, `trash/` |
| `MIRROR_CONTACT` | the contact for abuse and takedown requests, put into the landing page at start |
| `MIRROR_TRUSTED_ADDRESSES` | the site's server: at most four single IPv4 addresses, comma-separated; empty for none |
| `MIRROR_SUBNET` | the project's network (default `172.29.42.0/24`, a /16 to /29); X-Real-IP is believed from it |
| `MIRROR_MEMORY` | the container's memory, also with swap (default `128m`) |

## Checks

From the server, in this folder (the acceptance of the specification's section 4):
```sh
docker compose ps                                                       # files: running (healthy)
docker inspect findaline-mirror-files-1 --format '{{.HostConfig.ReadonlyRootfs}}'          # true: read-only root
docker inspect findaline-mirror-files-1 --format '{{.HostConfig.CapDrop}}'                 # [ALL]
docker compose exec files grep CapEff /proc/1/status                    # CapEff: 0000000000000000: no capability
docker port findaline-mirror-files-1                                    # nothing: no published port
docker network inspect findaline-mirror_mirror --format '{{.Internal}}'                     # true
docker compose exec files wget -q -T 5 -O /dev/null http://1.1.1.1/; echo $?   # not 0: no route out
wget -q -T 5 -O /dev/null http://1.1.1.1/; echo $?                      # 0 from the host itself: the control
ROOT=/path/to/findaline-mirror                                          # as in Install (MIRROR_ROOT)
ls -l "$ROOT/logs"                                                      # access-<day>.log files
# no log file named for a day 14 or more days back (the cleanup's own rule, by the name's date):
c=$(date -u -d "@$(( $(date -u +%s) - 14 * 86400 ))" +%F) && [ -n "$c" ] && echo "14 days back: $c" && ls "$ROOT/logs" | awk -v c="access-$c.log" '/^access-[0-9][0-9][0-9][0-9]-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])\.log$/ && $0 <= c' || echo "NOT CHECKED: the day 14 days back could not be computed"
```
The last line prints the day 14 days back and nothing else. A file name under it is a file the cleanup should
have deleted, and "NOT CHECKED" means nothing was compared. It works with GNU's and BusyBox's `date` and `awk`
(tried in the file server's image, Alpine, Debian and Ubuntu). The form `date -d '14 days ago'` is GNU only:
BusyBox refuses it, and a line built on it then prints nothing and looks like a pass.

From a PC with the repository, through SWAG (what needs no test data; the cap check needs one published
dataset, the index comparison `--master <folder>` the master copy):
```sh
bash tests/mirror_check.sh --live https://mirror.findaline.lukawski.org
```
From inside the home network the address SWAG sees may be a local one; the checks hold either way.

The cap check (LV15) takes the largest tile it finds (up to 15 tiles of every published product, at most 60
looked at) and asks for it eight times at once from one address: 4 answers 200 and 4 answers 429 with
`Retry-After: 10` show the cap of 4 per address through SWAG. The mirror sends a request no faster than 4 MB/s
whatever the client reads, so each served request stays open about its size / 4 MB/s and the eight overlap; it
needs no HTTP/2 (curl opens eight connections). With the test stack's stand-in (5 tries a size, from this PC
through Docker's published port and from a container beside the stand-in) it showed every time from 0.25 MB on
and never at 0.1 MB, where a request ends at once (its first 256 KB go without waiting). The check asks for 1 MB
(`LV15_MIN_BYTES`: 0.24 s a request, room for eight connections over the internet to start further apart) and
tries up to three times. Below that size LV15 is a SKIP that names the size found and the size needed, and the
summary says the cap is still unproven. So LV15 can be expected to run after the first publish, Madeira (tiles
of about 1.8 MB); Valle d'Aosta (about 1.9 MB) and Slovakia's 1 m (about 7 MB) as well.

LV17 holds slow downloads of the same tile and asks once more: it shows that SWAG passes `X-Accel-Buffering` on
(streams a tile instead of buffering it), which LV15 does not, but only when the tile is larger than what the
proxy's buffers and the sockets on the way hold. With the stand-in that was every time from 16 MB tiles on
(12-14 MB now and then, 8 MB never: `LV17_MIN_BYTES`); below it LV17 is a SKIP naming the sizes. None of
today's datasets has such tiles, so through the real SWAG that part stays unproven (the specification's open
item M4); the test stack's C03-C07 show it with the stand-in.

## The log and privacy

One JSON line per request, with exactly the keys `t` (time), `s` (status), `b` (bytes sent), `rt` (request time,
seconds), `ds` (the dataset, the first path part after `/v1/tiles/`, only for a request for one of the served
names and at most 40 characters, else `-`), `a` (the visitor's address), `lim` (the limit that refused: `rate`;
`conn` for a visitor's concurrent requests, which covers both the address's 4 and all visitors' 8, so `stats`
cannot tell those two apart; `trusted`; `-` when served), `v` (the version of a
`Find-a-Line/<version>` User-Agent: two or three numbers of at most three digits, optionally the word `a`, `b`,
`rc`, `.dev` or `.post` without its number, a local label dropped; `unknown` as it is; else `other`, so no
written form of an address is logged there). Never the tile's path, the query or the
rest of the User-Agent; `tools/mirror_publish.py stats` reads it. Docker's own log of the container holds nothing
of the requests (the error log runs at "critical"). The healthcheck's own requests are not logged.

The folder's size is bounded too: every hour, after deleting the files 14 or more days old, the cleanup deletes
the oldest days' files while all `access-*.log` files together are above `LOG_CAP_BYTES` (start.sh, 2 GB);
if today's file alone is above it, today's file is emptied in
place (nginx goes on writing it, nothing restarts). So under a flood of requests the log may hold fewer than
14 days.

The text the landing page carries (the privacy note of the project's README says the same):

> An installation that downloads from the project's data server shows it its address and which tiles it asks
> for. The server writes down the time, the address, the dataset (not the tile), the size, whether the request
> was served or refused, how long it took, and the Find-a-Line version of each request. It keeps this for at
> most 14 days, to hold the service within its limits, and uses it for nothing else. To never contact the data
> server, set `FINDALINE_MIRROR_URL` to `off`; the regions it serves then use coarser data.

A new key or another period changes this text, with the user's yes (docs/mirror-hosting/spec.md, section 7).

## Updating

- **The base images** (a monthly item; the door's: "The publishing account"): the file server's is pinned by tag and digest in `Dockerfile` (`ARG NGINX_IMAGE`), so it gets
  no automatic updates and compose tools that check for updates skip it. Pick the newest tag of the stable
  Alpine line, read its digest with `docker buildx imagetools inspect nginx/nginx-unprivileged:<tag>`, change
  the `ARG`, run `tests/mirror_check.sh --self-test` on a PC (or let CI's job `mirror` run it: the workflow
  `.github/workflows/mirror.yml` runs when this folder, the check script, its static test or the workflow
  change, and by hand), then on the
  server: copy the folder, `docker compose up -d --build --wait`.
- **The config** (a new version of this folder): copy it over the old one (keep `.env`), then
  `docker compose up -d --build --wait`. A changed SWAG conf is copied to SWAG's `proxy-confs/` again.

## Testing on a PC

`compose.test.yaml` adds a stand-in for SWAG (plain nginx with the settings of SWAG's `proxy.conf`,
`test/swag-proxy.conf`, and
this folder's SWAG conf turned into plain HTTP by `test/standin.sh`), published on `127.0.0.1:8790`; set
`MIRROR_TEST_PORT` in the environment or in the env file to use another port. With `MIRROR_ROOT` pointing at a
local copy of `public/` (and a `logs/` folder):
```sh
docker compose -p <name> --env-file <settings> -f compose.yaml -f compose.test.yaml up -d --build --wait
FINDALINE_MIRROR_URL=http://127.0.0.1:8790 python findaline.py ...      # a search over HTTP
docker compose -p <name> --env-file <settings> -f compose.yaml -f compose.test.yaml down
```
On Docker Desktop a mapped network drive shows up empty in a container: the copy must be on a local disk. Requests
through the stand-in come from the address Docker gives the published port's connections (the gateway of the
stand-in's `front` network): one visitor address, within the visitors' limits unless that address is in
`MIRROR_TRUSTED_ADDRESSES`.

`tests/mirror_check.sh` builds the stack with a fixture tree (`test/compose.check.yaml`, `test/fixture.sh`),
runs every check and, with `--self-test`, each behaviour switched off. Its project name, networks and port are
settings of its own (see its header).
