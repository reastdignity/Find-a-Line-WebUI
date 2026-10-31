"""The deployment files: what each service of compose.yaml may write and publish, and the files of
the host (deploy/nginx, deploy/fail2ban, deploy/firewall, deploy/monitoring): the fail2ban filter
and the masking of the access log, with Python's re (fail2ban's own engine; nginx's PCRE patterns
differ only in the spelling of named groups), the metrics log without addresses and its route
groups, the monitoring's bridge in the firewall and the monitoring's systemd units. nginx itself
runs in tests/nginx_check.sh (CI, the docker job)."""

import configparser
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY = os.path.join(ROOT, "deploy")
HOST = r"(?P<host>[0-9A-Fa-f:.]+|[\w\-.^_]*\w)"  # what fail2ban puts for <HOST> (simplified)


def _filter():
    """The failregex and ignoreregex lines of the filter, compiled."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(os.path.join(DEPLOY, "fail2ban", "findaline.conf"), encoding="utf-8")
    return [[re.compile(line.strip().replace("<HOST>", HOST))
             for line in parser["Definition"][key].splitlines() if line.strip()]
            for key in ("failregex", "ignoreregex")]


def _line(status, request='GET /api/jobs HTTP/2.0', ip="203.0.113.7", referer="-"):
    return (f'{ip} - - [28/Oct/2026:11:40:02 +0100] "{request}" {status} 31 "{referer}" '
            f'"Mozilla/5.0 (X11; Linux x86_64) \\x22quoted\\x22 401"')  # nginx escapes " as \x22


def test_fail2ban_filter():
    """Refusals (401, 403, 429) count, with the client's address; nothing else does, also not a 401
    in the size, the referer or the user agent of another answer; nor a 429 of an orthophoto tile."""
    regexes, ignored = _filter()

    def host(line):
        if any(regex.search(line) for regex in ignored):
            return None
        for regex in regexes:
            match = regex.search(line)
            if match:
                return match.group("host")
        return None

    for status in (401, 403, 429):
        assert host(_line(status)) == "203.0.113.7"
    assert host(_line(429, "POST /api/estimate HTTP/1.1", ip="2001:db8::5")) == "2001:db8::5"
    assert host(_line(401, "GET /s/<token>/data.js HTTP/2.0")) == "203.0.113.7"
    tile = "GET /cache/poland/ortho/live/wm256/13/4551/2774.jpg HTTP/2.0"
    assert host(_line(429, tile)) is None
    assert host(_line(403, tile)) == "203.0.113.7"
    assert host(_line(429, "GET /api/x?next=/cache/a HTTP/2.0")) == "203.0.113.7"
    assert host(_line(429, "GET /api/x HTTP/2.0", referer="https://findaline.example.org/cache/a"))         == "203.0.113.7"
    for status in (200, 204, 301, 304, 400, 404, 500, 502, 503):
        assert host(_line(status)) is None, status
    assert host(_line(200, 'GET /api/x" 401 0 "x HTTP/2.0'.replace('"', '\\x22'))) is None  # nginx escapes "
    assert host(_line(200, referer="https://findaline.example.org/ 401 ")) is None
    assert host('203.0.113.7 - - [28/Oct/2026:11:40:02 +0100] "\\x16\\x03\\x01" 400 157 "-" "-"') is None


def _maps():
    """The map blocks of the http part: {variable: [(regex, value)]}, PCRE groups as Python's."""
    with open(os.path.join(DEPLOY, "nginx", "findaline-http.conf"), encoding="utf-8") as f:
        text = f.read()
    maps = {}
    for source, target, body in re.findall(r"map \$(\w+) \$(\w+) \{(.*?)\n\}", text, re.S):
        entries = re.findall(r'^\s*"~(.*)" "(.*)";$', body, re.M)
        maps[target] = (source, [(re.compile(p.replace("(?<", "(?P<")), v) for p, v in entries])
    return maps


def _masked(maps, variable, value):
    for regex, template in maps[variable][1]:
        match = regex.search(value)
        if match:
            return re.sub(r"\$\{(\w+)\}", lambda m: match.group(m.group(1)) or "", template)
    return value


def test_access_log_masking():
    """Share tokens and the query of a sign-in callback never reach the log; the viewer's files
    and the other paths stay as they are."""
    maps = _maps()
    assert {name: source for name, (source, _) in maps.items()} == {
        "findaline_request": "request", "findaline_referer": "http_referer", "findaline_group": "uri"}
    token = "-Ab_9" + "x" * 38
    request = lambda path: _masked(maps, "findaline_request", f"GET {path} HTTP/2.0")  # noqa: E731
    assert request(f"/s/{token}/data.js") == "GET /s/<token>/data.js HTTP/2.0"
    assert request(f"/s/{token}/") == "GET /s/<token>/ HTTP/2.0"
    assert request(f"/s/{token}") == "GET /s/<token> HTTP/2.0"
    assert request(f"/s/{token}/map.html?x=1") == "GET /s/<token>/map.html?x=1 HTTP/2.0"
    assert request("/auth/github?code=abc&state=def") == "GET /auth/github?<query> HTTP/2.0"
    for path in ("/s/_viewer/viewer.js", "/s/runs.js", "/s/index.html", "/s/runs.js?v=2", "/api/jobs",
                 "/runs/x/data.js", "/login/github?next=/", "/"):
        assert request(path) == f"GET {path} HTTP/2.0"
    referer = lambda url: _masked(maps, "findaline_referer", url)  # noqa: E731
    assert referer(f"https://findaline.example.org/s/{token}/map.html") == \
        "https://findaline.example.org/s/<token>/map.html"
    for url in ("https://findaline.example.org/s/_viewer/map.html", "https://findaline.example.org/app/", "-"):
        assert referer(url) == url


def _services():
    """The services of compose.yaml (its own layout, without a YAML library): {name: {"volumes":
    [(source, target, options)], "environment": {name: value}, key: value}}; a tmpfs mount is
    ("tmpfs", target, ""); an inline list (`ports: [...]`) stays the text of the list."""
    with open(os.path.join(ROOT, "compose.yaml"), encoding="utf-8") as f:
        lines = [line.split(" #")[0].rstrip() for line in f.read().splitlines()]
    services, current, section = {}, None, None
    for line in lines[lines.index("services:") + 1:]:
        if line and not line.startswith(" "):
            break  # the next top-level key
        if re.fullmatch(r"  [\w-]+:", line):
            current = services[line.strip()[:-1]] = {"volumes": [], "environment": {}, "ports": "[]"}
        elif current is None or not line.strip() or line.strip().startswith("#"):
            continue
        elif match := re.fullmatch(r"    ([\w-]+):(?: (.*))?", line):
            section = match.group(1)
            if match.group(2):
                current[section] = match.group(2)
        elif section == "volumes" and line.startswith("      - "):
            item = line[8:]
            short = re.fullmatch(r"(.+?):(/[^:]*)(?::(\w+))?", item)  # source:target[:options]
            current["volumes"].append(("tmpfs", None, "") if item == "type: tmpfs"
                                      else (short.group(1), short.group(2), short.group(3) or ""))
        elif section == "volumes" and (match := re.fullmatch(r"        target: (\S+)", line)):
            current["volumes"][-1] = ("tmpfs", match.group(1), "")
        elif section == "environment" and (match := re.fullmatch(r"      (\w+): (.*)", line)):
            current["environment"][match.group(1)] = match.group(2)
    return services


def test_compose_volumes():
    """What each service can write (docs/deployment.md, "What each service can write"): the
    accounts volume is the web service's only; numba's compiled code, the home and matplotlib's
    settings are in each service's own tmpfs, never in the shared data volume; no swap beyond the
    memory limit."""
    services = _services()
    assert set(services) == {"web", "worker"}
    web, worker = services["web"], services["worker"]
    assert web["volumes"] == [("data", "/data", ""), ("accounts", "/accounts", ""), ("tmpfs", "/tmp", "")]
    assert worker["volumes"] == [("data", "/data", ""), ("${FINDALINE_MIRROR_DIR:-no-mirror}", "/mirror", "ro"),
                                 ("tmpfs", "/tmp", "")]
    assert web["environment"]["FINDALINE_ACCOUNTS_DIR"] == "/accounts"
    assert "FINDALINE_ACCOUNTS_DIR" not in worker["environment"]
    for service in (web, worker):
        for name in ("HOME", "NUMBA_CACHE_DIR", "MPLCONFIGDIR"):
            assert service["environment"][name].startswith("/tmp/"), name
        assert service["memswap_limit"] == service["mem_limit"]


def test_compose_ports():
    """Only the web service publishes a port, on the host's loopback (nginx on the host proxies to
    it, deploy/nginx/findaline-http.conf); its network has the fixed gateway that
    findaline.env.example trusts as the proxy."""
    services = _services()
    assert services["web"]["ports"] == '["127.0.0.1:${WEB_PORT:-8765}:8765"]'
    assert services["worker"]["ports"] == "[]"
    with open(os.path.join(ROOT, "compose.yaml"), encoding="utf-8") as f:
        assert "gateway: 172.30.0.1" in f.read()
    with open(os.path.join(ROOT, "findaline.env.example"), encoding="utf-8") as f:
        assert "FINDALINE_TRUSTED_PROXY=172.30.0.1\n" in f.read()
    with open(os.path.join(DEPLOY, "nginx", "findaline-http.conf"), encoding="utf-8") as f:
        assert "server 127.0.0.1:8765;" in f.read()


def _read(*path):
    with open(os.path.join(DEPLOY, *path), encoding="utf-8") as f:
        return f.read()


def test_metrics_log_format():
    """The metrics log (docs/monitoring.md, C1-C3; parsed by deploy/monitoring/telegraf.conf) holds
    one JSON object per request with the fields of the contract and no address of any kind: no
    client address, X-Forwarded-For, path, query, Referer or User-Agent."""
    text = _read("nginx", "findaline-http.conf")
    match = re.search(r"log_format findaline_metrics escape=json ((?:'[^']*'\s*)+);", text)
    assert match, "log_format findaline_metrics escape=json '...'"
    fmt = "".join(re.findall(r"'([^']*)'", match.group(1)))
    variables = set(re.findall(r"\$(\w+)", fmt))
    assert variables == {"msec", "findaline_group", "request_method", "status", "request_time",
                         "upstream_response_time", "body_bytes_sent", "limit_req_status"}
    # Values as nginx writes them, the strings escaped by escape=json
    sample = {"msec": "1761900000.123", "findaline_group": "api", "request_method": "GET",
              "status": "200", "request_time": "0.004", "upstream_response_time": "0.004, 0.001",
              "body_bytes_sent": "312", "limit_req_status": ""}
    line = re.sub(r"\$(\w+)", lambda m: sample[m.group(1)], fmt)
    assert json.loads(line) == {"time": 1761900000.123, "group": "api", "method": "GET", "status": 200,
                                "request_time": 0.004, "upstream_time": "0.004, 0.001", "bytes": 312,
                                "limit": ""}
    # Its log in the site's server of port 443 only (not www's redirect, not port 80, not the
    # default servers that refuse other names)
    log = "access_log /var/log/nginx/findaline.metrics.log findaline_metrics;"
    servers = re.split(r"\nserver \{", _read("nginx", "findaline.conf"))
    assert [server.count(log) for server in servers[1:]] == [0, 0, 1]
    assert "findaline_metrics" not in _read("nginx", "findaline-acme.conf")


def _group(uri):
    """$findaline_group for a path as nginx's map gives it: exact strings first, then the patterns
    in their order, else the default."""
    text = _read("nginx", "findaline-http.conf")
    body = re.search(r"map \$uri \$findaline_group \{(.*?)\n\}", text, re.S).group(1)
    entries = re.findall(r'^\s*"(.*)" "(.*)";$', body, re.M)
    exact = {key: value for key, value in entries if not key.startswith("~")}
    if uri in exact:
        return exact[uri]
    for key, value in entries:
        if key.startswith("~") and re.search(key[1:], uri):
            return value
    return re.search(r'^\s*default "(.*)";$', body, re.M).group(1)


def test_metrics_log_groups():
    """The route groups of the metrics log: a handful of values, never the path itself."""
    expected = {
        "/api/events": "events", "/api/events/x": "api", "/api/jobs": "api", "/api/runs/x/share": "api",
        "/cache/poland/ortho/live/wm256/13/4551/2774.jpg": "cache", "/s/<token>/map.html": "share",
        "/s/_viewer/viewer.js": "share", "/login/github": "auth", "/auth/github": "auth", "/logout": "auth",
        "/loginx": "page", "/app/app.js": "app", "/runs/x/data.js": "app", "/runs/runs.js": "app",
        "/": "page", "/privacy": "page", "/about": "page", "/favicon.ico": "page", "/apps": "page",
    }
    assert {uri: _group(uri) for uri in expected} == expected


def test_stub_status_on_loopback():
    """nginx's stub_status listens on the host's loopback only, in a server of its own."""
    text = _read("nginx", "findaline-http.conf")
    assert re.findall(r"^\s*listen (\S+?)[ ;]", text, re.M) == ["127.0.0.1:8081"]
    assert "stub_status;" in text[text.index("listen 127.0.0.1:8081;"):]
    assert "stub_status" not in _read("nginx", "findaline.conf") + _read("nginx", "findaline-acme.conf")


def test_firewall_monitoring_bridge():
    """The monitoring's network (br-fal-mon, deploy/monitoring/compose.yaml) talks within itself
    like the site's two; the drops of br-fal-+ come after the three RETURN lines."""
    lines = _read("firewall", "ufw-after.rules").splitlines()
    returns = [f"-A DOCKER-USER -i {bridge} -o {bridge} -j RETURN"
               for bridge in ("br-fal-web", "br-fal-worker", "br-fal-mon")]
    for line in returns:
        assert line in lines
    first_drop = next(i for i, line in enumerate(lines) if line.endswith("-j DROP"))
    assert max(lines.index(line) for line in returns) < first_drop


def _unit(name):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(os.path.join(DEPLOY, "monitoring", "systemd", name), encoding="utf-8")
    return parser


def test_monitoring_units():
    """The units deploy/vps.sh installs: three timers with their services (Grafana's alert on
    failed units names the facts and heartbeat timers, docs/monitoring.md D1), the scripts by the
    checkout's path (@REPO@), the heartbeat as a throwaway user without capabilities."""
    names = sorted(os.path.basename(path) for path in glob.glob(os.path.join(DEPLOY, "monitoring", "systemd", "*")))
    assert names == sorted(f"findaline-{name}.{kind}" for name in ("facts", "check", "heartbeat")
                           for kind in ("service", "timer"))
    calendars = {"facts": "*:0/5", "check": "*-*-* 06:00", "heartbeat": "minutely"}
    for name, calendar in calendars.items():
        timer, service = _unit(f"findaline-{name}.timer"), _unit(f"findaline-{name}.service")
        assert timer["Timer"]["OnCalendar"] == calendar
        assert timer["Install"]["WantedBy"] == "timers.target"
        assert service["Service"]["Type"] == "oneshot"
        start = service["Service"]["ExecStart"]
        assert re.fullmatch(r"/bin/bash @REPO@/deploy/monitoring/(facts|heartbeat)\.sh( check)?", start), start
        script = start.split()[1].replace("@REPO@/deploy/", "")
        assert os.path.isfile(os.path.join(DEPLOY, script)), script
        assert service["Service"]["NoNewPrivileges"] == "yes"
    heartbeat = _unit("findaline-heartbeat.service")["Service"]
    assert heartbeat["DynamicUser"] == "yes" and heartbeat["CapabilityBoundingSet"] == ""
    assert heartbeat["EnvironmentFile"] == "-/etc/findaline-monitoring.env"
    facts = _unit("findaline-facts.service")["Service"]
    assert facts["CapabilityBoundingSet"] == "" and facts["PrivateNetwork"] == "yes"
    assert facts["StateDirectory"] == "findaline-monitoring"
    # vps.sh: the same timers enabled and checked, the backup's unit with the ping URL's file
    vps = _read("vps.sh")
    assert "MONITORING_TIMERS=(findaline-facts.timer findaline-check.timer findaline-heartbeat.timer)" in vps
    assert "EnvironmentFile=-$MONITORING_ENV" in vps and "MONITORING_ENV=/etc/findaline-monitoring.env" in vps
