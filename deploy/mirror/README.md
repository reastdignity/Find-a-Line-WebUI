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
  4 at once, outside the visitors' total, no request rate. A refusal is a 429 with `Retry-After: 10`;
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
   The files under `public/` must be readable by uid 101 (world-readable, as the publish tool leaves them).
3. Settings: `cp .env.example .env`, then set `MIRROR_ROOT`, `MIRROR_CONTACT` (the contact for abuse and
   takedown requests, shown on the landing page), `MIRROR_TRUSTED_ADDRESSES` (the site server's IPv4 address;
   at most four single addresses, or empty), and `MIRROR_SUBNET` only if `172.29.42.0/24` collides with another
   Docker network of the machine (`docker network inspect $(docker network ls -q) --format '{{.Name}}
   {{range .IPAM.Config}}{{.Subnet}}{{end}}'`). The start script refuses a network, a fifth address or anything
   else in `MIRROR_TRUSTED_ADDRESSES`, an empty contact and an odd subnet: `docker compose logs files` says why.
4. Start it:
   ```sh
   docker compose up -d --build --wait
   docker compose ps            # files: running (healthy)
   ```
5. Attach SWAG to the project's network (next section), copy the SWAG conf, add the host name to SWAG's
   certificate (the section after), and check from outside (`tests/mirror_check.sh --live`, "Checks").

## SWAG

SWAG reaches the mirror over the project's own network, `findaline-mirror_mirror`, which is `internal` (no route
out of the host): SWAG joins it as its second network, so the mirror's only neighbour is SWAG. The mirror
believes the visitor's address (`X-Real-IP`, which SWAG's `proxy.conf` sets) from any sender on this network:
**attach nothing else to it**.

```sh
docker network connect findaline-mirror_mirror swag          # "swag": SWAG's container name
cp swag/findaline-mirror.subdomain.conf /path/to/swag/config/nginx/proxy-confs/
docker restart swag                                           # or SWAG_AUTORELOAD
```

`swag/findaline-mirror.subdomain.conf` answers `mirror.findaline.lukawski.org`, passes requests on with SWAG's
own `proxy.conf`, refuses every method but GET and HEAD and any body over 1 KB itself (405 and 413, never 403,
which fail2ban's jails count), writes no access log for this host and only critical lines to the error log (both
would hold the tile's path and the visitor's address). It sets no `proxy_ignore_headers` and no `proxy_buffering`:
the mirror sends `X-Accel-Buffering: no`, without which SWAG would take a whole file into its temporary files at
once and the mirror's connection caps would count nothing. Keep it so when editing SWAG's configuration.

**Making the attachment lasting.** `docker network connect` lasts until SWAG's container is recreated (an image
update recreates it). Then the mirror is unreachable (an outage, never an exposure) until SWAG is attached again.
- SWAG run by compose: add the network to SWAG's compose file instead, so every recreation attaches it:
  ```yaml
  services:
    swag:
      networks: [default, findaline-mirror]
  networks:
    findaline-mirror:
      external: true
      name: findaline-mirror_mirror
  ```
  The mirror's project must then be up before SWAG starts (SWAG refuses to start without the network).
- SWAG run from a platform's container template: add the network in the template where the platform allows
  several networks per container; otherwise run the `docker network connect` above after every update of SWAG
  (a script the platform runs after Docker starts and after updates).

**Checking it** (after every update of SWAG):
```sh
docker inspect swag --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'   # lists findaline-mirror_mirror
docker exec swag curl -s -o /dev/null -w '%{http_code}\n' http://findaline-mirror-files:8080/robots.txt   # 200
```

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

The publishing key opens a small SFTP container that sees only `<root>` (the user's decision of 2026-11-15);
the details follow.

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
ls -l "$MIRROR_ROOT/logs"                                               # access-<day>.log, none 14 or more days old
find "$MIRROR_ROOT/logs" -name 'access-*.log' -mtime +14                # nothing
```

From a PC with the repository, through SWAG (what needs no test data; the cap check needs one published
dataset, the index comparison `--master <folder>` the master copy):
```sh
bash tests/mirror_check.sh --live https://mirror.findaline.lukawski.org
```
From inside the home network the address SWAG sees may be a local one; the checks hold either way.

## The log and privacy

One JSON line per request, with exactly the keys `t` (time), `s` (status), `b` (bytes sent), `rt` (request time,
seconds), `ds` (the dataset: the first path part after `/v1/tiles/`, else `-`), `a` (the visitor's address),
`lim` (the limit that refused: `rate`, `conn` for a visitor's concurrent requests, `trusted`; `-` when served),
`v` (the version of a `Find-a-Line/<version>` User-Agent, else `other`). Never the tile's path, the query or the
rest of the User-Agent; `tools/mirror_publish.py stats` reads it. Docker's own log of the container holds nothing
of the requests (the error log runs at "critical"). The healthcheck's own requests are not logged.

The text the landing page carries (the privacy note of the project's README says the same):

> An installation that downloads from the project's data server shows it its address and which tiles it asks
> for. The server writes down the time, the address, the dataset (not the tile), the size, whether the request
> was served or refused, how long it took, and the Find-a-Line version of each request. It keeps this for 14
> days, to hold the service within its limits, and uses it for nothing else. To never contact the data server,
> set `FINDALINE_MIRROR_URL` to empty; the regions it serves then use coarser data.

A new key or another period changes this text, with the user's yes (docs/mirror-hosting/spec.md, section 7).

## Updating

- **The base image** (a monthly item): pinned by tag and digest in `Dockerfile` (`ARG NGINX_IMAGE`), so it gets
  no automatic updates and compose tools that check for updates skip it. Pick the newest tag of the stable
  Alpine line, read its digest with `docker buildx imagetools inspect nginx/nginx-unprivileged:<tag>`, change
  the `ARG`, run `tests/mirror_check.sh --self-test` on a PC (or let CI's job `mirror` run it), then on the
  server: copy the folder, `docker compose up -d --build --wait`.
- **The config** (a new version of this folder): copy it over the old one (keep `.env`), then
  `docker compose up -d --build --wait`. A changed SWAG conf is copied to SWAG's `proxy-confs/` again.

## Testing on a PC

`compose.test.yaml` adds a stand-in for SWAG (plain nginx with SWAG's `proxy.conf`, `test/swag-proxy.conf`, and
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
