"""The mirror stack (deploy/mirror, docs/mirror-hosting/spec.md, section 4), read statically: the
compose project's hardening (as tests/test_monitoring.py::test_compose_hardening, written out
again here), that compose.yaml publishes no port and mounts the public folder read-only, its one
network internal, the SWAG conf's lines (A.8), the served patterns against the names the client
builds (grid_tile_name, res_name, the catalogue's mirror folders), the limits' and timeouts'
numbers, the log's keys and its 14 days, and the landing page's privacy text. The stack itself
runs in tests/mirror_check.sh (the CI job `mirror`)."""

import os
import re

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.join(ROOT, "deploy", "mirror")
HOST = "mirror.findaline.lukawski.org"
SETTINGS = {"MIRROR_ROOT", "MIRROR_SUBNET", "MIRROR_TRUSTED_ADDRESSES", "MIRROR_CONTACT", "MIRROR_MEMORY"}
LOG_KEYS = ["t", "s", "b", "rt", "ds", "a", "lim", "v"]
DIGEST = r"[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}"


def _load(*parts: str) -> str:
    with open(os.path.join(MIRROR, *parts), encoding="utf-8") as f:
        return f.read()


def _compose(name: str = "compose.yaml") -> dict:
    return yaml.safe_load(_load(name))


def _nginx() -> str:
    """nginx.conf without its comments."""
    return "\n".join(line.split("#", 1)[0] if not line.lstrip().startswith("#") else ""
                     for line in _load("nginx.conf").splitlines())


def test_compose_hardening():
    """One service `files` in the project findaline-mirror: read-only root, no capabilities, no new
    privileges, a non-root user, memory without swap, a pid limit, rotated logs, a healthcheck,
    init (the cleanup loop's children), restart; built from the Dockerfile, whose base is pinned
    by digest."""
    compose = _compose()
    assert compose["name"] == "findaline-mirror"
    assert set(compose["services"]) == {"files"}
    service = compose["services"]["files"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert str(service["user"]) == "101:101"
    assert service["mem_limit"] and service["memswap_limit"] == service["mem_limit"]
    assert service["pids_limit"] == 64
    assert service["logging"]["driver"] == "json-file" and "max-size" in service["logging"]["options"]
    assert service["healthcheck"]["test"] == ["CMD", "/usr/local/bin/mirror-start", "health"]
    assert service["restart"] == "unless-stopped"
    assert service["init"] is True
    assert service["build"] == {"context": "."} and "image" not in service
    dockerfile = _load("Dockerfile")
    arg = re.search(r"^ARG NGINX_IMAGE=(\S+)$", dockerfile, re.M)
    assert arg and re.fullmatch(DIGEST, arg.group(1))
    assert arg.group(1).startswith("nginx/nginx-unprivileged:") and "-alpine" in arg.group(1)
    assert re.search(r"^FROM \$\{NGINX_IMAGE\}$", dockerfile, re.M)
    assert re.search(r"^USER 101$", dockerfile, re.M)
    assert 'ENTRYPOINT ["/usr/local/bin/mirror-start"]' in dockerfile
    for source, target in [("nginx.conf", "/etc/nginx/nginx.conf"),
                           ("robots.txt", "/usr/share/findaline-mirror/robots.txt"),
                           ("landing/index.html", "/usr/share/findaline-mirror/index.html.in"),
                           ("start.sh", "/usr/local/bin/mirror-start")]:
        assert re.search(rf"^COPY --chmod=0[67][45][45] {re.escape(source)} {re.escape(target)}$", dockerfile, re.M), source


def test_no_published_port_and_mounts():
    """compose.yaml alone publishes nothing; it mounts <root>/public read-only and <root>/logs, never
    created by Docker, and a tmpfs; the test stack's stand-in publishes on the loopback only."""
    service = _compose()["services"]["files"]
    assert "ports" not in service and "expose" not in service and "network_mode" not in service
    volumes = {v["target"]: v for v in service["volumes"]}
    assert set(volumes) == {"/srv/public", "/var/log/mirror", "/tmp"}
    public, logs, tmp = volumes["/srv/public"], volumes["/var/log/mirror"], volumes["/tmp"]
    assert public["type"] == "bind" and public["read_only"] is True and public["source"].endswith("}/public")
    assert public["bind"] == {"create_host_path": False}
    assert logs["type"] == "bind" and not logs.get("read_only") and logs["source"].endswith("}/logs")
    assert logs["bind"] == {"create_host_path": False}
    assert tmp["type"] == "tmpfs"
    test = _compose("compose.test.yaml")
    assert set(test["services"]) == {"proxy"}
    for port in test["services"]["proxy"]["ports"]:
        assert port.startswith("127.0.0.1:${MIRROR_TEST_PORT:-"), port
    assert re.fullmatch(DIGEST, test["services"]["proxy"]["image"])


def test_one_internal_network():
    """The service's only network is the project's own, internal, with a fixed subnet; SWAG reaches
    the service by the alias its conf names."""
    compose = _compose()
    assert set(compose["networks"]) == {"mirror"}
    network = compose["networks"]["mirror"]
    assert network["internal"] is True
    assert network["ipam"]["config"] == [{"subnet": "${MIRROR_SUBNET:-172.29.42.0/24}"}]
    service = compose["services"]["files"]
    assert service["networks"] == {"mirror": {"aliases": ["findaline-mirror-files"]}}
    assert service["environment"]["MIRROR_SUBNET"] == "${MIRROR_SUBNET:-172.29.42.0/24}"


def test_settings():
    """.env.example holds exactly the contract's settings, and compose.yaml uses each."""
    example = _load(".env.example")
    keys = set(re.findall(r"^([A-Z_]+)=", example, re.M))
    assert keys == SETTINGS
    assert re.search(r"^MIRROR_CONTACT=$", example, re.M)   # never a contact in the repository
    compose = _load("compose.yaml")
    for key in SETTINGS:
        assert "${" + key in compose, key


def test_swag_conf():
    """A.8: the explicit host, GET and HEAD only (405, never 403: fail2ban counts it), a body of at
    most 1 KB, no access log, nothing that would keep the mirror's X-Accel-Buffering from working,
    SWAG's proxy.conf and resolver, the upstream by the alias on port 8080."""
    lines = [line.strip() for line in _load("swag", "findaline-mirror.subdomain.conf").splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    assert f"server_name {HOST};" in lines
    assert "if ($request_method !~ ^(GET|HEAD)$) {" in lines and "return 405;" in lines
    assert "client_max_body_size 1k;" in lines
    assert "access_log off;" in lines
    assert "include /config/nginx/proxy.conf;" in lines and "include /config/nginx/resolver.conf;" in lines
    assert "set $upstream_app findaline-mirror-files;" in lines and "set $upstream_port 8080;" in lines
    text = "\n".join(lines)
    for forbidden in ("proxy_ignore_headers", "proxy_buffering", "proxy_max_temp_file_size", "deny ", "return 403",
                      "limit_except"):
        assert forbidden not in text, forbidden
    # IPv4 only (spec section 3: no AAAA record until the limits count an IPv6 /64 as one visitor)
    assert [line for line in lines if line.startswith("listen ")] == ["listen 443 ssl;"]
    assert "[::]" not in text


def _served_patterns() -> list:
    return [re.compile(m) for m in re.findall(r'^\s*location ~ "([^"]+)"', _nginx(), re.M)]


def _served(path: str) -> bool:
    exact = re.findall(r"^\s*location = (\S+)", _nginx(), re.M)
    return path in exact and not path.startswith("/__") or any(p.search(path) for p in _served_patterns())


def _mirror_folders() -> list:
    """The catalogue's mirror folders (GridTiles(mirror=...)), e.g. "slovakia/dmr5/1m"."""
    folders = []
    catalogue = os.path.join(ROOT, "sources", "catalogue")
    for name in sorted(os.listdir(catalogue)):
        if name.endswith(".py"):
            with open(os.path.join(catalogue, name), encoding="utf-8") as f:
                folders += re.findall(r'mirror="([^"]+)"', f.read())
    return folders


def test_served_patterns_match_the_names_of_the_client():
    """A.2: every name the client builds is served (grid_tile_name with negative indices too,
    res_name with "0.5m", every mirror folder of the catalogue and its averaged resolutions), and
    nothing else."""
    from sources.layers.gridtiles import renamed, res_name
    from sources.readers.tilebases import grid_tile_name

    folders = _mirror_folders()
    assert {"slovakia/dmr5/1m", "madeira/dtm/2m", "aosta/dtm/2m"} <= set(folders)
    native = {"1m": 1.0, "2m": 2.0}
    for folder in folders:
        res = native[folder.rsplit("/", 1)[1]]
        for other in (res, 2.0, 5.0, 0.5):
            base = "/v1/tiles/" + renamed(folder, res, other)
            assert _served(base + "/index.json"), base
            for i, j in [(0, 0), (1, 2), (-3, 4), (123, -45), (-10, -10), (40719, 33)]:
                assert _served(f"{base}/{grid_tile_name(i, j)}"), (base, i, j)
    assert res_name(0.5) == "0.5m"
    for path in ["/", "/robots.txt", "/v1/datasets.json", "/v1/tiles/madeira/README.md",
                 "/v1/tiles/wallonia-2021/README.md", "/v1/tiles/madeira/dtm/0.5m/0_0/0_1.tif"]:
        assert _served(path), path
    for path in ["/index.html", "/v1/", "/v1/tiles/", "/v1/tiles/madeira/", "/v1/cubes/x", "/v1/cache/x",
                 "/v1/tiles/madeira/dtm/2m/", "/v1/tiles/madeira/dtm/2m/0_0/", "/v1/tiles/madeira/dtm/2m/0_0",
                 "/v1/tiles/madeira/dtm/2m/0_0/.1_2.tif", "/v1/tiles/madeira/dtm/2m/0_0/1_2.tif.part",
                 "/v1/tiles/madeira/.secret", "/v1/tiles/Madeira/dtm/2m/index.json",
                 "/v1/tiles/madeira/dtm/2m/notes.txt", "/v1/tiles/madeira/dtm/2m/0_0/1_2.TIF",
                 "/v1/tiles/madeira/dtm/2/index.json", "/v1/tiles/madeira/dtm/.5m/index.json",
                 "/v1/tiles/madeira/dtm/2m/0_0/1_2.tif/", "/v1/tiles/../dtm/2m/0_0/1_2.tif",
                 "/v1/tiles/madeira/dtm/2m/index.json.tmp", "/v1/datasets.json.new", "/v1/tiles/madeira/README.md/"]:
        assert not _served(path), path


def test_fixture_names_are_the_clients():
    """tests/mirror_check.sh's fixture tree uses the names grid_tile_name and res_name give."""
    from sources.layers.gridtiles import res_name
    from sources.readers.tilebases import grid_tile_name

    fixture = _load("test", "fixture.sh")
    assert f"d=v1/tiles/madeira/dtm/{res_name(2.0)}" in fixture
    assert f"h=v1/tiles/madeira/dtm/{res_name(0.5)}" in fixture
    for (i, j), folder in [((1, 2), "$d"), ((-3, 4), "$d"), ((0, 1), "$h")]:
        assert f'"{folder}/{grid_tile_name(i, j)}"' in fixture, (i, j)


def test_limits_and_timeouts():
    """A.5, A.6 and the contract's numbers: visitors 4 MB/s a request, 4 at once per address, 8 of
    all visitors, 20 requests a second with a burst of 40 and no queueing; the trusted class 16
    MB/s, 4 per address, outside the visitors' total, no request rate; every refusal 429 with
    Retry-After 10; several ranges 416, a query 400; timeouts 10, 30 and 15 s; caching."""
    conf = _nginx()
    for line in ["limit_conn visitor_address 4;", "limit_conn visitors_all 8;", "limit_conn trusted_address 4;",
                 "limit_req zone=visitor_rate burst=40 nodelay;", "limit_rate $mirror_rate;",
                 "limit_conn_status 429;", "limit_req_status 429;", "max_ranges 1;", "client_max_body_size 1k;",
                 "client_header_timeout 10s;", "send_timeout 30s;", "keepalive_timeout 15s;", "server_tokens off;",
                 "disable_symlinks on;", "error_log /dev/stderr crit;"]:
        assert re.search(rf"^\s*{re.escape(line)}", conf, re.M), line
    assert re.search(r"limit_req_zone\s+\$visitor_key zone=visitor_rate:\S+ rate=20r/s;", conf)
    assert re.search(r"map \$mirror_class \$mirror_rate \{ visitor 4000000; trusted 16000000; default 0; \}", conf)
    assert re.search(r"map \$mirror_class \$visitor_key \{ visitor \$binary_remote_addr; default \"\"; \}", conf)
    assert re.search(r"map \$mirror_class \$visitor_all \{ visitor \"all\"; +default \"\"; \}", conf)
    assert re.search(r"map \$mirror_class \$trusted_key \{ trusted \$binary_remote_addr; default \"\"; \}", conf)
    # The trusted class: 4 per address and 4 for the class together (spec A.5's table)
    assert re.search(r"map \$mirror_class \$trusted_all \{ trusted \"all\"; +default \"\"; \}", conf)
    assert re.search(r"^\s*limit_conn trusted_all 4;", conf, re.M)
    assert re.search(r'map \$status \$retry_after \{ 429 "10"; default ""; \}', conf)
    # Refusals answer after the limits (code review F1): the rewrite phase only sends them on, a
    # try_files of a name that never exists answers; no "return" anywhere
    assert re.search(r'if \(\$http_range ~ ","\) \{ rewrite \^ /__refused/416\? last; \}', conf)
    assert re.search(r'if \(\$request_uri ~ "\\\?"\) \{ rewrite \^ /__refused/400\? last; \}', conf)
    assert re.search(r"if \(\$request_method !~ \^\(GET\|HEAD\)\$\) \{ rewrite \^ /__refused/405\? last; \}", conf)
    for code in (400, 405, 416):
        assert f"location = /__refused/{code} {{ root /nonexistent; try_files /.none ={code}; }}" in conf
    assert "location / { root /nonexistent; try_files /.none =404; }" in conf
    assert "location = /__not_found { root /nonexistent; try_files /.none =404; }" in conf
    # The name try_files tests never lies under a root anybody can write (code review round 2, R1)
    assert len(re.findall(r"try_files /\.none", conf)) == 5 == len(re.findall(r"root /nonexistent; try_files /\.none", conf))
    start = _load("start.sh")
    # A failing cleanup pass or day switch does not end the loop (R2)
    assert '"$0" cleanup 2> /dev/null || echo "findaline-mirror: a cleanup pass failed; the loop goes on" >&2' in start
    assert '_size=$(stat -c %s "$_file" 2> /dev/null) || continue' in start
    assert not re.search(r"\breturn\b", conf) and not re.search(r"\binternal\b", conf)
    # The healthcheck's class on the connection's own address, before X-Real-IP (code review F3)
    assert re.search(r"geo \$realip_remote_addr \$mirror_local \{\s*default 0;\s*127\.0\.0\.1 1;\s*\}", conf)
    assert '"~\\.tif$"   "max-age=86400";' in conf and '"~\\.json$"  "no-cache";' in conf
    for header in ['X-Content-Type-Options "nosniff" always', 'Cross-Origin-Resource-Policy "same-origin" always',
                   'X-Robots-Tag "noindex" always', 'X-Accel-Buffering "no" always', "Retry-After $retry_after always"]:
        assert f"add_header {header};" in conf, header
    assert "Access-Control" not in conf
    start = _load("start.sh")
    assert re.search(r"^MAX_TRUSTED=4$", start, re.M)


def test_log_keys_and_days():
    """A.7 and the contract: one JSON line a request with exactly the keys t, s, b, rt, ds, a, lim, v
    (the privacy texts name exactly these), one file a day access-YYYY-MM-DD.log in <root>/logs,
    the healthcheck not logged; the cleanup deletes a file 14 or more days back, every hour."""
    conf = _nginx()
    fmt = re.search(r"log_format mirror escape=json((?:\s*'[^']*')+);", conf)
    assert fmt
    line = "".join(re.findall(r"'([^']*)'", fmt.group(1)))
    assert re.findall(r'"(\w+)":', line) == LOG_KEYS
    assert line == ('{"t":"$time_iso8601","s":$status,"b":$body_bytes_sent,"rt":$request_time,'
                    '"ds":"$mirror_dataset","a":"$remote_addr","lim":"$mirror_limit","v":"$mirror_version"}')
    assert re.search(r"^\s*include /tmp/mirror/log\.conf;", conf, re.M)
    assert not re.search(r"^\s*access_log ", conf, re.M)
    assert "map $mirror_class $mirror_loggable { local 0; default 1; }" in conf
    assert re.search(r'default\s+"other";', conf)
    start = _load("start.sh")
    # One file a day, named by start.sh (no variable in nginx's path: see nginx.conf)
    assert r'echo "access_log $LOGS/access-$1.log mirror if=\$mirror_loggable;"' in start
    assert "_today=$(date -u +%F)" in start
    for line in ["KEEP_DAYS=14", "CLEANUP_SECONDS=3600", "LOGS=/var/log/mirror"]:
        assert re.search(rf"^{line}$", start, re.M), line
    assert '"$LOGS"/access-*.log' in start and "-le \"$_cutoff\"" in start
    assert re.search(r"^ENV TZ=UTC$", _load("Dockerfile"), re.M)


# The privacy text for README and the landing page as the user approved it (U13, U46, U47:
# "for at most 14 days", the setting's word `off`), word for word; the code marks left out
PRIVACY = ("An installation that downloads from the project's data server shows it its address and which tiles it "
           "asks for. The server writes down the time, the address, the dataset (not the tile), the size, whether "
           "the request was served or refused, how long it took, and the Find-a-Line version of each request. It "
           "keeps this for at most 14 days, to hold the service within its limits, and uses it for nothing else. "
           "To never contact the data server, set FINDALINE_MIRROR_URL to off; the regions it serves then use "
           "coarser data.")


def _privacy_text() -> str:
    """The approved text (PRIVACY); also the README's quoted copy and the check script's must hold it."""
    readme = " ".join(_load("README.md").replace("> ", " ").replace("`", "").split())
    assert PRIVACY in readme
    with open(os.path.join(ROOT, "tests", "mirror_check.sh"), encoding="utf-8") as f:
        assert f'PRIVACY="{PRIVACY}"' in f.read()
    return PRIVACY


def test_landing_page():
    """A.9: the privacy text word for word, the contact put in by the start script (never in the
    repository), the datasets read from /v1/datasets.json in the browser; no outside resource."""
    page = _load("landing", "index.html")
    text = " ".join(re.sub(r"<[^>]+>", "", page).split())
    assert _privacy_text() in text
    assert page.count("@MIRROR_CONTACT@") == 1
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", page.replace("@MIRROR_CONTACT@", ""))
    assert 'fetch("/v1/datasets.json"' in page
    assert not re.search(r"<(script|link|img)[^>]+(src|href)=\"https?:", page)
    assert _load("robots.txt") == "User-agent: *\nDisallow: /\n"


def test_ci_job():
    """The job `mirror` runs the check script with its self-test, in a workflow of its own that runs
    only when the mirror's files, its check script, this test or the workflow change, and by hand
    (U49); on branches only (a path filter is not evaluated for tag pushes); not in ci.yml."""
    workflows = os.path.join(ROOT, ".github", "workflows")
    with open(os.path.join(workflows, "mirror.yml"), encoding="utf-8") as f:
        workflow = yaml.safe_load(f)
    steps = " ".join(step.get("run", "") for step in workflow["jobs"]["mirror"]["steps"])
    assert "bash tests/mirror_check.sh --self-test" in steps
    on = workflow[True]   # PyYAML reads the key "on" as True
    paths = ["deploy/mirror/**", "tests/mirror_check.sh", "tests/test_mirror_deploy.py", ".github/workflows/mirror.yml"]
    assert on["push"] == {"branches": ["**"], "paths": paths}
    assert on["pull_request"] == {"paths": paths}
    assert "workflow_dispatch" in on and set(on) == {"push", "pull_request", "workflow_dispatch"}
    with open(os.path.join(workflows, "ci.yml"), encoding="utf-8") as f:
        assert "mirror" not in yaml.safe_load(f)["jobs"]


def test_publishing_door_compose():
    """The publishing door (publish/, the user's U32/U33, U68): a second project with the door `sftp`
    in the network namespace of a Husarnet sidecar, started when the sidecar is healthy; no port
    published by either; <root> as one read-write mount, the keys read-only, nothing else of the
    host, the hardening list; the mirror's own project stays one service without a port."""
    compose = _compose(os.path.join("publish", "compose.yaml"))
    assert compose["name"] == "findaline-mirror-publish"
    assert set(compose["services"]) == {"sftp", "husarnet"}
    for name, svc in compose["services"].items():
        assert "ports" not in svc and "expose" not in svc, name
    service = compose["services"]["sftp"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert str(service["user"]) == "1000:1000" and service["group_add"] == ["101"]
    assert service["mem_limit"] and service["memswap_limit"] == service["mem_limit"]
    assert service["pids_limit"]
    assert service["logging"]["driver"] == "json-file" and "max-size" in service["logging"]["options"]
    assert service["healthcheck"]["test"]
    assert service["restart"] == "unless-stopped"
    assert service["build"] == {"context": "."} and "image" not in service
    # In the sidecar's namespace, after it is healthy (joined and up); no network of its own
    assert service["network_mode"] == "service:husarnet"
    assert "environment" not in service and "env_file" not in service   # the join code never reaches the door
    assert "networks" not in service and "sysctls" not in service
    assert service["depends_on"] == {"husarnet": {"condition": "service_healthy", "restart": True}}
    volumes = {v["target"]: v for v in service["volumes"]}
    assert set(volumes) == {"/mirror", "/keys/authorized_keys", "/keys/host/ssh_host_ed25519_key", "/tmp"}
    root = volumes["/mirror"]
    assert root["type"] == "bind" and re.fullmatch(r"\$\{MIRROR_ROOT:\?[^}]*\}", root["source"])
    assert not root.get("read_only") and root["bind"] == {"create_host_path": False}
    for target in ("/keys/authorized_keys", "/keys/host/ssh_host_ed25519_key"):
        key = volumes[target]
        assert key["type"] == "bind" and key["read_only"] is True and key["source"].startswith("${PUBLISH_KEYS:?")
        assert key["bind"] == {"create_host_path": False}
    assert volumes["/tmp"]["type"] == "tmpfs"
    # The sidecar: pinned by digest, NET_ADMIN its one added capability, the tun device, IPv6 on in
    # the namespace, the join code and the state folder required, on the project's own network
    husarnet = compose["services"]["husarnet"]
    # built here (U75): husarnet-sidecar.Dockerfile, no image from a registry
    assert husarnet["build"] == {"context": ".", "dockerfile": "husarnet-sidecar.Dockerfile"} and "image" not in husarnet
    assert husarnet["cap_add"] == ["NET_ADMIN"] and "privileged" not in husarnet
    # bounded (U77): memory = swap, processes
    assert husarnet["mem_limit"] and husarnet["memswap_limit"] == husarnet["mem_limit"] and husarnet["pids_limit"]
    assert husarnet["devices"] == ["/dev/net/tun"]
    assert husarnet["sysctls"] == {"net.ipv6.conf.all.disable_ipv6": 0}
    # the code only for the first join: compose does not require it (husarnet.sh refuses without a join)
    assert husarnet["environment"]["HUSARNET_JOIN_CODE"] == "${HUSARNET_JOIN_CODE:-}"
    assert re.fullmatch(r"\$\{HUSARNET_HOSTNAME:-[a-z0-9-]+\}", husarnet["environment"]["HUSARNET_HOSTNAME"])
    # never HUSARNET_DEBUG: with it the daemon prints the join code to Docker's log
    assert set(husarnet["environment"]) == {"HUSARNET_JOIN_CODE", "HUSARNET_HOSTNAME"}
    assert not re.search(r"^\s+HUSARNET_DEBUG", _load("publish", "compose.yaml"), re.M)
    hvolumes = {v["target"]: v for v in husarnet["volumes"]}
    assert set(hvolumes) == {"/var/lib/husarnet"}
    state = hvolumes["/var/lib/husarnet"]
    assert state["type"] == "bind" and re.fullmatch(r"\$\{HUSARNET_STATE:\?[^}]*\}", state["source"])
    assert state["bind"] == {"create_host_path": False} and not state.get("read_only")
    assert "entrypoint" not in husarnet   # the image's: husarnet.sh start
    assert husarnet["healthcheck"]["test"] == ["CMD", "/usr/local/bin/husarnet.sh", "health"]
    sidecar = _load("publish", "husarnet-sidecar.Dockerfile")
    arg = re.search(r"^ARG DEBIAN_IMAGE=(\S+)$", sidecar, re.M)
    assert arg and re.fullmatch(DIGEST, arg.group(1)) and re.match(r"debian:[a-z]+-\d{8}-slim@", arg.group(1))
    assert re.search(r"^ARG HUSARNET_VERSION=\d+:\d+\.\d+\.\d+$", sidecar, re.M)
    assert re.search(r"^ARG HUSARNET_KEY_FINGERPRINT=[0-9A-F]{40}$", sidecar, re.M)
    assert re.findall(r"^FROM (\S+)", sidecar, re.M) == ["${DEBIAN_IMAGE}", "${DEBIAN_IMAGE}"]
    assert '"husarnet=${HUSARNET_VERSION}"' in sidecar and "--no-install-recommends" in sidecar
    assert "signed-by=/usr/share/keyrings/husarnet.gpg] https://nightly.husarnet.com/deb/ all husarnet" in sidecar
    assert re.search(r"^ARG HUSARNET_VERSION=1:2\.0\.\d+$", sidecar, re.M) and '"husarnet=${HUSARNET_VERSION}" jq' in sidecar
    assert '[ "$fingerprints" != "$HUSARNET_KEY_FINGERPRINT" ]' in sidecar
    assert "COPY --chmod=0755 husarnet.sh /usr/local/bin/husarnet.sh" in sidecar
    assert 'ENTRYPOINT ["/usr/local/bin/husarnet.sh", "start"]' in sidecar
    # the check's stand-in never builds the real sidecar (its build reset), keeps the sysctl (D37)
    overlay = _load("test", "compose.door-check.yaml")
    stand_in = overlay[overlay.index("  husarnet:\n"):overlay.index("  sftp:\n")]
    assert "    build: !reset null\n" in stand_in and "    image: !override ${DOOR_STANDIN_IMAGE:?}\n" in stand_in
    assert "sysctls" not in stand_in and "ports" not in stand_in and "networks" not in stand_in
    assert "cap_add" not in stand_in and "devices" not in stand_in   # the sidecar's NET_ADMIN and tun: it holds hnet0
    standin = _load("test", "door-standin.Dockerfile")
    assert re.search(r"^FROM \$\{DOOR_IMAGE\}$", standin, re.M) and "TUN,tun-name=hnet0" in standin
    # sftp's lost-namespace test reads the sidecar's interface by name, not "anything but lo" (G1)
    assert "grep -q '^ *hnet0:' /proc/net/dev || kill -TERM 1" in service["healthcheck"]["test"][3]
    assert husarnet["restart"] == "unless-stopped"
    assert husarnet["logging"]["driver"] == "json-file" and "max-size" in husarnet["logging"]["options"]
    assert husarnet["networks"] == ["publish"]
    assert set(compose["networks"]) == {"publish"} and not compose["networks"]["publish"].get("internal")
    assert "external" not in compose["networks"]["publish"] and "name" not in compose["networks"]["publish"]
    example = _load("publish", ".env.example")
    keys = set(re.findall(r"^([A-Z_]+)=", example, re.M))
    assert keys == {"MIRROR_ROOT", "PUBLISH_KEYS", "HUSARNET_JOIN_CODE", "HUSARNET_HOSTNAME", "HUSARNET_STATE"}
    assert re.search(r"^HUSARNET_JOIN_CODE=$", example, re.M) and "SECRET" in example
    assert "first join" in example
    dockerfile = _load("publish", "Dockerfile")
    arg = re.search(r"^ARG ALPINE_IMAGE=(\S+)$", dockerfile, re.M)
    assert arg and re.fullmatch(DIGEST, arg.group(1)) and arg.group(1).startswith("alpine:")
    assert re.search(r"^FROM \$\{ALPINE_IMAGE\}$", dockerfile, re.M)
    assert re.search(r"^USER 1000:1000$", dockerfile, re.M)
    # The mirror's own project is untouched by the door
    mirror = _compose()
    assert set(mirror["services"]) == {"files"} and "ports" not in mirror["services"]["files"]


def _bash():
    """bash for running publish/husarnet.sh: Git's on Windows (`bash` there may be WSL's)"""
    import shutil
    import sys
    if sys.platform == "win32":
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        return git_bash if os.path.isfile(git_bash) else None
    return shutil.which("bash")


def _bash_with_jq():
    """bash, where jq runs too (husarnet.sh reads the daemon's JSON with jq, as the sidecar's image has it)"""
    import subprocess
    bash = _bash()
    if not bash:
        pytest.skip("no bash")
    if subprocess.run([bash, "-c", "command -v jq"], capture_output=True).returncode != 0:
        pytest.skip("no jq beside bash (the sidecar's image has it; Linux CI has it)")
    return bash


# Husarnet's own servers in a status of the nightly daemon 2.0.349 (seen 2026-11-19), and its websetup host
API_SERVER = "fc94:9d15:7d86:cee1:46a2:2209:b58d:e52c"
EB_SERVER = "fc94:62c3:0cda:07e0:1cd4:64e1:a323:f0de"
WEBSETUP = "fc94:b01d:1803:8dd8:b293:5c7d:7639:932a"


def _daemon_status(peers: list = (), local: list = (), summary: bool = True, dashboard: bool = True,
                   base: str = "UDP", claimed: bool = False) -> bytes:
    """An answer of the nightly Husarnet daemon's GET /api/status in its form (2.0.349's
    core/husarnet/api_server/server.cpp: result.config.dashboard/license/user_config, result.live), with the
    fields husarnet.sh reads: the dashboard's peers, the local whitelist, Husarnet's servers, the health."""
    import json
    result = {
        "config": {
            "dashboard": {"claim_info": {"hostname": "", "owner": ""}, "is_claimed": claimed,
                          "peers": [{"address": a, "aliases": [], "hostname": "pc"} for a in peers]},
            "env": {"daemon_api_host": "127.0.0.1", "daemon_api_port": 16216},
            "license": {"api_servers": [API_SERVER], "eb_servers": [EB_SERVER], "websetup_host": WEBSETUP,
                        "base_server_addresses": ["192.0.2.1"]},
            "user_config": {"local-whitelist": list(local)},
        },
        "live": {"base_connection": {"address": "192.0.2.1", "port": 5582, "type": base},
                 "dashboard_connection": dashboard, "health": {"summary": summary},
                 "local_ip": "fc94:1111:2222:3333:4444:5555:6666:7777",
                 "peers": [{"address": EB_SERVER, "is_active": True}, {"address": API_SERVER, "is_active": True}]},
        "user_agent": "Husarnet,Linux,AMD64,2.0.349", "version": "2.0.349"}
    return json.dumps({"result": result, "status": "success"}, indent=4, sort_keys=True).encode()


def _fake_api(answer: dict):
    """A stand-in for the daemon's API on 127.0.0.1:<free port>, answering answer["body"]; with
    answer["seq"], each request after the first takes the next body of that list (the last one stays)."""
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            assert self.path == "/api/status"
            body = answer["body"]
            if answer.get("seq"):
                answer["body"] = answer["seq"].pop(0)
            self.send_response(200)
            self.send_header("Content-Type", "text/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_husarnet_health_means_up_with_a_peer_of_the_user():
    """publish/husarnet.sh health against a stand-in for the nightly daemon's API (U79): healthy only when
    live.health.summary and the control plane connection are true with a base connection, and an address
    of the user's is on the allow list (the dashboard's peers or the local whitelist), Husarnet's own
    servers not counting, also when written in another form; no daemon at all: unhealthy."""
    import subprocess

    bash = _bash_with_jq()
    answer = {"body": b""}
    server = _fake_api(answer)
    script = os.path.join(MIRROR, "publish", "husarnet.sh")

    def health(port: int) -> int:
        env = dict(os.environ, HUSARNET_DAEMON_API_PORT=str(port))
        return subprocess.run([bash, script, "health"], env=env, capture_output=True, timeout=60).returncode

    peer = "fc94:aaaa:bbbb:cccc:dddd:eeee:ffff:0001"
    port = server.server_address[1]
    try:
        for body, want in [(_daemon_status(peers=[peer]), 0), (_daemon_status(local=[peer]), 0),
                           (_daemon_status(), 1),
                           # Husarnet's own servers as peers, one compressed: not the user's
                           (_daemon_status(peers=[API_SERVER, "fc94:62c3:cda:7e0:1cd4:64e1:a323:f0de"], local=[WEBSETUP]), 1),
                           (_daemon_status(peers=[peer], summary=False), 1), (_daemon_status(peers=[peer], dashboard=False), 1),
                           (_daemon_status(peers=[peer], base="None"), 1), (_daemon_status(claimed=True), 1),
                           # the door's own address among the dashboard's peers: not a peer of the user's
                           (_daemon_status(peers=["fc94:1111:2222:3333:4444:5555:6666:7777"]), 1),
                           (b"", 1), (b"not json", 1)]:
            answer["body"] = body
            assert health(port) == want, body[:300]
    finally:
        server.shutdown()
        server.server_close()
    assert health(port) == 1   # nothing listening


def _stub(folder: str, name: str, body: str) -> None:
    path = os.path.join(folder, name)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/bash\n" + body)
    os.chmod(path, 0o755)


CODE = "dummy@example.com/NOTAJOINCODEdummy00000"
PEER = "fc94:aaaa:bbbb:cccc:dddd:eeee:ffff:0001"
FAILED_CLAIM = "ERROR:  API request failed. Message: invalid code"   # what the nightly CLI printed, exit status 0


@pytest.mark.parametrize("answers, code, claim_says, want_rc, want_join, want_line", [
    ("peer", "", "", 0, False, "joined before (claimed, or a peer on the allow list): no join"),
    ("claimed", "", "", 0, False, "joined before"),
    ("peer", CODE, "", 0, False, "joined before"),
    ("new", CODE, "", 0, True, ""),
    ("new", "", "", 1, False, "not joined (not claimed, no peer on the allow list) and no HUSARNET_JOIN_CODE"),
    # the daemon's kept state shows only from the third answer on (it is read in a thread of its own):
    # the 10 s re-check must see it, so no claim and no refusal
    ("late", "", "", 0, False, "joined before"),
    ("late", CODE, "", 0, False, "joined before"),
    # a refused claim (the CLI says so and exits 0): one line of husarnet.sh's own, never the CLI's text
    ("new", CODE, FAILED_CLAIM, 0, True, "husarnet.sh: the join request failed (husarnet claim)"),
    # no API at all (a short wait set by the test): no claim
    ("none", CODE, "", 0, False, "husarnet.sh: the daemon's API did not answer; no join"),
], ids=["peer-no-code", "claimed-no-code", "peer-with-code", "first-join", "neither", "late-state-no-code",
        "late-state-with-code", "claim-refused", "no-api"])
def test_husarnet_start_joins_once(tmp_path, answers, code, claim_says, want_rc, want_join, want_line):
    """publish/husarnet.sh start with stubs of husarnet-daemon and the husarnet CLI on PATH and a stand-in
    for the nightly daemon's API: a kept state (claimed, or a peer of the user's on the allow list) starts
    without a join, with or without the code, also when the daemon shows it only after a few answers (the
    10 s re-check); a new state and a code: one `husarnet claim <code> --hostname <name>`, the code never
    in the daemon's environment, a refused claim reported by husarnet.sh's own line; neither: the refusal
    line, exit 1; no API: no claim. The real nightly daemon did the joined, first-join and neither cases
    with a dummy code (the build's fix rounds 2 and 3)."""
    import subprocess

    bash = _bash_with_jq()
    new, joined = _daemon_status(), _daemon_status(peers=[PEER])
    bodies = {"peer": [joined], "claimed": [_daemon_status(claimed=True)], "new": [new], "late": [new, new, joined],
              "none": [new]}[answers]
    answer = {"body": bodies[0], "seq": bodies[1:]}
    server = _fake_api(answer)
    port = server.server_address[1]
    if answers == "none":   # a port where nothing listens
        server.shutdown()
        server.server_close()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = (tmp_path / "calls.txt").as_posix()
    # the daemon: counts the code's names and its secret part in its environment, lives 3 s; the CLI:
    # writes down its arguments and says what the test gives it
    _stub(str(bin_dir), "husarnet-daemon",
          'env | grep -cE "^(HUSARNET_JOIN_CODE|HUSARNET_JOINCODE|JOINCODE)=|NOTAJOINCODE" > '
          f'"{(tmp_path / "daemon-env.txt").as_posix()}"\nsleep 3\n')
    _stub(str(bin_dir), "husarnet", f'echo "$*" >> "{calls}"\necho "{claim_says}"\n')
    script = os.path.join(MIRROR, "publish", "husarnet.sh")
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}   # it would name the test's code
    env.update(HUSARNET_DAEMON_API_PORT=str(port), HUSARNET_JOIN_CODE=code, HUSARNET_HOSTNAME="door-test",
               HUSARNET_SH_API_WAIT="2")
    prefix = f'export PATH="$(cygpath -u "{bin_dir.as_posix()}" 2>/dev/null || echo "{bin_dir.as_posix()}"):$PATH"; '
    try:
        done = subprocess.run([bash, "-c", prefix + f'exec bash "{script}" start'.replace("\\", "/")], env=env,
                              capture_output=True, text=True, timeout=90)
    finally:
        if answers != "none":
            server.shutdown()
            server.server_close()
    lines = open(calls, encoding="utf-8").read().splitlines() if os.path.exists(calls) else []
    assert done.returncode == want_rc, (done.returncode, done.stderr)
    assert lines == ([f"claim {code} --hostname door-test"] if want_join else []), lines
    assert want_line in done.stderr
    assert "invalid code" not in done.stderr and "NOTAJOINCODE" not in done.stderr
    if not claim_says:
        assert "the join request failed" not in done.stderr
    assert open(tmp_path / "daemon-env.txt", encoding="utf-8").read().strip() == "0"   # no JOIN name reached the daemon


def test_publishing_door_sshd_and_gate():
    """Key only, one account, no root, no TTY, no forwarding of any kind, no user rc, the forced gate;
    the gate resolves the path and allows only the SFTP server and sha256sum of a regular file under
    /mirror."""
    lines = {line.strip() for line in _load("publish", "sshd_config").splitlines()
             if line.strip() and not line.startswith("#")}
    for line in ["AllowUsers publish", "PermitRootLogin no", "AuthenticationMethods publickey", "PasswordAuthentication no",
                 "PermitEmptyPasswords no", "KbdInteractiveAuthentication no", "PermitTTY no", "PermitUserRC no",
                 "DisableForwarding yes", "AllowTcpForwarding no", "AllowStreamLocalForwarding no", "AllowAgentForwarding no",
                 "X11Forwarding no", "PermitTunnel no", "ForceCommand /usr/local/bin/gate",
                 "AuthorizedKeysFile /keys/authorized_keys", "HostKey /keys/host/ssh_host_ed25519_key",
                 "Subsystem sftp /usr/lib/ssh/sftp-server"]:
        assert line in lines, line
    assert not any(line.split()[0] in ("Match", "PermitOpen", "PermitListen") for line in lines)
    gate = _load("publish", "gate.sh")
    assert "exec /usr/lib/ssh/sftp-server -u 022 -P symlink,hardlink" in gate
    assert 'resolved=$(readlink -f -- "$path" 2> /dev/null) || refuse' in gate
    assert '[ -f "$resolved" ] && [ ! -L "$resolved" ] || refuse' in gate
    assert 'exec sha256sum "$resolved"' in gate
    assert gate.rstrip().endswith("refuse")
    assert re.search(r"^MAX_REQUEST=\d+$", gate, re.M) and re.search(r"^MIRROR=/mirror$", gate, re.M)
    dockerfile = _load("publish", "Dockerfile")
    assert "COPY --chmod=0644 sshd_config /etc/ssh/sshd_config" in dockerfile
    assert "COPY --chmod=0755 gate.sh /usr/local/bin/gate" in dockerfile


def _map_regexes(name: str) -> list:
    """The regex sources of an nginx.conf map (Python's syntax for named groups)."""
    block = re.search(r"map \S+ \$" + name + r" \{(.*?)\n    \}", _nginx(), re.S)
    assert block, name
    return [re.compile(r.replace("(?<", "(?P<")) for r in re.findall(r'"~([^"]+)"', block.group(1))]


def _first(regexes: list, text: str, group: str, default: str) -> str:
    for regex in regexes:
        found = regex.search(text)
        if found:
            return found.group(group)
    return default


def test_log_dataset_and_version_forms():
    """Code review F2, the planner's ruling: ds only of a request for a served name, at most 40
    characters; v two or three numbers of at most three digits, optionally the word a, b, rc,
    .dev or .post (its number and a local label dropped), or "unknown"; anything else "other"."""
    ds = _map_regexes("mirror_dataset")
    for path, want in [("/v1/tiles/madeira/dtm/2m/0_0/1_2.tif", "madeira"), ("/v1/tiles/madeira/README.md", "madeira"),
                       ("/v1/tiles/slovakia/dmr5/1m/index.json", "slovakia"), ("/v1/tiles/aosta/dtm/0.5m/-1_0/-3_4.tif", "aosta"),
                       ("/v1/tiles/" + "a" * 300 + "-john-smith-192-168-1-20/x", "-"),
                       ("/v1/tiles/madeira-dtm-2m-0_0-1_2-tif/x", "-"), ("/v1/tiles/madeira/x", "-"),
                       ("/v1/tiles/" + "a" * 41 + "/README.md", "-"), ("/v1/datasets.json", "-"), ("/", "-")]:
        assert _first(ds, path, "ds", "-") == want, path
    v = _map_regexes("mirror_version")
    # The planner's rule (2026-11-16): the word after the numbers kept, its number and a local label
    # dropped; "unknown" kept; no written form of an address fits
    for agent, want in [("Find-a-Line/0.1.0 (highline finder; self-hosted)", "0.1.0"), ("Find-a-Line/0.2.0rc1 (x)", "0.2.0rc"),
                        ("Find-a-Line/1.0.0.dev3", "1.0.0.dev"), ("Find-a-Line/0.1.0+local (x)", "0.1.0"),
                        ("Find-a-Line/1.2.post4", "1.2.post"), ("Find-a-Line/2.1 (x)", "2.1"),
                        ("Find-a-Line/unknown (highline finder)", "unknown"), ("Find-a-Line/0.1.0+ip203x0x113x7", "0.1.0"),
                        ("Find-a-Line/203.0.113.77 (x)", "other"), ("Find-a-Line/203.0.113.dev7x", "other"),
                        ("Find-a-Line/madeira.dtm.2m.0.0.1.2", "other"), ("Find-a-Line/1.2.3.4.5", "other"),
                        ("Find-a-Line/1234.1.0", "other"), ("Find-a-Line/unknownx", "other"),
                        ("Mozilla/5.0 Find-a-Line/1.0.0", "other"), ("Find-a-Line/1.0.0-x", "other")]:
        assert _first(v, agent, "v", "other") == want, agent


def test_publishing_door_readme_checks_the_binding():
    """Code review F6, after U68: the README's install shows that neither of the door's containers
    publishes a port, and what to do if one does; the Husarnet network for the door alone, the
    whitelist's role quoted with its source, the join code a secret, the state folder 0700, the
    door's Husarnet address, the rclone host and known_hosts line for it."""
    readme = " ".join(_load("README.md").split())
    for words in ["docker port findaline-mirror-publish-sftp-1", "docker port findaline-mirror-publish-husarnet-1",
                  "docker compose down", "only the publishing PC and the door",
                  "it can send packets to current device", "husarnet.com/docs/cli-guide/, read 2026-11-19",
                  "Keep your join code secret!", 'install -d -m 0700 "$HSTATE"',
                  "docker compose exec husarnet husarnet status", "host = [<the door's Husarnet IP>]",
                  "[<the door's Husarnet IP>]:2222 ssh-ed25519", "never set `HUSARNET_DEBUG`",
                  "docker compose restart sftp", "docker compose build --pull", "husarnet-sidecar.Dockerfile",
                  "may be removed from `.env` after the first join", "docker inspect", "Docker Engine 28.0",
                  "docker version --format", "If the door does not answer"]:
        assert words in readme, words
    assert "docker compose port sftp" not in readme and "PUBLISH_ADDRESS" not in readme


def test_log_size_bound_and_readme_part_b():
    """U42-U45: the log folder's size bound beside the 14 days (the number is the user's); the README's
    default SWAG attachment by docker network connect with a check that shows when it is missing, the
    other way with its risk; the door's own log; "conn" covering both connection limits."""
    start = _load("start.sh")
    assert re.search(r"^LOG_CAP_BYTES=\d+$", start, re.M)
    assert 'cap_logs "${1:-$LOG_CAP_BYTES}"' in start and ': > "$LOGS/access-$_today.log"' in start
    readme = " ".join(_load("README.md").split())
    for words in ["docker network connect findaline-mirror_mirror swag", "NOT ATTACHED",
                  "cannot start while that network is missing", "502",
                  "the publishing PC's Husarnet address and the key's fingerprint",
                  "covers both the address's 4 and all visitors' 8", "fewer than 14 days"]:
        assert words in readme, words
