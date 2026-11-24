"""The deployment files: what each service of compose.yaml may write and publish, and the files of
the host (deploy/nginx, deploy/fail2ban, deploy/firewall, deploy/monitoring): the fail2ban filter
and the masking of the access log, with Python's re (fail2ban's own engine; nginx's PCRE patterns
differ only in the spelling of named groups), the metrics log without addresses and its route
groups, the monitoring's bridge in the firewall, the monitoring's systemd units, the SSH login
notice (pam_exec) and the monthly renewal of the USA's index (its units, run in bash). nginx itself runs in tests/nginx_check.sh (CI, the docker job)."""

import configparser
import glob
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import pytest

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
    """Only the web service publishes ports, on the host's loopback: the site's (nginx on the host
    proxies to it, deploy/nginx/findaline-http.conf) and its metrics' (Telegraf on the host reads
    them, deploy/monitoring/telegraf.conf; nginx never proxies to them); its network has the fixed
    gateway that findaline.env.example trusts as the proxy."""
    services = _services()
    assert services["web"]["ports"] == '["127.0.0.1:${WEB_PORT:-8765}:8765", "127.0.0.1:${METRICS_PORT:-8766}:8766"]'
    assert "--metrics-port" not in services["web"]["command"]  # web --public's default: 8766
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
        "/api/events": "events", "/api/events/x": "api", "/api/patch": "patch", "/api/patchx": "api", "/api/jobs": "api", "/api/runs/x/share": "api",
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
    assert names == sorted([f"findaline-{name}.{kind}" for name in ("facts", "check", "heartbeat")
                            for kind in ("service", "timer")] + ["telegraf.service.d"])  # Telegraf's drop-in
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


def test_ssh_login_notice_installed():
    """D4: vps.sh installs deploy/monitoring/ssh-login.sh as a root-owned copy with the checkout's
    path and one `session optional` line of pam_exec in sshd's PAM stack (optional: the script's
    failure never refuses a login), and `check` looks for both."""
    vps = _read("vps.sh")
    assert "SSH_LOGIN_SCRIPT=/usr/local/sbin/findaline-ssh-login\n" in vps
    assert 'SSH_LOGIN_PAM="session optional pam_exec.so quiet $SSH_LOGIN_SCRIPT"\n' in vps
    assert 'put "$SSH_LOGIN_SCRIPT" 755 < <(sed "s#@REPO@#$REPO#g" "$DEPLOY/monitoring/ssh-login.sh")' in vps
    assert vps.count('grep -qxF "$SSH_LOGIN_PAM" /etc/pam.d/sshd') == 2   # installed and checked
    assert vps.count("ssh_login_notice") == 2   # defined and called by monitoring
    script = _read("monitoring", "ssh-login.sh")
    assert script.startswith("#!/bin/bash\n")
    assert "NTFY_URL_FILE=@REPO@/secrets/ntfy_url\n" in script   # the topic of Grafana's alerts
    assert re.search(r'^\[ "\$\{PAM_TYPE:-\}" = open_session \] \|\| exit 0$', script, re.M)
    assert script.rstrip().endswith("exit 0") and "set -e" not in script
    assert "setsid curl -fsS -m 5 " in script and "flock -w 2 9" in script


def _run_notice(tmp_path, pam_type, url=None):
    """The script with its folder and the checkout in tmp_path, run as pam_exec runs it"""
    out, repo = tmp_path / "out", tmp_path / "repo"
    (repo / "secrets").mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)
    if url is not None:
        (repo / "secrets" / "ntfy_url").write_text(url + "\n")
    script = tmp_path / "ssh-login"
    script.write_text(_read("monitoring", "ssh-login.sh").replace("@REPO@", str(repo))
                      .replace("OUT=/var/lib/findaline-monitoring", f"OUT={out}"))
    env = {"PAM_TYPE": pam_type, "PAM_USER": "op\nerator", "PAM_RHOST": "203.0.113.7", "PAM_SERVICE": "sshd"}
    started = time.monotonic()
    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, timeout=30)
    return result, time.monotonic() - started, out


@pytest.mark.skipif(sys.platform == "win32" or not shutil.which("flock") or not shutil.which("setsid"),
                    reason="the script is for the server (flock, setsid)")
def test_ssh_login_notice_runs(tmp_path):
    """The script counts the logins of open_session (not close_session) in ssh.json, sends the
    message to ntfy without making the login wait, and exits 0 when ntfy cannot be reached or its
    folder is missing."""
    posts = []

    class Ntfy(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            posts.append((self.headers.get("Title"), self.rfile.read(int(self.headers["Content-Length"])).decode()))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ntfy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/topic"
        for pam_type in ("open_session", "close_session", "open_session"):
            result, _, out = _run_notice(tmp_path, pam_type, url)
            assert result.returncode == 0 and not result.stdout and not result.stderr
        logins = json.loads((out / "ssh.json").read_text())
        assert logins["logins"] == 2 and abs(logins["time"] - time.time()) < 60
        for _ in range(50):
            if len(posts) == 2:
                break
            time.sleep(0.1)
        host = os.uname().nodename
        assert posts == [(f"SSH login on {host}", f"SSH login: operator from 203.0.113.7 on {host}")] * 2
    finally:
        server.shutdown()
    # ntfy not reachable (a closed port; an address that drops packets): the login does not wait
    for url in ("http://127.0.0.1:9/topic", "http://192.0.2.1/topic"):
        result, seconds, out = _run_notice(tmp_path, "open_session", url)
        assert result.returncode == 0 and seconds < 3, (url, seconds)
    assert json.loads((out / "ssh.json").read_text())["logins"] == 4
    # Its folder missing (a file in its place): nothing counted, still 0
    shutil.rmtree(out)
    out.write_text("")
    result = subprocess.run(["bash", str(tmp_path / "ssh-login")], env={"PAM_TYPE": "open_session"},
                            capture_output=True, timeout=30)
    assert result.returncode == 0


def test_osm_data_step():
    """vps.sh downloads the OSM world water polygons and the catalogue's Geofabrik extracts in the
    worker container with the app's own functions and commands (setup and update, after the start);
    the extracts it leaves out are among those of the catalogue."""
    vps = _read("vps.sh")
    body = vps[vps.index("osm_data() {"):vps.index("\nbackups() {")]
    assert "coast.world_polygons(\"/data/cache\")" in body
    assert "osm.catalogue_extracts(\"/data/cache\")" in body
    assert "compose exec -T worker python findaline.py osm download \"$region\"" in body
    for function in ("setup", "update"):
        steps = vps[vps.index(f"\n{function}() {{"):]
        steps = steps[:steps.index("\n}")]
        assert steps.index("start\n") < steps.index("osm_data\n"), function
    skipped = re.search(r"^OSM_EXTRACTS_SKIP=\((.*)\)$", vps, re.M).group(1).split()
    assert skipped == ["us", "canada", "nunavut", "british-columbia"]


def test_cache_migrate_step():
    """vps.sh update converts the cached tiles of an older encoding in the worker container with the
    app's own command, after the new image runs; tiles left over are listed, never a failure."""
    vps = _read("vps.sh")
    body = vps[vps.index("\ncache_migrate() {"):vps.index("\nbackups() {")]
    assert "compose exec -T worker python findaline.py cache migrate \\\n        || todo " in body
    steps = vps[vps.index("\nupdate() {"):]
    steps = steps[:steps.index("\n}")]
    assert steps.index("start\n") < steps.index("cache_migrate\n") < steps.index("monitoring\n")


def _bash():
    """bash for a test of vps.sh's functions: Git's on Windows (`bash` there may be WSL's)"""
    if sys.platform == "win32":
        git_bash = r"C:\Program Files\Git\bin\bash.exe"
        return git_bash if os.path.isfile(git_bash) else None
    return shutil.which("bash")


def test_secret_files_listed():
    """deploy/secrets.example holds a file for every Docker secret of both compose projects: vps.sh
    makes the files from it (secret_files), so a secret added to compose.yaml without its example
    would stop `docker compose up` on the server. Grafana's are GRAFANA_SECRETS, the monitoring's
    only; setup and update make the files before the services start, and check looks at them."""
    import yaml

    examples = set(os.listdir(os.path.join(DEPLOY, "secrets.example")))
    with open(os.path.join(ROOT, "compose.yaml"), encoding="utf-8") as f:
        app = set(yaml.safe_load(f)["secrets"])
    with open(os.path.join(DEPLOY, "monitoring", "compose.yaml"), encoding="utf-8") as f:
        monitoring = set(yaml.safe_load(f)["secrets"])
    assert app | monitoring == examples
    vps = _read("vps.sh")
    assert set(re.search(r"^GRAFANA_SECRETS=\(([^)]*)\)$", vps, re.M).group(1).split()) == monitoring
    assert not app & monitoring
    for function in ("settings", "update"):
        body = vps[vps.index(f"\n{function}() {{"):]
        body = body[:body.index("\n}")]
        assert "secret_files" in body, function
    update = vps[vps.index("\nupdate() {"):]
    update = update[:update.index("\n}")]
    assert update.index("secret_files") < update.index("\n    start\n")
    check = vps[vps.index("\ncheck() {"):]
    assert "secret_uid" in check[:check.index("\n}")]


@pytest.mark.skipif(_bash() is None, reason="no bash")
def test_secret_files(tmp_path):
    """secret_files on a server set up before some secrets existed: the missing files are made empty
    (with a note), those there keep their values, Grafana's go to uid 472, all others to the app's
    10001, each with mode 0400."""
    repo = tmp_path / "repo"
    (repo / "secrets").mkdir(parents=True)
    (repo / "secrets" / "findaline_session_secret").write_text("kept\n")
    (repo / "secrets" / "grafana_admin_password").write_text("also kept\n")
    script = tmp_path / "run.sh"
    # chown and chmod logged, not run: the test is no root (and a read-only file on Windows stays)
    script.write_text('source "$1"\nREPO=$2\nDEPLOY=$3\n'
                      'chown() { echo "chown $*" >> "$REPO/log"; }\n'
                      'chmod() { echo "chmod $*" >> "$REPO/log"; }\n'
                      'secret_files\n', newline="\n")
    result = subprocess.run([_bash(), script.as_posix(), os.path.join(DEPLOY, "vps.sh").replace("\\", "/"),
                             repo.as_posix(), DEPLOY.replace("\\", "/")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    examples = sorted(os.listdir(os.path.join(DEPLOY, "secrets.example")))
    assert sorted(os.listdir(repo / "secrets")) == examples
    assert (repo / "secrets" / "findaline_session_secret").read_text() == "kept\n"
    assert (repo / "secrets" / "grafana_admin_password").read_text() == "also kept\n"
    new = [n for n in examples if n not in ("findaline_session_secret", "grafana_admin_password")]
    assert all((repo / "secrets" / n).stat().st_size == 0 for n in new)
    assert result.stdout.splitlines() == [f"   secrets/{n}: a new, empty one (secrets/README.md)" for n in new]
    log = (repo / "log").read_text().splitlines()
    for name in examples:
        uid = 472 if name in ("grafana_admin_password", "ntfy_url") else 10001
        assert f"chown {uid}:{uid} {repo.as_posix()}/secrets/{name}" in log, name
        assert f"chmod 400 {repo.as_posix()}/secrets/{name}" in log, name
    assert len(log) == 2 * len(examples)


def test_usa_renewal_step():
    """The USA's 1 m index every week, what is older than 28 days (the user's answer of 2026-11-23; docs/deployment.md,
    section 13): a weekly calendar in one place (USA_RENEWAL_CALENDAR, the timer's only OnCalendar), the units
    installed in setup and update after the start and before the monitoring (Telegraf lists the timer for D1, and a
    timer it lists unloaded fires the alert), `check` running check_usa_renewal."""
    vps = _read("vps.sh")
    calendars = re.findall(r"^USA_RENEWAL_CALENDAR='([^']*)'$", vps, re.M)
    assert len(calendars) == 1 and re.fullmatch(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) \*-\*-\* \d\d:\d\d", calendars[0])
    assert vps.count(calendars[0]) == 1   # the calendar nowhere else
    body = vps[vps.index("\nusa_renewal() {"):]
    body = body[:body.index("\n}")]
    assert re.findall(r"^OnCalendar=.*$", body, re.M) == ["OnCalendar=$USA_RENEWAL_CALENDAR"]
    for function, before in (("setup", "backups"), ("update", "monitoring")):
        steps = vps[vps.index(f"\n{function}() {{"):]
        steps = steps[:steps.index("\n}")]
        assert steps.count("usa_renewal\n") == 1, function
        assert steps.index("start\n") < steps.index("usa_renewal\n") < steps.index(f"{before}\n"), function
        assert steps.index("usa_renewal\n") < steps.index("monitoring"), function
    check = vps[vps.index("\ncheck() {"):]
    assert "\n    check_usa_renewal\n" in check[:check.index("\n}")]
    assert re.search(r"^USA_RENEWAL=findaline-usa-renewal$", vps, re.M)
    with open(os.path.join(DEPLOY, "monitoring", "telegraf.conf"), encoding="utf-8") as f:
        assert "findaline-usa-renewal.timer" in re.findall(r'^  pattern = "(.*)"$', f.read(), re.M)[1].split()


def test_usa_renewal_weekly_and_28_days(tmp_path):
    """A weekly timer with `cache update usa`'s 28 days: the list and an answer checked by one run are not due at the
    next four weekly runs (7 to 28 days less the run's minutes: not more than 28) and due at the fifth (35), so each
    is renewed at day 35 when the timer renewed it, and one renewed between two runs (a search, a run by hand) at the
    first run after its 28 days: never later than day 35 (a run on the 1st of every month renewed nothing in three
    Marches of four: February has 28 days)."""
    import cache
    import update
    from sources.layers import tnmbucket as tb

    cache_dir = str(tmp_path / "cache")
    answer = os.path.join(cache_dir, "usa", "sheet-index", "dem1m", "N40.50_W112.00.json")
    os.makedirs(os.path.dirname(answer))
    with open(answer, "w", encoding="utf-8") as f:
        f.write('{"sheets": []}')
    cache.record(cache_dir, answer, url="https://tnmaccess.nationalmap.gov/api/v1/products")
    os.makedirs(os.path.dirname(tb.unlisted_path(cache_dir)))
    with open(tb.unlisted_path(cache_dir), "w", encoding="utf-8") as f:
        f.write("{}")
    cache.record(cache_dir, tb.unlisted_path(cache_dir), url=tb.BUCKET)
    due = {}
    for week in range(1, 7):
        age = week * 7 * 86400 - 10 * 60   # the next trigger, a run of 10 minutes after the one before
        db = cache._connect(cache_dir, "usa")
        with db:
            db.execute("UPDATE files SET checked_at = ?", (cache.now_iso(age),))
        db.close()
        paths = {c.path for c in update.checks(cache_dir, "usa")}
        due[week * 7] = (cache.relative(cache_dir, answer) in paths, cache.relative(cache_dir, tb.unlisted_path(cache_dir)) in paths)
    assert due == {7: (False, False), 14: (False, False), 21: (False, False), 28: (False, False),
                   35: (True, True), 42: (True, True)}
    # Renewed 3 days before a weekly run (a search's answer, a run by hand): due at the first run after its 28 days
    db = cache._connect(cache_dir, "usa")
    firsts = []
    for week in range(1, 7):
        with db:
            db.execute("UPDATE files SET checked_at = ?", (cache.now_iso((3 + (week - 1) * 7) * 86400),))
        if update.checks(cache_dir, "usa"):
            firsts.append(3 + (week - 1) * 7)
    db.close()
    assert firsts[0] == 31


def _renewal(tmp_path, runs, call="usa_renewal", notify=False):
    """`call` (usa_renewal by default) run once per item of `runs` (shell lines run before it) with the real put, its
    units in tmp_path/units and the script's state in tmp_path/state; systemctl a stand-in that logs its calls and
    keeps the timer's state in files (enabled, active, masked, failed: the service's last run; service-masked). Returns the folder of
    the units and, per run, its output and systemctl's calls."""
    units, state = tmp_path / "units", tmp_path / "state"
    units.mkdir(parents=True, exist_ok=True)
    if notify:
        (units / "notify-failure@.service").write_text("[Service]\nType=oneshot\nExecStart=/usr/bin/true %i\n")
    standin = '''
LOG=$3
systemctl() {
    echo "$*" >> "$LOG"
    local s
    case $1 in
        enable) touch "$UNITS/enabled" "$UNITS/active" ;;
        disable) rm -f "$UNITS/enabled" "$UNITS/active" ;;
        start) touch "$UNITS/active" ;;
        is-enabled)
            if [ "${*: -1}" = findaline-usa-renewal.service ]; then   # static, or masked (service-masked)
                if [ -f "$UNITS/service-masked" ]; then s=masked; else s=static; fi
                [ "$2" = -q ] || echo "$s"
                [ "$s" = static ]
                return
            fi
            if [ -f "$UNITS/masked" ]; then s=masked; elif [ -f "$UNITS/enabled" ]; then s=enabled
            elif [ -f "$UNITS/findaline-usa-renewal.timer" ]; then s=disabled; else return 1; fi
            [ "$2" = -q ] || echo "$s"
            [ "$s" = enabled ] ;;
        is-active) [ -f "$UNITS/active" ] ;;
        is-failed) [ -f "$UNITS/failed" ] ;;
        *) return 0 ;;
    esac
}
'''
    results = []
    for k, before in enumerate(runs):
        log = tmp_path / f"systemctl.{k}"
        script = tmp_path / "run.sh"
        script.write_text('source "$1"\nREPO=/srv/find-a-line-webui\nUNITS=$2\nNOTIFY_FAILURE=$UNITS/notify-failure@.service\n'
                          'MONITORING_DIR=$4\n' + standin + before + f"\n{call}\necho done\n", newline="\n")
        result = subprocess.run([_bash(), script.as_posix(), os.path.join(DEPLOY, "vps.sh").replace("\\", "/"),
                                 units.as_posix(), log.as_posix(), state.as_posix()],
                                capture_output=True, text=True, timeout=60)
        assert result.returncode == 0 and result.stdout.endswith("done\n"), result.stdout + result.stderr
        results.append((result.stdout + result.stderr, log.read_text().splitlines() if log.exists() else []))
    return units, results


@pytest.mark.skipif(_bash() is None, reason="no bash")
def test_usa_renewal_units(tmp_path):
    """The service runs `cache update usa` in the worker's container as cache_migrate does (compose exec -T), bounded
    inside the container (timeout: a killed client leaves its process running there) and by systemd a little longer;
    the timer once a week with a random delay fixed per machine and Persistent (a week missed while the server was off
    is caught up once). A second run changes nothing; OnFailure= only when the host has notify-failure@.service."""
    units, results = _renewal(tmp_path, ["", ""])
    (first, calls1), (second, calls2) = results
    assert "wrote" in first and calls1[0] == "daemon-reload" and "enable -q --now findaline-usa-renewal.timer" in calls1
    assert "no notify-failure@.service" in first
    assert "wrote" not in second and not [c for c in calls2 if c.startswith(("daemon-reload", "enable"))]
    service, timer = _unit_file(units / "findaline-usa-renewal.service"), _unit_file(units / "findaline-usa-renewal.timer")
    assert "OnFailure" not in service["Unit"] and service["Unit"]["After"] == "network-online.target docker.service"
    assert "28 days" in service["Unit"]["Description"] and "every week" in timer["Unit"]["Description"]
    assert service["Service"]["Type"] == "oneshot"
    start = service["Service"]["ExecStart"]
    repo = "/srv/find-a-line-webui"
    prefix = (f"/usr/bin/docker compose --project-directory {repo} -f {repo}/compose.yaml exec -T worker "
              f"timeout 6h sh -c '")
    assert start.startswith(prefix) and start.endswith("'"), start
    assert service["Service"]["TimeoutStartSec"] == "6h 10min"
    calendar = re.search(r"^USA_RENEWAL_CALENDAR='([^']*)'$", _read("vps.sh"), re.M).group(1)
    assert dict(timer["Timer"]) == {"OnCalendar": calendar, "RandomizedDelaySec": "4h",
                                    "FixedRandomDelay": "true", "Persistent": "true"}
    assert timer["Install"]["WantedBy"] == "timers.target"
    # The command inside the container: no folder of the USA, one line and success without the app; with it the app's
    # `cache update usa` and its exit code (1: a check failed; the unit fails)
    inner = start[len(prefix):-1]
    data = tmp_path / "data"
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "python").write_text('#!/bin/sh\necho "python $*"\nexit 1\n', newline="\n")
    os.chmod(bin_ / "python", 0o755)
    env = {**os.environ, "PATH": str(bin_) + os.pathsep + os.environ.get("PATH", "")}
    script = inner.replace("/data/cache/usa", (data / "cache" / "usa").as_posix())
    nothing = subprocess.run([_bash(), "-c", script], capture_output=True, text=True, timeout=30, env=env)
    assert (nothing.returncode, nothing.stdout) == (0, "No cached data of the USA: nothing to renew\n")
    (data / "cache" / "usa").mkdir(parents=True)
    update = subprocess.run([_bash(), "-c", script], capture_output=True, text=True, timeout=30, env=env)
    assert (update.returncode, update.stdout) == (1, "python findaline.py cache update usa\n")
    # notify-failure@.service on the host: the failed run reported (section 11)
    units, results = _renewal(tmp_path / "with", [""], notify=True)
    assert _unit_file(units / "findaline-usa-renewal.service")["Unit"]["OnFailure"] == "notify-failure@%N.service"
    assert "no notify-failure@.service" not in results[0][0]


@pytest.mark.skipif(_bash() is None, reason="no bash")
def test_usa_renewal_install_states(tmp_path):
    """"First install" is the marker usa-renewal.enabled, written after a successful enable: a first install that
    stopped before it (its file written, the enable failed or never ran) is enabled by the next run; a timer file
    removed by hand is written and enabled again; a timer the operator disabled stays off; a masked one is left alone
    (no write onto the /dev/null link) and setup or update goes on."""
    disable = "systemctl disable --now findaline-usa-renewal.timer"
    units, results = _renewal(tmp_path / "a", ["", disable, "", f"rm {(tmp_path / 'a' / 'units').as_posix()}/findaline-usa-renewal.timer"])
    assert (tmp_path / "a" / "state" / "usa-renewal.enabled").exists()
    assert "is off" in results[2][0] and not [c for c in results[2][1] if c.startswith("enable")]
    assert "enable -q --now findaline-usa-renewal.timer" in results[3][1] and (units / "enabled").exists()
    # The enable fails at the first install: listed, no marker; the next run enables it
    failing = 'systemctl() { echo "$*" >> "$LOG"; [ "$1" != enable ] && [ "$1" != is-enabled ]; }'
    units, results = _renewal(tmp_path / "b", [failing])
    assert "could not be enabled" in results[0][0] and not (tmp_path / "b" / "state" / "usa-renewal.enabled").exists()
    units, results = _renewal(tmp_path / "b", [""])
    assert "enable -q --now findaline-usa-renewal.timer" in results[0][1]
    assert (tmp_path / "b" / "state" / "usa-renewal.enabled").exists() and (units / "enabled").exists()
    # A run that stopped after writing the timer, before the enable (its file there, no marker)
    stopped = tmp_path / "c" / "units"
    stopped.mkdir(parents=True)
    (stopped / "findaline-usa-renewal.timer").write_text("[Timer]\nOnCalendar=weekly\n")
    units, results = _renewal(tmp_path / "c", [""])
    assert "enable -q --now findaline-usa-renewal.timer" in results[0][1]
    # Enabled but stopped (its service was masked at an elapse, then unmasked): update starts it
    stopped_timer = f"touch $UNITS/enabled; mkdir -p $MONITORING_DIR; touch $MONITORING_DIR/usa-renewal.enabled"
    units, results = _renewal(tmp_path / "f", ["", f"rm -f $UNITS/active; {stopped_timer}", ""])
    assert "start findaline-usa-renewal.timer" in results[1][1] and (units / "active").exists()
    assert not [c for c in results[2][1] if c.startswith("start")]
    # A failed enable removes the marker, also one of before (the timer file removed by hand): never off for good
    units, results = _renewal(tmp_path / "g", [""])
    marker = tmp_path / "g" / "state" / "usa-renewal.enabled"
    assert marker.exists()
    _renewal(tmp_path / "g", ["systemctl disable --now findaline-usa-renewal.timer; rm $UNITS/findaline-usa-renewal.timer; "
                              + failing])
    assert not marker.exists()
    units, results = _renewal(tmp_path / "g", [""])
    assert "enable -q --now findaline-usa-renewal.timer" in results[0][1] and (units / "enabled").exists()
    # Masked (the stand-in's link test): a note, nothing written, the script goes on
    masked = 'is_masked() { [ "$1" = "$UNITS/findaline-usa-renewal.timer" ]; }'
    units, results = _renewal(tmp_path / "d", [masked])
    assert "is masked: left alone" in results[0][0] and not results[0][1]
    assert not (units / "findaline-usa-renewal.timer").exists() and not (units / "findaline-usa-renewal.service").exists()
    if sys.platform != "win32":   # a real link to /dev/null, as `systemctl mask` makes it
        real = tmp_path / "e" / "units"
        real.mkdir(parents=True)
        os.symlink("/dev/null", real / "findaline-usa-renewal.timer")
        units, results = _renewal(tmp_path / "e", [""])
        assert "is masked: left alone" in results[0][0] and os.readlink(real / "findaline-usa-renewal.timer") == "/dev/null"


@pytest.mark.skipif(_bash() is None, reason="no bash")
def test_check_usa_renewal(tmp_path):
    """check's lines for the renewal, each outcome with its text: enabled and active (ok), enabled and not active
    (FAIL), disabled after its first install (a note) and before it (FAIL), masked (a note), missing (FAIL); a last run
    that failed (FAIL, with the journal's command) beside any of them; the service masked by the operator (a note,
    not the timer's "enabled but not active" it leads to)."""
    timer = "touch $UNITS/findaline-usa-renewal.timer"
    marker = "mkdir -p $MONITORING_DIR && touch $MONITORING_DIR/usa-renewal.enabled"
    cases = {
        "enabled, active": (f"{timer}; touch $UNITS/enabled $UNITS/active", "ok: findaline-usa-renewal.timer", 0),
        "enabled, not active": (f"{timer}; touch $UNITS/enabled", "FAIL: findaline-usa-renewal.timer is enabled but not active", 1),
        "disabled": (f"{timer}; {marker}", "findaline-usa-renewal.timer: turned off (section 13)", 0),
        "never enabled": (timer, "FAIL: findaline-usa-renewal.timer was installed but never enabled", 1),
        "masked": ("touch $UNITS/masked", "findaline-usa-renewal.timer: masked by the operator", 0),
        "missing": ("", "FAIL: findaline-usa-renewal.timer is not installed", 1),
        "service masked": (f"{timer}; {marker}; touch $UNITS/enabled $UNITS/service-masked",
                           "findaline-usa-renewal.service: masked by the operator (section 13)", 0),
        "failed run": (f"{timer}; touch $UNITS/enabled $UNITS/active $UNITS/failed",
                       "FAIL: findaline-usa-renewal.service: its last run failed: journalctl -u findaline-usa-renewal.service", 1),
    }
    for k, (name, (before, text, failed)) in enumerate(cases.items()):
        _, results = _renewal(tmp_path / str(k), [before], call='check_usa_renewal; echo "FAILED=$FAILED"')
        out = results[0][0]
        assert text in out and f"FAILED={failed}" in out, (name, out)
        assert name != "service masked" or "not active" not in out, out
        if name != "failed run":
            assert "last run failed" not in out, (name, out)


def _unit_file(path):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser


def test_push_cube_script(tmp_path):
    """deploy/push-cube.sh holds no ssh details (address, user, key, port: they come from the
    caller's ssh configuration), and refuses an id that could break out of the remote command or
    a missing cube before any connection is made."""
    script = os.path.join(DEPLOY, "push-cube.sh")
    with open(script, encoding="utf-8", newline="") as f:
        text = f.read()
    assert "\r" not in text
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b|root@|\w@\w|lukawski|id_(rsa|ed25519)|\.pem|BEGIN [A-Z ]*KEY"
                         r"|\bssh\b[^\n#]* -[ip] |\bssh\b[^\n#]* -p ", text)
    bash = _bash()
    if bash is None:
        pytest.skip("no bash")
    fake = tmp_path / "ssh"
    fake.write_text("#!/bin/sh\necho ssh was called >&2\nexit 99\n")
    fake.chmod(0o755)
    env = {**os.environ, "SSH": str(fake)}

    def run(*args):
        return subprocess.run([bash, script, *args], env=env, capture_output=True, text=True)

    assert run().returncode == 2
    bad = run("host", "../etc", str(tmp_path))
    assert bad.returncode == 2 and "not a country id" in bad.stderr
    missing = run("host", "nowhere", str(tmp_path))
    assert missing.returncode == 1 and "no cube" in missing.stderr
    assert "ssh was called" not in bad.stderr + missing.stderr


def _tree(folder) -> dict:
    """The files under a folder by their path relative to it (with /), and their bytes."""
    out = {}
    for root, _, names in os.walk(folder):
        for name in names:
            path = os.path.join(root, name)
            with open(path, "rb") as f:
                out[os.path.relpath(path, folder).replace(os.sep, "/")] = f.read()
    return out


def test_push_cube_copies_the_named_build(tmp_path):
    """deploy/push-cube.sh against a stand-in server (a fake ssh that runs the remote command here, with /data/countries
    a folder of the test, and a fake docker that runs what `docker exec` is given): it copies cube.json, area.geojson
    and the build folder cube.json names, not an earlier build, a half-written one or a stray file; swaps the folder
    in (a second push replaces the first: no file of the first stays); compares the sums of every file copied; a cube
    built before the build folders (the fixed-name arrays beside cube.json) still goes; a cube.json naming no build
    folder, or one that is not there, is refused before any connection."""
    sys.path.insert(0, ROOT)
    import countcube as cc
    bash = _bash()
    if bash is None:
        pytest.skip("no bash")
    data, server, fakes = tmp_path / "data", tmp_path / "server", tmp_path / "bin"
    fakes.mkdir()
    (fakes / "ssh").write_text('#!/bin/sh\nfor last; do :; done\n'  # the remote command: the last argument
                               'exec sh -c "$(printf "%s" "$last" | sed "s#/data/countries#$FAKE_ROOT#g")"\n',
                               newline="\n")
    (fakes / "docker").write_text('#!/bin/sh\n[ "$1" = exec ] || exit 98\nshift\n[ "$1" = -i ] && shift\nshift\n'
                                  'exec "$@"\n', newline="\n")
    for name in ("ssh", "docker"):
        (fakes / name).chmod(0o755)
    env = {**os.environ, "SSH": (fakes / "ssh").as_posix(), "FAKE_ROOT": (server / "countries").as_posix(),
           "PATH": str(fakes) + os.pathsep + os.environ["PATH"]}
    script = os.path.join(DEPLOY, "push-cube.sh")

    def push():
        return subprocess.run([bash, script, "host", "testland", str(data)], env=env, capture_output=True, text=True,
                              timeout=120)
    cube = data / "countries" / "testland" / "cube"
    cc.build([], str(cube), {"origin": [1, 2]})
    built = cc.build([], str(cube), {"origin": [1, 2], "id": "testland"})  # the build before it removed
    (cube / "area.geojson").write_text('{"type": "Polygon", "coordinates": []}')
    for stale in ("build-20200101T000000.000000Z-0123abcd", "build-29990101T000000.000000Z-0123abcd"):
        (cube / stale).mkdir()  # an earlier build left behind, a half-written one
        (cube / stale / "lines_1.npy").write_bytes(b"stale")
    (cube / "notes.txt").write_text("not a cube's")
    done = push()
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Done: 10 files, sha256 identical." in done.stdout
    wanted = {"cube.json", "area.geojson", *(f"{built['arrays']}/{n}" for n in cc.ARRAY_FILES)}
    local = _tree(cube)
    there = _tree(server / "countries" / "testland" / "cube")
    assert set(there) == wanted and all(there[k] == local[k] for k in wanted)
    assert sorted(os.listdir(server / "countries" / "testland")) == ["cube"]  # swapped in, nothing beside
    # a cube built before the build folders: the fixed names beside cube.json
    for name in cc.ARRAY_FILES:
        os.replace(cube / built["arrays"] / name, cube / name)
    info = json.loads((cube / "cube.json").read_text())
    del info["arrays"]
    (cube / "cube.json").write_text(json.dumps(info))
    done = push()
    assert done.returncode == 0, done.stdout + done.stderr
    there = _tree(server / "countries" / "testland" / "cube")
    assert set(there) == {"cube.json", "area.geojson", *cc.ARRAY_FILES}  # the first push's build folder is gone
    assert all(there[k] == _tree(cube)[k] for k in there)
    # refused before any connection: a name off the pattern, a build folder that is not there
    for arrays in ("../../etc", "build-20200101T000000.000000Z-0123abcd"):
        (cube / "cube.json").write_text(json.dumps({**info, "arrays": arrays}))
        if arrays.startswith("build"):
            for name in cc.ARRAY_FILES:
                os.remove(cube / name)
            os.rename(cube / arrays, tmp_path / "gone")
        refused = push()
        assert refused.returncode == 1 and ("no build folder" in refused.stderr or "no arrays" in refused.stderr), \
            refused.stdout + refused.stderr
        assert "Copying" not in refused.stdout
