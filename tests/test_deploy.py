"""The deployment files: what each service of compose.yaml may write and publish, and the files of
the host (deploy/nginx, deploy/fail2ban, deploy/firewall, deploy/monitoring): the fail2ban filter
and the masking of the access log, with Python's re (fail2ban's own engine; nginx's PCRE patterns
differ only in the spelling of named groups), the metrics log without addresses and its route
groups, the monitoring's bridge in the firewall, the monitoring's systemd units and the SSH login
notice (pam_exec). nginx itself runs in tests/nginx_check.sh (CI, the docker job)."""

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
