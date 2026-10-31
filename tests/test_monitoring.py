"""The monitoring project (deploy/monitoring, docs/monitoring.md): what its compose file publishes
and how its services are hardened, that Telegraf keeps addresses, users and paths out of its tags,
and that Grafana's provisioning is valid and names the provisioned data source everywhere. The
stack itself runs in CI (the docker job)."""

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
SERVICES = {"telegraf", "victoriametrics", "grafana", "socket-proxy"}


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


def test_compose_services_and_ports():
    """The four services; only VictoriaMetrics, Grafana and the socket proxy publish a port, each on
    the host's loopback; Telegraf shares the host's network namespace and publishes nothing."""
    compose = _compose()
    assert compose["name"] == "findaline-monitoring"
    services = compose["services"]
    assert set(services) == SERVICES
    assert services["victoriametrics"]["ports"] == ["127.0.0.1:8428:8428"]
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
    digest."""
    for name, service in _compose()["services"].items():
        assert service["read_only"] is True, name
        assert service["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in service["security_opt"], name
        user = str(service["user"])
        assert user.split(":")[0] not in ("", "0", "root"), name
        assert service["mem_limit"] and service["memswap_limit"] == service["mem_limit"], name
        assert service["logging"]["driver"] == "json-file" and "max-size" in service["logging"]["options"], name
        assert service["healthcheck"]["test"], name
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
    for name in ("victoriametrics", "grafana", "socket-proxy"):
        assert compose["services"][name]["networks"] == ["monitoring"], name


def test_socket_proxy_allowlist():
    """Read-only and narrow: GET of what Telegraf's docker input asks (the version check, /info, the
    container list, a container's inspect and stats) and HEAD of /_ping; no other method."""
    command = _compose()["services"]["socket-proxy"]["command"]
    allows = [c for c in command if c.startswith("-allow") and c != "-allowhealthcheck"]
    assert sorted(allows) == sorted([
        "-allowfrom=172.30.2.1/32", "-allowHEAD=/_ping", "-allowGET=/_ping",
        r"-allowGET=/v1\.[0-9]+/(info|containers/json|containers/[0-9a-f]{64}/(json|stats))"])
    pattern = re.compile(r"^(?:/v1\.[0-9]+/(info|containers/json|containers/[0-9a-f]{64}/(json|stats)))$")
    container = "/v1.56/containers/" + "a" * 64
    for path in ("/v1.56/info", "/v1.56/containers/json", container + "/json", container + "/stats"):
        assert pattern.match(path), path
    for path in (container + "/logs", container + "/exec", "/v1.56/events", "/v1.56/containers/create",
                 "/v1.56/images/json", "/v1.56/containers/" + "a" * 64 + "/archive"):
        assert not pattern.match(path), path


# Tags that may reach the store: the server's name, mount points and interfaces of the host, unit
# and container names, the type of a certificate, Telegraf's own plugin names
ALLOWED_TAGS = {"host", "path", "name", "interface", "container_name", "container_status", "type", "input",
                "output"}
# Inputs whose tags are fixed and harmless without a taginclude (cpu: only cpu=cpu-total, dropped)
FIXED_TAGS = {"cpu", "system", "mem", "kernel_vmstat", "netstat"}


def test_telegraf_tags():
    """No tag carries an IP address, a user, a request's path or an id: every input that could add
    one keeps an allowlist of tags; the nginx log gives only its route group as a tag; Docker's
    labels and chrony's server stay out."""
    config = _telegraf()
    for plugin, instances in config["inputs"].items():
        for instance in instances:
            if plugin in FIXED_TAGS:
                assert "taginclude" not in instance or set(instance["taginclude"]) <= ALLOWED_TAGS
                continue
            if plugin == "tail":
                assert instance["path_tag"] == "" and instance["tag_keys"] == ["group"]
                assert "taginclude" not in instance   # its tags are set by the starlark processor below
                continue
            assert "taginclude" in instance, plugin
            assert set(instance["taginclude"]) <= ALLOWED_TAGS, plugin
            assert "path" not in instance["taginclude"] or plugin == "disk", plugin
    docker = config["inputs"]["docker"][0]
    assert docker["docker_label_exclude"] == ["*"] and docker["endpoint"] == "tcp://127.0.0.1:2375"
    starlark = config["processors"]["starlark"][0]
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


def test_telegraf_reads_the_contract_paths():
    """The files and ports host's side writes (the contract of phase 1): the nginx metrics log,
    stub_status on the loopback, the three facts files."""
    config = _telegraf()
    assert config["inputs"]["tail"][0]["files"] == ["/var/log/nginx/findaline.metrics.log"]
    assert config["inputs"]["nginx"][0]["urls"] == ["http://127.0.0.1:8081/nginx_status"]
    files = {i["name_override"]: i["files"] for i in config["inputs"]["file"]}
    assert files == {"findaline_facts": ["/var/lib/findaline-monitoring/facts.json"],
                     "findaline_check": ["/var/lib/findaline-monitoring/check.json"],
                     "findaline_backup": ["/var/lib/findaline-monitoring/backup.json"]}
    units = " ".join(i["pattern"] for i in config["inputs"]["systemd_units"]).split()
    assert sorted(units) == sorted([
        "nginx.service", "docker.service", "fail2ban.service", "ssh.service", "certbot.timer",
        "findaline-backup.timer", "findaline-facts.timer", "findaline-heartbeat.timer",
        "unattended-upgrades.service"])


def test_grafana_provisioning_valid():
    """Every provisioning file parses; the data source has the fixed uid the rules and panels use."""
    for folder, _, names in os.walk(os.path.join(GRAFANA, "provisioning")):
        for name in names:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                assert yaml.safe_load(f)["apiVersion"] == 1, name
    sources = yaml.safe_load(_load("grafana", "provisioning", "datasources", "victoriametrics.yaml"))["datasources"]
    assert [(s["uid"], s["type"], s["url"]) for s in sources] == [
        (DATASOURCE, "prometheus", "http://victoriametrics:8428")]
    points = yaml.safe_load(_load("grafana", "provisioning", "alerting", "contact-points.yaml"))["contactPoints"]
    for point in points:
        for receiver in point["receivers"]:
            assert receiver["settings"]["url"] == "$__file{/run/secrets/ntfy_url}"


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
    # The alert and info rows of phase 1 (docs/monitoring.md, "Alerts"); G1 is healthchecks.io's
    assert rows == {"A1", "A2", "A3", "A4", "A7", "A8", "B1", "B2", "C1", "C2", "C5", "C6", "D1", "D2", "D3",
                    "E1", "G2"}
    for name in ("rules.yaml", "templates.yaml", "policies.yaml"):
        text = _load("grafana", "provisioning", "alerting", name)
        assert not re.findall(r"\$(?!\{FINDALINE_PUBLIC_URL\})", text), name


def test_dashboards():
    """The dashboards VPS and Site: unique panel ids, every panel and query on the provisioned data
    source."""
    dashboards = _dashboards()
    assert sorted(d["uid"] for d in dashboards.values()) == ["site", "vps"]
    for name, dashboard in dashboards.items():
        ids = [p["id"] for p in dashboard["panels"]]
        assert len(ids) == len(set(ids)), name
        for panel in dashboard["panels"]:
            if panel["type"] == "row":
                continue
            assert panel["datasource"]["uid"] == DATASOURCE, (name, panel["id"])
            assert panel["targets"], (name, panel["id"])
            for target in panel["targets"]:
                assert target["datasource"]["uid"] == DATASOURCE, (name, panel["id"])
                assert target["expr"], (name, panel["id"])


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
                "findaline_check_failed", "findaline_backup_last_success", "systemd_units_active_code",
                "internal_write_errors", "prometheus_vm_free_disk_space_bytes"]


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
    assert sorted(d["uid"] for d in _get(LIVE + "/api/search?type=dash-db")) == ["site", "vps"]
    provisioned = {r["uid"]: r for r in _get(LIVE + "/api/v1/provisioning/alert-rules")}
    assert set(provisioned) == {r["uid"] for r in _rules()}
    assert {r["folderUID"] for r in provisioned.values()} == {d["meta"]["folderUid"] for d in (
        _get(LIVE + "/api/dashboards/uid/vps"), _get(LIVE + "/api/dashboards/uid/site"))}
    assert sorted(c["name"] for c in _get(LIVE + "/api/v1/provisioning/contact-points")) == ["ntfy", "ntfy-info"]
    vm = os.environ.get("FINDALINE_VM_URL", "http://127.0.0.1:8428")
    missing = [m for m in LIVE_METRICS
               if not _get(vm + "/api/v1/query?" + urllib.parse.urlencode({"query": f"last_over_time({m}[15m])"}))
               ["data"]["result"]]
    assert not missing

    def query(expr, instant):
        body = {"from": "now-1h", "to": "now", "queries": [{
            "refId": "A", "datasource": {"type": "prometheus", "uid": DATASOURCE}, "expr": expr,
            "instant": instant, "range": not instant, "intervalMs": 30000, "maxDataPoints": 200}]}
        return _get(LIVE + "/api/ds/query", body)["results"]["A"].get("error")

    errors = {}
    for rule in _rules():
        errors[rule["uid"]] = query(rule["data"][0]["model"]["expr"], True)
    for name, dashboard in _dashboards().items():
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                errors[f"{name} {panel['id']} {target['refId']}"] = query(
                    target["expr"].replace("$__rate_interval", "2m"), bool(target.get("instant")))
    assert not {key: error for key, error in errors.items() if error}
