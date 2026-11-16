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
        assert f"location = /__refused/{code} {{ try_files /.none ={code}; }}" in conf
    assert "location / { try_files /.none =404; }" in conf and "location = /__not_found { try_files /.none =404; }" in conf
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


def _privacy_text() -> str:
    """The approved text for README and the landing page, from the specification's section 7."""
    with open(os.path.join(ROOT, "docs", "mirror-hosting", "spec.md"), encoding="utf-8") as f:
        spec = f.read()
    quoted = re.search(r"- README and the mirror's landing page: \"(.+?data\.)\"", spec, re.S)
    assert quoted
    return " ".join(quoted.group(1).replace("`", "").split())


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
    """The CI job `mirror` runs the check script with its self-test."""
    with open(os.path.join(ROOT, ".github", "workflows", "ci.yml"), encoding="utf-8") as f:
        jobs = yaml.safe_load(f)["jobs"]
    steps = " ".join(step.get("run", "") for step in jobs["mirror"]["steps"])
    assert "bash tests/mirror_check.sh --self-test" in steps


def test_publishing_door_compose():
    """The publishing door (publish/, the user's U32/U33): a second project with one service, its port
    on the LAN address only (required, never bare), <root> as one read-write mount, the keys
    read-only, nothing else of the host, a network of its own, the hardening list; the mirror's own
    project stays one service without a port."""
    compose = _compose(os.path.join("publish", "compose.yaml"))
    assert compose["name"] == "findaline-mirror-publish"
    assert set(compose["services"]) == {"sftp"}
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
    # The port: exactly on the address given, which compose requires
    assert len(service["ports"]) == 1
    assert re.fullmatch(r"\$\{PUBLISH_ADDRESS:\?[^}]*\}:\$\{PUBLISH_PORT:-2222\}:2222", service["ports"][0])
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
    assert service["networks"] == ["publish"]
    assert set(compose["networks"]) == {"publish"} and not compose["networks"]["publish"].get("internal")
    assert "external" not in compose["networks"]["publish"] and "name" not in compose["networks"]["publish"]
    keys = set(re.findall(r"^([A-Z_]+)=", _load("publish", ".env.example"), re.M))
    assert keys == {"MIRROR_ROOT", "PUBLISH_KEYS", "PUBLISH_ADDRESS", "PUBLISH_PORT"}
    assert re.search(r"^PUBLISH_ADDRESS=$", _load("publish", ".env.example"), re.M)
    dockerfile = _load("publish", "Dockerfile")
    arg = re.search(r"^ARG ALPINE_IMAGE=(\S+)$", dockerfile, re.M)
    assert arg and re.fullmatch(DIGEST, arg.group(1)) and arg.group(1).startswith("alpine:")
    assert re.search(r"^FROM \$\{ALPINE_IMAGE\}$", dockerfile, re.M)
    assert re.search(r"^USER 1000:1000$", dockerfile, re.M)
    # The mirror's own project is untouched by the door
    mirror = _compose()
    assert set(mirror["services"]) == {"files"} and "ports" not in mirror["services"]["files"]


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
    characters; v only of a version-shaped token (two or three numbers, a pre-release, .post, .dev
    and a local label starting with a letter, at most 24 characters), anything else "other"."""
    ds = _map_regexes("mirror_dataset")
    for path, want in [("/v1/tiles/madeira/dtm/2m/0_0/1_2.tif", "madeira"), ("/v1/tiles/madeira/README.md", "madeira"),
                       ("/v1/tiles/slovakia/dmr5/1m/index.json", "slovakia"), ("/v1/tiles/aosta/dtm/0.5m/-1_0/-3_4.tif", "aosta"),
                       ("/v1/tiles/" + "a" * 300 + "-john-smith-192-168-1-20/x", "-"),
                       ("/v1/tiles/madeira-dtm-2m-0_0-1_2-tif/x", "-"), ("/v1/tiles/madeira/x", "-"),
                       ("/v1/tiles/" + "a" * 41 + "/README.md", "-"), ("/v1/datasets.json", "-"), ("/", "-")]:
        assert _first(ds, path, "ds", "-") == want, path
    v = _map_regexes("mirror_version")
    for agent, want in [("Find-a-Line/0.2.0 (highline finder; self-hosted)", "0.2.0"), ("Find-a-Line/0.2.0rc1 (x)", "0.2.0rc1"),
                        ("Find-a-Line/1.0.0.dev3", "1.0.0.dev3"), ("Find-a-Line/0.1.0+local (x)", "0.1.0+local"),
                        ("Find-a-Line/2.1 (x)", "2.1"), ("Find-a-Line/203.0.113.77 (x)", "other"),
                        ("Find-a-Line/madeira.dtm.2m.0.0.1.2", "other"), ("Find-a-Line/1.2.3.4.5", "other"),
                        ("Find-a-Line/1.0+203.0.113.7", "other"), ("Find-a-Line/12345.1.0", "other"),
                        ("Find-a-Line/1.0.0+abcdefghijklmnopqrst", "other"), ("Mozilla/5.0 Find-a-Line/1.0.0", "other"),
                        ("Find-a-Line/1.0.0-x", "other")]:
        assert _first(v, agent, "v", "other") == want, agent


def test_publishing_door_readme_checks_the_binding():
    """Code review F6: the README's install shows where the door's port is really bound, and what
    0.0.0.0 or :: there means."""
    readme = _load("README.md")
    assert "docker compose port sftp 2222" in readme
    assert "`0.0.0.0:<port>` or `[::]:<port>`" in readme and "docker compose down" in readme
