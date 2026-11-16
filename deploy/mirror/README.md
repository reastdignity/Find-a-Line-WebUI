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
   through group 101: "The publishing account" below.
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
The attachment lasts until SWAG's container is recreated (an image update recreates it): **run the
`docker network connect` again after every update of SWAG**, and check it (below). This way can never stop SWAG:
the conf names the mirror through a variable and SWAG's resolver, so SWAG starts and serves its other sites
whether the mirror is there or not (tried with the test stack's stand-in: taken off the mirror's network and
restarted, it started and answered the mirror's name with 502).

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
```
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
SWAG runs from a platform's container template, the template may allow several networks per container, with the
same risk.

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

What the door is:
- one account, `publish` (uid 1000, also in group 101, the file server's group), key only: no password, no
  keyboard-interactive login, no root, no TTY, no forwarding of any kind, no user rc. sshd runs as that account,
  on a read-only root, with no capability;
- a command gate (`publish/gate.sh`, sshd's `ForceCommand`): the key can run the SFTP server and `sha256sum` of
  one regular file whose resolved path lies under the mirror folder, nothing else (no shell; a symlink out of the
  folder, a device, `..`, two paths, shell syntax are refused);
- its port published on the server's **LAN address only** (`PUBLISH_ADDRESS`, required; never `0.0.0.0`; the
  router forwards nothing to it), on a network of its own, never the mirror's internal one;
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
`publish/`) is kept: sshd writes there the publishing PC's LAN address and the key's fingerprint at each login,
and refused attempts. It is the record of when the publishing key was used. It is bounded by the json-file size
cap of `publish/compose.yaml` (3 files of 1 MB) and goes with the container when it is removed.

What the key can still read, accepted: the container's own read-only files (an Alpine system, no secret) and the
door's host key (sshd runs as the account and needs it). Whoever holds the publishing key could therefore copy the
door's host key and pose as the door on the LAN; and whoever holds it decides what every installation downloads
(spec S17). So:
- **the key pair is made on the PC that publishes, used for publishing only, and never placed on the VPS or in
  the repository**:
  ```sh
  ssh-keygen -t ed25519 -C findaline-publish -f <keys folder on the PC>/findaline-publish
  ```
  (a passphrase is possible; rclone then needs it as `key_file_pass`, obscured, in its config).

**Install** (on the server; `ROOT` as in the mirror's install, `KEYS` a folder outside the copy of this folder):
```sh
KEYS=/path/to/findaline-mirror-keys
install -d -m 0755 "$KEYS"
cd publish && cp .env.example .env    # MIRROR_ROOT (the mirror's), PUBLISH_KEYS="$KEYS", PUBLISH_ADDRESS (LAN), PUBLISH_PORT
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
docker compose port sftp 2222        # must show the LAN address (<address>:<port>)
```
If `docker compose port sftp 2222` shows `0.0.0.0:<port>` or `[::]:<port>`, the door listens on every address:
stop it at once (`docker compose down`), put the server's LAN address into `PUBLISH_ADDRESS` and start it again.
Both images are built on the server from this folder (no registry): a compose tool that pulls but does not build
needs `docker compose build` first, for the file server's image (`compose.yaml`) and for the door's
(`publish/compose.yaml`).

**The rclone remote on the PC**, in a config file of its own (rclone writes into the config file it is given, e.g.
settings it detects; keep the file private, out of the repository). The values in angle brackets are yours:
```ini
[findaline-mirror]
type = sftp
host = <the server's LAN address>
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
- `known_hosts_file` holds one line, `[<address>]:<port> ssh-ed25519 AAAA...`, the content of the server's
  `ssh_host_ed25519_key.pub` (compare `ssh-keygen -l -f` of it with the fingerprint noted). Without it rclone
  checks no host key at all.
- `shell_type`, `hashes` and `sha256sum_command` must be set: rclone's detection would set the hashes to `none`
  behind the gate.
- The remote's top folder is the mirror folder as the container shows it: `findaline-mirror:/mirror` (so
  `--to findaline-mirror:/mirror`, `--from findaline-mirror:/mirror/logs`).

**Checking it**: from the PC, `rclone --config <file> lsd findaline-mirror:/mirror` lists `logs`, `public`, `staging`,
`trash`, and `rclone --config <file> hashsum sha256 findaline-mirror:/mirror/public/v1` hashes on the server.
`tests/mirror_check.sh` checks the door (the D lines) on a PC or in CI.

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
ls "$ROOT/logs" | awk -v c="access-$(date -u -d '14 days ago' +%F).log" '/^access-[0-9]{4}-[0-9]{2}-[0-9]{2}\.log$/ && $0 <= c'   # nothing
```

From a PC with the repository, through SWAG (what needs no test data; the cap check needs one published
dataset, the index comparison `--master <folder>` the master copy):
```sh
bash tests/mirror_check.sh --live https://mirror.findaline.lukawski.org
```
From inside the home network the address SWAG sees may be a local one; the checks hold either way. The cap
check (LV15) holds slow downloads of the largest listed tile open: it shows that SWAG honours
`X-Accel-Buffering` only when that tile is larger than what the sockets and buffers on the way hold (several
MB); with a small tile it fails without saying anything about SWAG.

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
the oldest days' files while all `access-*.log` files together are above `LOG_CAP_BYTES` (start.sh;
provisionally 2 GB, the number is the user's); if today's file alone is above it, today's file is emptied in
place (nginx goes on writing it, nothing restarts). So under a flood of requests the log may hold fewer than
14 days.

The text the landing page carries (the privacy note of the project's README says the same):

> An installation that downloads from the project's data server shows it its address and which tiles it asks
> for. The server writes down the time, the address, the dataset (not the tile), the size, whether the request
> was served or refused, how long it took, and the Find-a-Line version of each request. It keeps this for 14
> days, to hold the service within its limits, and uses it for nothing else. To never contact the data server,
> set `FINDALINE_MIRROR_URL` to empty; the regions it serves then use coarser data.

A new key or another period changes this text, with the user's yes (docs/mirror-hosting/spec.md, section 7).

## Updating

- **The base images** (a monthly item; the door's: "The publishing account"): the file server's is pinned by tag and digest in `Dockerfile` (`ARG NGINX_IMAGE`), so it gets
  no automatic updates and compose tools that check for updates skip it. Pick the newest tag of the stable
  Alpine line, read its digest with `docker buildx imagetools inspect nginx/nginx-unprivileged:<tag>`, change
  the `ARG`, run `tests/mirror_check.sh --self-test` on a PC (or let CI's job `mirror` run it), then on the
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
