"""The monitoring project (deploy/monitoring, docs/monitoring.md): what its compose file publishes
and how its services are hardened, that Telegraf keeps addresses, users and paths out of its tags,
sends the log lines only to VictoriaLogs (addresses masked) and the samples only to
VictoriaMetrics, and that Grafana's provisioning is valid, names the provisioned data sources
everywhere and asks only for the application's metrics of the phase-2 and phase-3 contracts
(metrics.py). The stack itself runs in CI (the monitoring job)."""

import json
import os
import re
import tomllib

import pytest

yaml = pytest.importorskip("yaml")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONITORING = os.path.join(ROOT, "deploy", "monitoring")
GRAFANA = os.path.join(MONITORING, "grafana")
DATASOURCE = "victoriametrics"
LOGS_DATASOURCE = "victorialogs"
SERVICES = {"telegraf", "victoriametrics", "victorialogs", "grafana", "socket-proxy"}
DASHBOARDS = ["findaline", "logs", "site", "vps"]
# The measurements of the log lines: to VictoriaLogs only
LOG_MEASUREMENTS = ["docker_log", "nginx_error"]
# The application's /metrics (metrics.py, docs/monitoring.md rows F): every name as it is exposed,
# with its labels (Telegraf adds `host`)
APP_METRICS = {
    "findaline_build_info": {"version"},
    "findaline_workers_alive": set(),
    "findaline_worker_lease_age_seconds": set(),
    "findaline_jobs": {"status"},
    "findaline_queue_max": set(),
    "findaline_slots": {"phase"},
    "findaline_job_oldest_waiting_seconds": set(),
    "findaline_jobs_finished_total": {"status", "error"},
    "findaline_job_duration_seconds_sum": {"status"},
    "findaline_job_duration_seconds_count": {"status"},
    "findaline_job_phase_seconds_sum": {"phase"},
    "findaline_job_phase_seconds_count": {"phase"},
    "findaline_quick_waiting": set(),
    "findaline_quick_oldest_waiting_seconds": set(),
    "findaline_quick_answers_total": {"result"},
    "findaline_users": {"status"},
    "findaline_users_by_country": {"country"},
    "findaline_users_searched_in": {"country"},
    "findaline_sessions_active": {"window"},
    "findaline_audit_events_last_hour": {"action"},
    "findaline_refusals_last_hour": {"kind"},
    "findaline_reports_open": set(),
    "findaline_runs": set(),
    "findaline_runs_bytes": set(),
    "findaline_cache_bytes": {"folder"},
    "findaline_free_disk_bytes": set(),
    "findaline_area_km2_total": {"country"},
    "findaline_searches_total": {"country"},
    "findaline_favourites": set(),
    # Phase 3 (F11-F13, F17): `host` of the outside services is the application's label
    "findaline_service_requests_total": {"host", "outcome"},
    "findaline_service_bytes_total": {"host"},
    "findaline_service_seconds_total": {"host"},
    "findaline_http_requests_total": {"route", "method", "status"},
    "findaline_http_request_seconds_sum": {"route"},
    "findaline_http_request_seconds_count": {"route"},
    "findaline_event_streams": set(),
    "findaline_housekeeping_removed": {"what"},
    "findaline_housekeeping_last_run_timestamp_seconds": set(),
    "findaline_housekeeping_seconds": set(),
    "findaline_coverage_km2": set(),
    "findaline_searches_by_cell": {"lat", "lon"},
}
# The measurements of the host's files (phase 1; ssh.json phase 3): findaline_facts_*,
# findaline_check_*, findaline_backup_*, findaline_ssh_*
HOST_FILES = ("findaline_facts_", "findaline_check_", "findaline_backup_", "findaline_ssh_")


def _load(*parts):
    with open(os.path.join(MONITORING, *parts), encoding="utf-8") as f:
        return f.read()


def _compose():
    return yaml.safe_load(_load("compose.yaml"))


def _telegraf():
    return tomllib.loads(_load("telegraf.conf"))


def _rules():
    return [rule for group in yaml.safe_load(_load("grafana", "provisioning", "alerting", "rules.yaml"))["groups"]
            for rule in group["rules"]]


def _dashboards():
    folder = os.path.join(GRAFANA, "dashboards")
    out = {}
    for name in sorted(os.listdir(folder)):
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            out[name] = json.load(f)
    return out


# PromQL/MetricsQL words that are not metrics
KEYWORDS = {"by", "without", "on", "ignoring", "group_left", "group_right", "offset", "and", "or", "unless", "bool"}


def _metrics(expr):
    """The metric names and the label names of a query: label matchers per metric, grouping
    labels; a name followed by "(" is a function."""
    selectors = re.findall(r"([a-zA-Z_:][\w:]*)\{([^}]*)\}", expr)
    labels = {name: set(re.findall(r"(\w+)\s*(?:=~|!~|!=|=)", matchers)) for name, matchers in selectors}
    grouping = set()
    for words in re.findall(r"\b(?:by|without|on|ignoring)\s*\(([^)]*)\)", expr):
        grouping |= {w.strip() for w in words.split(",") if w.strip()}
    bare = re.sub(r'"[^"]*"', "", expr)
    bare = re.sub(r"\{[^}]*\}|\[[^\]]*\]", " ", bare)
    bare = re.sub(r"\b(?:by|without|on|ignoring)\s*\([^)]*\)", " ", bare)
    names = {m.group(1) for m in re.finditer(r"(?<![\w.])([a-zA-Z_:][\w:]*)(?![\w:]|\s*\()", bare)}
    names = {n for n in names if n not in KEYWORDS and not re.fullmatch(r"\d+[smhdwy]?", n)}
    return names, labels, grouping


def _queries():
    """Every query of VictoriaMetrics in the provisioning: (where, expr), for the rules and the
    dashboards' panels and annotations (not the dashboard Logs: LogsQL)."""
    out = [(f"rule {r['uid']}", item["model"]["expr"]) for r in _rules() for item in r["data"]
           if item["datasourceUid"] == DATASOURCE]
    for name, dashboard in _dashboards().items():
        if dashboard["uid"] == "logs":
            continue
        for panel in dashboard["panels"]:
            out += [(f"{dashboard['uid']} {panel['id']}", t["expr"]) for t in panel.get("targets", [])]
        out += [(f"{dashboard['uid']} annotation {a['name']}", a["expr"]) for a in dashboard["annotations"]["list"]]
    return out


def test_compose_services_and_ports():
    """The five services; only VictoriaMetrics, VictoriaLogs, Grafana and the socket proxy publish a
    port, each on the host's loopback; Telegraf shares the host's network namespace and publishes
    nothing."""
    compose = _compose()
    assert compose["name"] == "findaline-monitoring"
    services = compose["services"]
    assert set(services) == SERVICES
    assert services["victoriametrics"]["ports"] == ["127.0.0.1:8428:8428"]
    assert services["victorialogs"]["ports"] == ["127.0.0.1:9428:9428"]
    assert services["grafana"]["ports"] == ["127.0.0.1:3000:3000"]
    assert services["socket-proxy"]["ports"] == ["127.0.0.1:2375:2375"]
    assert services["telegraf"]["network_mode"] == "host"
    assert "ports" not in services["telegraf"]
    for name, service in services.items():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), (name, port)


def test_compose_hardening():
    """As compose.yaml of the site: read-only root, no capabilities, no new privileges, a non-root
    user, a memory limit without swap, rotated logs, a healthcheck (up --wait), an image pinned by
    digest. VictoriaLogs' distroless image has no tool to ask its /health: Telegraf's healthcheck
    asks it (and `disable: true` would make `up --wait` fail)."""
    services = _compose()["services"]
    assert "healthcheck" not in services["victorialogs"]
    assert "http://127.0.0.1:9428/health" in services["telegraf"]["healthcheck"]["test"][-1]
    assert services["telegraf"]["depends_on"]["victorialogs"] == {"condition": "service_started"}
    for name, service in services.items():
        assert service["read_only"] is True, name
        assert service["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in service["security_opt"], name
        user = str(service["user"])
        assert user.split(":")[0] not in ("", "0", "root"), name
        assert service["mem_limit"] and service["memswap_limit"] == service["mem_limit"], name
        assert service["logging"]["driver"] == "json-file" and "max-size" in service["logging"]["options"], name
        assert name == "victorialogs" or service["healthcheck"]["test"], name
        assert re.fullmatch(r"[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}", service["image"]), name
        assert service["restart"] == "unless-stopped", name


def test_compose_mounts():
    """Telegraf reads the host read-only (and never creates a missing host path); the socket proxy
    alone has the Docker socket; secrets come from the checkout's secrets/."""
    compose = _compose()
    services = compose["services"]
    telegraf = services["telegraf"]
    binds = {v["target"]: v for v in telegraf["volumes"]}
    assert set(binds) == {"/etc/telegraf/telegraf.conf", "/hostfs", "/var/log/nginx",
                          "/run/dbus/system_bus_socket", "/var/lib/findaline-monitoring"}
    for target, volume in binds.items():
        assert volume["type"] == "bind" and volume["read_only"] is True, target
        if target != "/etc/telegraf/telegraf.conf":
            assert volume["bind"]["create_host_path"] is False, target
    assert binds["/hostfs"]["source"] == "/" and binds["/hostfs"]["bind"]["propagation"] == "rslave"
    assert telegraf["environment"]["HOST_MOUNT_PREFIX"] == "/hostfs"
    assert telegraf["environment"]["HOST_PROC"] == "/hostfs/proc"
    assert telegraf["group_add"] == ["${ADM_GID:?ADM_GID missing: copy .env.example to .env}"]
    for name, service in services.items():
        mounts = [v if isinstance(v, str) else v.get("source", "") for v in service.get("volumes", [])]
        assert ("/var/run/docker.sock" in str(mounts)) == (name == "socket-proxy"), name
    assert services["socket-proxy"]["user"].startswith("65534:${DOCKER_GID")
    assert compose["secrets"] == {"grafana_admin_password": {"file": "../../secrets/grafana_admin_password"},
                                  "ntfy_url": {"file": "../../secrets/ntfy_url"}}
    grafana = services["grafana"]["environment"]
    assert grafana["GF_SECURITY_ADMIN_PASSWORD__FILE"] == "/run/secrets/grafana_admin_password"
    for key in ("GF_USERS_ALLOW_SIGN_UP", "GF_AUTH_ANONYMOUS_ENABLED", "GF_ANALYTICS_REPORTING_ENABLED",
                "GF_ANALYTICS_CHECK_FOR_UPDATES", "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES"):
        assert grafana[key] == "false", key
    # Its plugin from the host's folder that deploy/vps.sh fills (pinned by version and sha256),
    # read-only; Grafana installs nothing itself
    assert grafana["GF_PLUGINS_PREINSTALL_DISABLED"] == "true"
    assert grafana["GF_PATHS_PLUGINS"] == "/var/lib/grafana-plugins"
    plugins = [v for v in services["grafana"]["volumes"] if isinstance(v, dict) and v["target"] == "/var/lib/grafana-plugins"]
    assert plugins == [{"type": "bind", "source": "/var/lib/findaline-grafana-plugins", "target": "/var/lib/grafana-plugins",
                        "read_only": True, "bind": {"create_host_path": False}}]
    with open(os.path.join(ROOT, "deploy", "vps.sh"), encoding="utf-8") as f:
        vps = f.read()
    assert "GRAFANA_PLUGINS_DIR=/var/lib/findaline-grafana-plugins\n" in vps
    assert "GRAFANA_PLUGIN=victoriametrics-logs-datasource\n" in vps
    assert re.search(r"^GRAFANA_PLUGIN_VERSION=\d+\.\d+\.\d+$", vps, re.M)
    assert re.search(r"^GRAFANA_PLUGIN_SHA256=[0-9a-f]{64}$", vps, re.M)
    # VictoriaLogs keeps 30 days (the privacy page) in its volume
    command = services["victorialogs"]["command"]
    assert "-retentionPeriod=30d" in command and "-httpListenAddr=:9428" in command
    assert services["victorialogs"]["volumes"] == ["victorialogs:/home/nonroot"]
    env = _load(".env.example")
    assert re.search(r"^DOCKER_GID=\d+$", env, re.M) and re.search(r"^ADM_GID=4$", env, re.M)
    with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
        assert "deploy/monitoring/.env\n" in f.read()


def test_compose_network():
    """One network with the bridge name the host's firewall knows (br-fal-mon), no IPv6, and a fixed
    gateway: the only address the socket proxy lets in (published ports' connections come from it)."""
    compose = _compose()
    network = compose["networks"]["monitoring"]
    assert network["driver_opts"]["com.docker.network.bridge.name"] == "br-fal-mon"
    assert network["enable_ipv6"] is False
    assert network["ipam"]["config"] == [{"subnet": "172.30.2.0/24", "gateway": "172.30.2.1"}]
    for name in ("victoriametrics", "victorialogs", "grafana", "socket-proxy"):
        assert compose["services"][name]["networks"] == ["monitoring"], name


def test_socket_proxy_allowlist():
    """Read-only and narrow: GET of what Telegraf's docker and docker_log inputs ask (the version
    check, /info, the container list, a container's inspect, stats and logs) and HEAD of /_ping; no
    other method."""
    command = _compose()["services"]["socket-proxy"]["command"]
    allows = [c for c in command if c.startswith("-allow") and c != "-allowhealthcheck"]
    assert sorted(allows) == sorted([
        "-allowfrom=172.30.2.1/32", "-allowHEAD=/_ping", "-allowGET=/_ping",
        r"-allowGET=/v1\.[0-9]+/(info|containers/json|containers/[0-9a-f]{64}/(json|stats|logs))"])
    pattern = re.compile(r"^(?:/v1\.[0-9]+/(info|containers/json|containers/[0-9a-f]{64}/(json|stats|logs)))$")
    container = "/v1.56/containers/" + "a" * 64
    for path in ("/v1.56/info", "/v1.56/containers/json", container + "/json", container + "/stats",
                 container + "/logs"):
        assert pattern.match(path), path
    for path in (container + "/exec", container + "/attach", "/v1.56/events", "/v1.56/containers/create",
                 "/v1.56/images/json", "/v1.56/containers/" + "a" * 64 + "/archive"):
        assert not pattern.match(path), path


# Tags that may reach the store: the server's name, mount points and interfaces of the host, unit
# and container names, the type of a certificate, Telegraf's own plugin names, the stream of a
# container's log line (stdout, stderr)
ALLOWED_TAGS = {"host", "path", "name", "interface", "container_name", "container_status", "type", "input",
                "output", "stream"}
# Inputs whose tags are fixed and harmless without a taginclude (cpu: only cpu=cpu-total, dropped)
FIXED_TAGS = {"cpu", "system", "mem", "kernel_vmstat", "netstat"}


def test_telegraf_tags():
    """No tag carries an IP address, a user, a request's path or an id: every input that could add
    one keeps an allowlist of tags; the nginx log gives only its route group as a tag; Docker's
    labels and chrony's server stay out."""
    config = _telegraf()
    for plugin, instances in config["inputs"].items():
        for instance in instances:
            if instance.get("urls") == ["http://127.0.0.1:8766/metrics"]:
                continue   # the application's labels: test_telegraf_app_metrics
            if plugin in FIXED_TAGS:
                assert "taginclude" not in instance or set(instance["taginclude"]) <= ALLOWED_TAGS
                continue
            if plugin == "tail" and instance["name_override"] == "nginx_log":
                assert instance["path_tag"] == "" and instance["tag_keys"] == ["group"]
                assert "taginclude" not in instance   # its tags are set by the starlark processor below
                continue
            if plugin == "tail":   # nginx's error log: the line only, no tag (test_telegraf_logs)
                assert instance["path_tag"] == "" and "tag_keys" not in instance
                assert instance["data_format"] == "value" and instance["value_field_name"] == "message"
                continue
            assert "taginclude" in instance, plugin
            assert set(instance["taginclude"]) <= ALLOWED_TAGS, plugin
            assert "path" not in instance["taginclude"] or plugin == "disk", plugin
    docker = config["inputs"]["docker"][0]
    assert docker["docker_label_exclude"] == ["*"] and docker["endpoint"] == "tcp://127.0.0.1:2375"
    logs = config["inputs"]["docker_log"][0]
    assert logs["docker_label_exclude"] == ["*"] and logs["endpoint"] == "tcp://127.0.0.1:2375"
    assert logs["taginclude"] == ["container_name", "stream"] and logs["fieldinclude"] == ["message"]
    starlark = [p for p in config["processors"]["starlark"] if p["namepass"] == ["nginx_log"]][0]
    assert starlark["namepass"] == ["nginx_log"]
    assert set(re.findall(r'\.tags\["(\w+)"\]', starlark["source"])) == {"class"}
    assert re.search(r'tags = \{"host": .*, "group": .*\}', starlark["source"])
    # The nginx samples are aggregated every 30 s and only they go through the aggregators
    for aggregator in ("basicstats", "quantile"):
        settings = config["aggregators"][aggregator][0]
        assert settings["drop_original"] is True and settings["period"] == "30s"
        assert settings["namepass"] in (["nginx_requests"], ["nginx_times"])
    assert config["agent"]["interval"] == "30s"
    assert config["outputs"]["http"][0]["url"] == "http://127.0.0.1:8428/write"


def test_telegraf_app_metrics():
    """The application's /metrics (phase 2): only its findaline_* metrics (no process_*, python_*
    or _created samples), no tag added but the host (not the scraped URL), and the series keep the
    application's names (measurement findaline, the prefix of the fields stripped)."""
    config = _telegraf()
    apps = [i for i in config["inputs"]["prometheus"] if i["urls"] == ["http://127.0.0.1:8766/metrics"]]
    assert len(apps) == 1
    app = apps[0]
    assert app["metric_version"] == 2 and app["name_override"] == "findaline"
    assert app["fieldinclude"] == ["findaline_*"] and app["fieldexclude"] == ["*_created"]
    assert {"url", "address"} <= set(app["tagexclude"]) and "taginclude" not in app
    assert "interval" not in app   # the agent's 30 s
    strings = [s for s in config["processors"]["strings"] if s["namepass"] == ["findaline"]]
    assert [s["trim_prefix"] for s in strings] == [[{"field_key": "*", "prefix": "findaline_"}]]
    # No other measurement is named findaline, so the processor touches nothing else
    names = [i.get("name_override") for instances in config["inputs"].values() for i in instances]
    assert names.count("findaline") == 1


def test_telegraf_reads_the_contract_paths():
    """The files and ports host's side writes (the contract of phase 1): the nginx metrics log,
    stub_status on the loopback, the three facts files."""
    config = _telegraf()
    tails = {i["name_override"]: i["files"] for i in config["inputs"]["tail"]}
    assert tails == {"nginx_log": ["/var/log/nginx/findaline.metrics.log"],
                     "nginx_error": ["/var/log/nginx/findaline.error.log"]}
    assert config["inputs"]["nginx"][0]["urls"] == ["http://127.0.0.1:8081/nginx_status"]
    files = {i["name_override"]: i["files"] for i in config["inputs"]["file"]}
    assert ["http://127.0.0.1:8766/metrics"] in [i["urls"] for i in config["inputs"]["prometheus"]]
    assert files == {"findaline_facts": ["/var/lib/findaline-monitoring/facts.json"],
                     "findaline_check": ["/var/lib/findaline-monitoring/check.json"],
                     "findaline_backup": ["/var/lib/findaline-monitoring/backup.json"],
                     "findaline_ssh": ["/var/lib/findaline-monitoring/ssh.json"]}
    with open(os.path.join(ROOT, "deploy", "nginx", "findaline.conf"), encoding="utf-8") as f:
        assert "error_log /var/log/nginx/findaline.error.log " in f.read()
    script = _load("ssh-login.sh")
    assert 'OUT=/var/lib/findaline-monitoring\n' in script and '"$OUT/ssh.json"' in script
    units = " ".join(i["pattern"] for i in config["inputs"]["systemd_units"]).split()
    assert sorted(units) == sorted([
        "nginx.service", "docker.service", "fail2ban.service", "ssh.service", "certbot.timer",
        "findaline-backup.timer", "findaline-facts.timer", "findaline-check.timer", "findaline-heartbeat.timer",
        "unattended-upgrades.service"])


# nginx's error lines (deploy/nginx/findaline.conf writes them with `client: <address>`) and the
# application's, each with what must not survive Telegraf's processor
LOG_LINES = [
    ('2026/11/01 12:00:00 [error] 812#812: *41 upstream timed out (110: Connection timed out) while reading response '
     'header from upstream, client: 203.0.113.7, server: findaline.example.org, request: "GET /api/jobs HTTP/2.0", '
     'upstream: "http://127.0.0.1:8765/api/jobs", host: "findaline.example.org"', ["203.0.113.7", "127.0.0.1"]),
    ('2026/11/01 12:00:01 [warn] 812#812: *42 limiting requests, excess: 10.500 by zone "api", client: '
     '2001:db8:85a3::8a2e:370:7334, server: findaline.example.org', ["2001:db8", "8a2e:370:7334"]),
    ('2026/11/01 12:00:02 [crit] 812#812: *43 SSL_do_handshake() failed while SSL handshaking, client: '
     '::ffff:198.51.100.4, server: 0.0.0.0:443', ["198.51.100.4", "ffff", "0.0.0.0"]),
    ('2026/11/01 12:00:03 [error] 812#812: *44 connect() failed, client: fe80::1%eth0, server: _', ["fe80"]),
    ("ValueError: boom near 2001:0db8:0000:0000:0000:ff00:0042:8329", ["2001:0db8", "8329"]),
    ('2026/11/01 12:00:04 [error] 812#812: *45 upstream prematurely closed connection, client: 192.0.2.10, server: '
     'findaline.example.org, request: "GET /favicon.ico HTTP/2.0", referrer: "https://findaline.example.org/s/'
     'Zx9_secretToken-1/map.html#line=1"', ["192.0.2.10", "Zx9_secretToken-1"]),
    ('2026/11/01 12:00:05 [error] 812#812: *46 upstream timed out, client: 192.0.2.11, request: "GET '
     '/auth/github?code=abc123&state=xyz HTTP/2.0"', ["192.0.2.11", "abc123", "xyz"]),
    ("requests.exceptions.ConnectionError: HTTPSConnectionPool(host='wcs.datafordeler.dk', port=443): Max "
     "retries exceeded with url: /DHMNedboer/dhm_wcs/1.0.0/WCS?SERVICE=WCS&REQUEST=GetCoverage&apikey=0f3c9e1a2b4d6f8e7a&WIDTH=2000 "
     "(Caused by ConnectTimeoutError(198.51.100.20))", ["0f3c9e1a2b4d6f8e7a", "198.51.100.20"]),
    ("RuntimeError: HTTP 401 for https://portal.opentopography.org/API/globaldem?demtype=NASADEM&API_Key=Ab12Cd34"
     " from 203.0.113.9", ["Ab12Cd34", "203.0.113.9"]),
]


def _mask(message):
    """Telegraf's regex processor of the log lines, applied as Telegraf does (Go's RE2 and Python's
    re agree on these patterns: no look-around, (?i) and word boundaries alike; Go's $1 is Python's group 1)."""
    for field in _telegraf()["processors"]["regex"][0]["fields"]:
        assert field["key"] == "message"
        message = re.sub(field["pattern"], field["replacement"].replace("$1", r"\1"), message)
    return message


def test_telegraf_logs():
    """The log lines (docker_log of web and worker, nginx's error log) go only to VictoriaLogs and
    every other sample only to VictoriaMetrics; their addresses are masked first; the lines carry
    the source (web, worker, nginx), the container, the stream, the level and the message, nothing
    else of the metric; VictoriaLogs' JSON lines API with source as the stream."""
    config = _telegraf()
    outputs = config["outputs"]["http"]
    assert len(outputs) == 2
    metrics, logs = outputs
    assert metrics["url"] == "http://127.0.0.1:8428/write" and metrics["namedrop"] == LOG_MEASUREMENTS
    assert "namepass" not in metrics
    assert logs["namepass"] == LOG_MEASUREMENTS and "namedrop" not in logs
    assert logs["url"] == ("http://127.0.0.1:9428/insert/jsonline?_stream_fields=source&_msg_field=message"
                           "&_time_field=time")
    assert logs["data_format"] == "json" and logs["use_batch_format"] is False
    keys = set(re.findall(r'^\s*"(\w+)":', logs["json_transformation"], re.M))
    assert keys == {"time", "source", "container", "stream", "level", "message"}
    # Which inputs make the log measurements: the docker_log input and the error log's tail only
    makers = [plugin for plugin, instances in config["inputs"].items() for i in instances
              if plugin == "docker_log" or i.get("name_override") in LOG_MEASUREMENTS]
    assert sorted(makers) == ["docker_log", "tail"]
    assert config["inputs"]["docker_log"][0]["container_name_include"] == ["findaline-web-*", "findaline-worker-*"]
    # The processors of the log lines: the masking first, then the level
    regex = config["processors"]["regex"]
    assert len(regex) == 1 and regex[0]["namepass"] == LOG_MEASUREMENTS and regex[0]["order"] == 1
    levels = [p for p in config["processors"]["starlark"] if p["namepass"] == LOG_MEASUREMENTS]
    assert len(levels) == 1 and levels[0]["order"] == 2
    for line, secrets in LOG_LINES:
        masked = _mask(line)
        for secret in secrets:
            assert secret not in masked, (masked, secret)
        assert "<address>" in masked
    masked = _mask(LOG_LINES[0][0])
    assert masked.startswith("2026/11/01 12:00:00 [error] 812#812: *41 upstream timed out")
    assert "client: <address>, server: findaline.example.org" in masked and "excess: 10.500" in _mask(LOG_LINES[1][0])
    assert '"https://findaline.example.org/s/<token>/map.html#line=1"' in _mask(LOG_LINES[5][0])
    assert '"GET /auth/github?<query> HTTP/2.0"' in _mask(LOG_LINES[6][0])
    assert "&apikey=<secret>&WIDTH=2000 " in _mask(LOG_LINES[7][0])
    assert "&API_Key=<secret> from" in _mask(LOG_LINES[8][0])
    for text in ("Saved run 2026-11-01_12-00-00 at 50.1559508, 19.7562722 in 12:03:44", "lines: 1.2.3 of 4"):
        assert _mask(text) == text


def test_grafana_provisioning_valid():
    """Every provisioning file parses; the data source has the fixed uid the rules and panels use."""
    for folder, _, names in os.walk(os.path.join(GRAFANA, "provisioning")):
        for name in names:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                assert yaml.safe_load(f)["apiVersion"] == 1, name
    sources = yaml.safe_load(_load("grafana", "provisioning", "datasources", "victoriametrics.yaml"))["datasources"]
    assert [(s["uid"], s["type"], s["url"]) for s in sources] == [
        (DATASOURCE, "prometheus", "http://victoriametrics:8428")]
    sources = yaml.safe_load(_load("grafana", "provisioning", "datasources", "victorialogs.yaml"))["datasources"]
    assert [(s["uid"], s["type"], s["url"], s["isDefault"]) for s in sources] == [
        (LOGS_DATASOURCE, "victoriametrics-logs-datasource", "http://victorialogs:9428", False)]
    points = yaml.safe_load(_load("grafana", "provisioning", "alerting", "contact-points.yaml"))["contactPoints"]
    for point in points:
        for receiver in point["receivers"]:
            assert receiver["settings"]["url"] == "${FINDALINE_NTFY_URL}"
    entrypoint = _compose()["services"]["grafana"]["entrypoint"][-1]
    assert "< /run/secrets/ntfy_url" in entrypoint and r"tr -d '\r\n'" in entrypoint and "grafana://noop" in entrypoint


def test_alert_rules():
    """Every rule queries the provisioned data source (or Grafana's expressions), names its row of
    docs/monitoring.md, its level and the server, links to a panel that exists, and has no other
    dollar sign than the server's variable (Grafana expands environment variables in provisioning)."""
    dashboards = {d["uid"]: {p["id"] for p in d["panels"]} for d in _dashboards().values()}
    rules = _rules()
    assert len({r["uid"] for r in rules}) == len(rules)
    rows = set()
    for rule in rules:
        for item in rule["data"]:
            assert item["datasourceUid"] in (DATASOURCE, "__expr__"), rule["uid"]
        assert re.fullmatch(r"[A-G]\d+", rule["labels"]["row"]), rule["uid"]
        assert rule["title"].startswith(rule["labels"]["row"] + " "), rule["uid"]
        assert rule["labels"]["level"] in ("alert", "info"), rule["uid"]
        assert rule["labels"]["server"] == "${FINDALINE_PUBLIC_URL}", rule["uid"]
        assert rule["annotations"]["summary"], rule["uid"]
        assert int(rule["annotations"]["__panelId__"]) in dashboards[rule["annotations"]["__dashboardUid__"]], rule["uid"]
        assert rule["noDataState"] == "OK", rule["uid"]
        rows.add(rule["labels"]["row"])
    # The alert and info rows (docs/monitoring.md, "Alerts"); G1 is healthchecks.io's, D4 goes from
    # the host to ntfy itself (deploy/monitoring/ssh-login.sh)
    assert rows == {"A1", "A2", "A3", "A4", "A7", "A8", "B1", "B2", "C1", "C2", "C5", "C6", "D1", "D2", "D3",
                    "E1", "G2", "F1", "F2", "F3", "F5", "F6", "F7", "F8", "F11", "F13"}
    levels = {}
    for rule in rules:
        levels.setdefault(rule["labels"]["row"], set()).add(rule["labels"]["level"])
    assert {row for row, level in levels.items() if level == {"info"}} == {"A7", "F6", "F8"}
    for name in ("rules.yaml", "templates.yaml", "policies.yaml"):
        text = _load("grafana", "provisioning", "alerting", name)
        assert not re.findall(r"\$(?!\{FINDALINE_PUBLIC_URL\})", text), name


def test_dashboards():
    """The dashboards VPS, Site, Find-a-Line (VictoriaMetrics) and Logs (VictoriaLogs): unique panel
    ids, every panel, query and annotation on its provisioned data source; the Logs dashboard's
    queries filter by its variables (the plugin expands `field:$var` to `field:in(...)`, All to
    `in(*)`) and use the plugin's query types; the coverage map gets numbers for its coordinates."""
    dashboards = _dashboards()
    assert sorted(d["uid"] for d in dashboards.values()) == DASHBOARDS
    for name, dashboard in dashboards.items():
        source = LOGS_DATASOURCE if dashboard["uid"] == "logs" else DATASOURCE
        ids = [p["id"] for p in dashboard["panels"]]
        assert len(ids) == len(set(ids)), name
        for panel in dashboard["panels"]:
            if panel["type"] == "row":
                continue
            assert panel["datasource"]["uid"] == source, (name, panel["id"])
            assert panel["targets"], (name, panel["id"])
            for target in panel["targets"]:
                assert target["datasource"]["uid"] == source, (name, panel["id"])
                assert target["expr"], (name, panel["id"])
        for annotation in dashboard["annotations"]["list"]:
            assert annotation["datasource"]["uid"] == DATASOURCE and annotation["expr"], name
    logs = dashboards["logs.json"]
    assert [v["name"] for v in logs["templating"]["list"]] == ["source", "level", "search"]
    assert logs["templating"]["list"][0]["query"] == "web,worker,nginx"
    assert logs["templating"]["list"][1]["query"] == "error,warning,info"
    for panel in logs["panels"]:
        for target in panel["targets"]:
            assert target["expr"].startswith("source:$source level:"), panel["id"]
            assert target["queryType"] == ("instant" if panel["type"] == "logs" else "statsRange"), panel["id"]
    assert [p["type"] for p in logs["panels"]] == ["timeseries", "timeseries", "logs"]
    geomap = [p for p in dashboards["findaline.json"]["panels"] if p["type"] == "geomap"]
    assert len(geomap) == 1
    assert geomap[0]["targets"][0]["expr"] == "sum by (lat, lon) (findaline_searches_by_cell)"
    assert geomap[0]["targets"][0]["format"] == "table"
    assert geomap[0]["transformations"][0]["id"] == "convertFieldType"
    location = geomap[0]["options"]["layers"][0]["location"]
    assert location == {"mode": "coords", "latitude": "latitude", "longitude": "longitude"}


def test_queries_name_known_metrics():
    """Every findaline_* metric a rule, panel or annotation asks for is one of the application's
    (APP_METRICS, with its labels) or of the host's files; the dashboard Find-a-Line and the rules
    of rows F ask for nothing else (and group by no label but theirs and the host)."""
    app_labels = set().union(*APP_METRICS.values()) | {"host"}
    app_queries = {where for where, _ in _queries() if re.match(r"findaline |rule (f\d|g2-app)", where)}
    assert len(app_queries) > 40
    for where, expr in _queries():
        names, labels, grouping = _metrics(expr)
        for name in names:
            if name.startswith("findaline_") and not name.startswith(HOST_FILES):
                assert name in APP_METRICS, (where, name)
                assert labels.get(name, set()) <= APP_METRICS[name] | {"host"}, (where, name, labels[name])
            else:
                assert where not in app_queries, (where, name)
        if where in app_queries:
            assert grouping <= app_labels, (where, grouping)


# The running stack (CI's monitoring job, or a local test stack): FINDALINE_GRAFANA_URL and
# FINDALINE_GRAFANA_PASSWORD (the admin's); VictoriaMetrics at FINDALINE_VM_URL
LIVE = os.environ.get("FINDALINE_GRAFANA_URL")
# What Telegraf writes even without the site: the host, Docker (the monitoring containers), the nginx
# metrics log and the facts files of the job, systemd's units, Telegraf and VictoriaMetrics themselves
LIVE_METRICS = ["cpu_usage_idle", "cpu_usage_steal", "system_load5", "mem_available_percent", "kernel_vmstat_oom_kill",
                'disk_free{path="/"}', "diskio_io_time", "netstat_tcp_established", "reboot_required_exists",
                "docker_container_mem_usage_percent", "docker_container_status_restart_count",
                "docker_container_health_health_code", "nginx_requests_request_time_count",
                "nginx_times_request_time_095", "findaline_facts_time", "findaline_facts_fail2ban_sshd_banned_total",
                "findaline_check_failed", "findaline_backup_last_success", "findaline_ssh_logins",
                "systemd_units_active_code",
                "internal_write_errors", "prometheus_vm_free_disk_space_bytes"]
# The application's metrics, when its /metrics answers on 127.0.0.1:8766 of the stack's host (the
# site, or a stand-in serving APP_METRICS): FINDALINE_APP_METRICS=1. Those absent without rows
# (labels of jobs that never happened, accounts locally, the cache sizes before the first
# housekeeping, the lease age without a worker, queue_max when unlimited) are not required.
LIVE_APP_METRICS = ["findaline_build_info", "findaline_workers_alive", "findaline_slots",
                    "findaline_job_oldest_waiting_seconds", "findaline_quick_waiting",
                    "findaline_quick_oldest_waiting_seconds", "findaline_reports_open", "findaline_runs",
                    "findaline_runs_bytes", "findaline_free_disk_bytes", "findaline_favourites",
                    "findaline_service_requests_total", "findaline_service_bytes_total",
                    "findaline_service_seconds_total", "findaline_http_requests_total",
                    "findaline_http_request_seconds_sum", "findaline_event_streams",
                    "findaline_housekeeping_removed", "findaline_housekeeping_last_run_timestamp_seconds",
                    "findaline_housekeeping_seconds", "findaline_coverage_km2", "findaline_searches_by_cell"]
# A text of a log line written into the stack's nginx error log (or a container's output) before the
# test: FINDALINE_LOG_LINE; its line must be found through Grafana, with its client address masked
LIVE_LOG_LINE = os.environ.get("FINDALINE_LOG_LINE")


def _get(url, data=None):
    import base64
    import urllib.request
    password = os.environ.get("FINDALINE_GRAFANA_PASSWORD", "")
    headers = {"Authorization": "Basic " + base64.b64encode(f"admin:{password}".encode()).decode(),
               "Content-Type": "application/json"}
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


@pytest.mark.skipif(not LIVE, reason="needs a running monitoring stack (FINDALINE_GRAFANA_URL)")
def test_live_stack():
    """Grafana is healthy, its data source answers, the dashboards and every rule are provisioned,
    VictoriaMetrics holds Telegraf's samples under the names the rules and panels use, and every
    query of a rule or a panel runs without an error."""
    import urllib.parse
    assert _get(LIVE + "/api/health")["database"] == "ok"
    assert _get(LIVE + f"/api/datasources/uid/{DATASOURCE}/health")["status"] == "OK"
    assert sorted(d["uid"] for d in _get(LIVE + "/api/search?type=dash-db")) == DASHBOARDS
    provisioned = {r["uid"]: r for r in _get(LIVE + "/api/v1/provisioning/alert-rules")}
    assert set(provisioned) == {r["uid"] for r in _rules()}
    assert {r["folderUID"] for r in provisioned.values()} == {
        _get(LIVE + f"/api/dashboards/uid/{uid}")["meta"]["folderUid"] for uid in DASHBOARDS}
    assert sorted(c["name"] for c in _get(LIVE + "/api/v1/provisioning/contact-points")) == ["ntfy", "ntfy-info"]
    assert _get(LIVE + f"/api/datasources/uid/{LOGS_DATASOURCE}/health")["status"] == "OK"
    plugin = _get(LIVE + "/api/plugins/victoriametrics-logs-datasource/settings")
    assert plugin["signature"] == "valid", plugin["signature"]
    vm = os.environ.get("FINDALINE_VM_URL", "http://127.0.0.1:8428")
    expected = LIVE_METRICS + (LIVE_APP_METRICS if os.environ.get("FINDALINE_APP_METRICS") else [])
    missing = [m for m in expected
               if not _get(vm + "/api/v1/query?" + urllib.parse.urlencode({"query": f"last_over_time({m}[15m])"}))
               ["data"]["result"]]
    assert not missing

    def query(expr, instant):
        body = {"from": "now-1h", "to": "now", "queries": [{
            "refId": "A", "datasource": {"type": "prometheus", "uid": DATASOURCE}, "expr": expr,
            "instant": instant, "range": not instant, "intervalMs": 30000, "maxDataPoints": 200}]}
        return _get(LIVE + "/api/ds/query", body)["results"]["A"].get("error")

    def logs(expr, query_type):
        # The dashboard's variables as the plugin expands them for "All" (in(*)) and an empty text
        expr = expr.replace("$source", "in(*)").replace("$level", "in(*)").replace("$search", "")
        body = {"from": "now-1h", "to": "now", "queries": [{
            "refId": "A", "datasource": {"type": "victoriametrics-logs-datasource", "uid": LOGS_DATASOURCE},
            "expr": expr, "queryType": query_type, "intervalMs": 300000, "maxLines": 1000}]}
        return _get(LIVE + "/api/ds/query", body)["results"]["A"]

    errors = {}
    for rule in _rules():
        errors[rule["uid"]] = query(rule["data"][0]["model"]["expr"], True)
    for panel in _dashboards()["logs.json"]["panels"]:
        for target in panel["targets"]:
            errors[f"logs {panel['id']}"] = logs(target["expr"], target["queryType"]).get("error")
    if LIVE_LOG_LINE:
        found = logs(f'"{LIVE_LOG_LINE}"', "instant")
        text = json.dumps(found)
        assert LIVE_LOG_LINE in text and "client: <address>" in text, text[:2000]
        assert not re.search(r"client: \d", text), text[:2000]
    for name, dashboard in _dashboards().items():
        if dashboard["uid"] == "logs":
            continue
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                errors[f"{name} {panel['id']} {target['refId']}"] = query(
                    target["expr"].replace("$__rate_interval", "2m"), bool(target.get("instant")))
        for annotation in dashboard["annotations"]["list"]:
            errors[f"{name} annotation {annotation['name']}"] = query(annotation["expr"], False)
    assert not {key: error for key, error in errors.items() if error}
