"""The pairs between the three parts of the project's data server (docs/mirror-hosting/spec.md): the mirror stack
(deploy/mirror), the publish tool (tools/mirror_publish.py) and the client (sources/readers/tilebases.py, sources/net.py),
and the site's side (Telegraf's checks, the docs). Static: no Docker, no network, no rclone; each test fails when one
side of its pair changes alone. Where wave 1's own tests already pin a pair, a comment names them instead of a second
copy: tests/test_mirror_deploy.py (the stack), tests/test_mirror_client.py (the client), tests/test_mirror_publish.py
(the tool; skipped without rclone, so the few pairs of the tool that matter here are asserted again, thinly).

tests/conftest.py keeps sources.net.HOST_RATES_OF for this module (its fixture empties it for the others): the client's
request rate is one side of the limits' pair. Nothing here calls net._get or net.rate_turn."""

import importlib.util
import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import cache  # noqa: E402
import mirror_publish as mp  # noqa: E402
import mirror_tiles  # noqa: E402
import sk_tiles  # noqa: E402
from sources import net  # noqa: E402
from sources.layers.gridtiles import renamed, res_name  # noqa: E402
from sources.readers import tilebases  # noqa: E402

HOST = "mirror.findaline.lukawski.org"
MIRROR = os.path.join(ROOT, "deploy", "mirror")
# The log's keys, in the order of nginx.conf's log_format (the contract; tests/test_mirror_deploy.py LOG_KEYS too)
LOG_KEYS = ["t", "s", "b", "rt", "ds", "a", "lim", "v"]
# What the approved privacy sentence names for each key (docs/mirror-hosting/spec.md, section 7: "The server writes
# down ..."): a ninth key, or a key without its words, fails test_the_logs_keys_and_the_privacy_sentence. The status
# and the refusing limit are both "whether the request was served or refused" (the specification's note, U22)
SENTENCE_OF_KEY = {
    "t": "the time",
    "a": "the address",
    "ds": "the dataset (not the tile)",
    "b": "the size",
    "s": "whether the request was served or refused",
    "lim": "whether the request was served or refused",
    "rt": "how long it took",
    "v": "the Find-a-Line version",
}


def _read(*parts: str) -> str:
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _nginx() -> str:
    """The mirror's nginx.conf without its comments."""
    return "\n".join("" if line.lstrip().startswith("#") else line.split("#", 1)[0]
                     for line in _read("deploy", "mirror", "nginx.conf").splitlines())


def _map_regexes(name: str) -> list:
    """The regular expressions of an nginx.conf map in their order, as Python's (named groups (?<n>...) are Python's
    (?P<n>...); the rest of these patterns reads the same in PCRE and Python)."""
    block = re.search(r"map \S+ \$" + name + r" \{(.*?)\n    \}", _nginx(), re.S)
    assert block, name
    return [(re.compile(source.replace("(?<", "(?P<")), value)
            for source, value in re.findall(r'"~([^"]+)"\s+(\$?\w+);', block.group(1))]


def _mapped(name: str, text: str, default: str) -> str:
    """What nginx's map $name gives for text: the first regular expression that matches wins (a "$v" value is its
    named group), else the default."""
    for regex, value in _map_regexes(name):
        found = regex.search(text)
        if found:
            return found.group(value[1:]) if value.startswith("$") else value
    return default


def _number(pattern: str) -> int:
    found = re.search(pattern, _nginx(), re.M)
    assert found, pattern
    return int(found.group(1))


def _privacy_text() -> str:
    """The approved text for README and the landing page, from the specification's section 7 (as
    tests/test_mirror_deploy.py reads it)."""
    quoted = re.search(r"- README and the mirror's landing page: \"(.+?data\.)\"", _read("docs", "mirror-hosting", "spec.md"),
                       re.S)
    assert quoted
    return " ".join(quoted.group(1).replace("`", "").split())


# 1. The server's limits against the client's manners

def test_the_client_stays_inside_one_visitors_limits():
    """The client's entries for the mirror's host (net.HOST_SLOTS_OF: tile connections at once; net.HOST_RATES_OF:
    requests a minute) against nginx.conf's limits for one visitor's address (limit_conn visitor_address, the
    limit_req zone's rate). The inequality asserted (docs/mirror-hosting/spec.md C.6): two installations behind one
    address fit, so 2 x the client's connections <= the address's concurrent requests, and 2 x the client's rate
    (per second) <= the address's request rate; the burst is not counted on. The trusted class (the site's server)
    allows as many at once per address as a visitor's address. The numbers' own pins: tests/test_mirror_deploy.py
    test_limits_and_timeouts (the server) and tests/test_rates.py test_published_limits,
    tests/test_mirror_client.py test_the_hosts_manners (the client)."""
    per_address = _number(r"^\s*limit_conn visitor_address (\d+);")
    trusted_per_address = _number(r"^\s*limit_conn trusted_address (\d+);")
    per_second = _number(r"limit_req_zone\s+\$visitor_key zone=visitor_rate:\S+ rate=(\d+)r/s;")
    assert (per_address, trusted_per_address, per_second) == (4, 4, 20)  # the contract's numbers
    assert tilebases.MIRROR_HOST == HOST
    slots, per_minute = net.HOST_SLOTS_OF[HOST], net.HOST_RATES_OF[HOST]
    assert 2 * slots <= per_address, "two installations behind one address must fit the address's connections"
    assert 2 * slots <= trusted_per_address
    assert 2 * per_minute / 60 <= per_second, "two installations behind one address must fit its request rate"
    # A mirror under another address (a LAN, the test stack) takes the same entries: net.LIMITS_AS maps it to the host
    # (tests/test_mirror_client.py test_two_connections_whatever_address)


def test_conftest_keeps_the_rates_for_this_module():
    """tests/conftest.py's line for this module: without it HOST_RATES_OF is empty here and the test above would
    compare nothing."""
    assert net.HOST_RATES_OF.get(HOST) == 600


# 2. One host everywhere

def _hosts(text: str) -> set:
    """Every name of the mirror's kind (mirror.<...>.lukawski.org) a text holds."""
    return set(re.findall(r"\bmirror\.[a-z0-9.-]*lukawski\.org\b", text))


def test_one_host_everywhere():
    """The client's MIRROR_URL, the SWAG conf's server_name, the server's README and the client's manners in
    sources/net.py name one host (the landing page names none: it is served under it)."""
    assert tilebases.MIRROR_URL == f"https://{HOST}"
    swag = _read("deploy", "mirror", "swag", "findaline-mirror.subdomain.conf")
    assert re.findall(r"^\s*server_name (\S+);", swag, re.M) == [HOST]
    for parts in [("deploy", "mirror", "swag", "findaline-mirror.subdomain.conf"), ("deploy", "mirror", "README.md"),
                  ("sources", "net.py"), ("sources", "readers", "tilebases.py")]:
        assert _hosts(_read(*parts)) == {HOST}, parts
    assert _hosts(_read("deploy", "mirror", "landing", "index.html")) == set()


# 3. The version a client sends, the server's log and the publish tool's rule

def _versions_logged(agent: str):
    """(the server's v, stats' v) for a User-Agent: nginx.conf's map $mirror_version, then
    mirror_publish.client_version of what the server wrote."""
    logged = _mapped("mirror_version", agent, "other")
    return logged, mp.client_version(logged)


VERSION_RULE = ("the version rule (nginx.conf's map $mirror_version, mirror_publish.CLIENT_VERSION): two or three numbers "
                "of at most three digits joined by dots, optionally a, b, rc, .dev or .post with a number; any other "
                "version is logged as \"other\" for every real client")


def test_the_clients_version_is_logged_as_it_is(monkeypatch):
    """cache.http_headers()'s User-Agent (from pyproject.toml's real version), for a self-hosted installation and for
    the public site's worker, is logged by the server as that version, and the publish tool's stats keeps it."""
    assert cache.USER_AGENT == f"Find-a-Line/{cache.VERSION} (highline finder"
    assert cache.VERSION == re.search(r'^version = "([^"]+)"$', _read("pyproject.toml"), re.M).group(1)
    for site, contact in [(None, None), ("https://findaline.example.org", "ops@example.org")]:
        for name, value in [("FINDALINE_PUBLIC_URL", site), ("FINDALINE_CONTACT", contact)]:
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)
        agent = cache.http_headers()["User-Agent"]
        assert agent.startswith(f"Find-a-Line/{cache.VERSION} ("), agent
        assert _versions_logged(agent) == (cache.VERSION, cache.VERSION), VERSION_RULE


def test_an_unknown_version_is_unknown_on_both_sides(monkeypatch):
    """cache.py loaded where pyproject.toml cannot be read (its _version gives "unknown"): the server logs "unknown"
    and stats keeps it."""
    import tomllib

    def unreadable(*args, **kwargs):
        raise KeyError("project")
    monkeypatch.setattr(tomllib, "load", unreadable)
    spec = importlib.util.spec_from_file_location("cache_without_a_version", cache.__file__)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    assert fresh.VERSION == "unknown"
    monkeypatch.delenv("FINDALINE_PUBLIC_URL", raising=False)
    assert _versions_logged(fresh.http_headers()["User-Agent"]) == ("unknown", "unknown")


@pytest.mark.parametrize("version, logged", [("0.1.0", "0.1.0"), ("1.2", "1.2"), ("999.999.999", "999.999.999"),
                                             ("0.2.0rc1", "0.2.0rc"), ("1.0.0.dev3", "1.0.0.dev"),
                                             ("1.2.3.post4", "1.2.3.post"), ("0.1.0+local", "0.1.0"),
                                             ("1000.0.0", "other"), ("1.2.3.4", "other"), ("1", "other")])
def test_the_version_rule_on_both_sides(version, logged):
    """The forms the rule keeps and those it does not, through the server's map and the tool's function alike: a
    release with a four-digit part or a fourth number would be logged as "other". The rule's own tests:
    tests/test_mirror_deploy.py test_log_dataset_and_version_forms, tests/test_mirror_publish.py
    test_stats_counts_the_clients_versions."""
    assert _versions_logged(f"Find-a-Line/{version} (highline finder; self-hosted)") == (logged, logged), VERSION_RULE


# 4. The log's keys, the publish tool's stats and the privacy sentence

def _log_format() -> str:
    found = re.search(r"log_format mirror escape=json((?:\s*'[^']*')+);", _nginx())
    assert found
    return "".join(re.findall(r"'([^']*)'", found.group(1)))


def test_the_logs_keys_and_the_privacy_sentence():
    """nginx.conf's log_format holds exactly the keys t s b rt ds a lim v; the publish tool's docstring names them
    and its stats reads no other; the approved privacy sentence names what each one holds and nothing more."""
    line = _log_format()
    assert re.findall(r'"(\w+)":', line) == LOG_KEYS
    assert "t, s, b, rt, ds, a, lim, v" in " ".join(mp.__doc__.split())
    source = _read("tools", "mirror_publish.py")
    stats = source[source.index("def stats("):source.index("def main(")]
    read = set(re.findall(r'record\["(\w+)"\]', stats)) | set(
        re.findall(r'"(\w+)"', re.search(r"for k in \(([^)]*)\)", stats).group(1)))
    assert read and read <= set(LOG_KEYS), read - set(LOG_KEYS)
    # The sentence: its list of what is written down, item by item, against the table
    text = _privacy_text()
    listed = re.search(r"The server writes down (.+?) of each request\.", text).group(1)
    items = [item.strip() for item in re.split(r",(?: and)? ", listed)]
    assert set(SENTENCE_OF_KEY) == set(LOG_KEYS)
    assert sorted(set(SENTENCE_OF_KEY.values())) == sorted(items), "a key or a noun of the sentence changed alone"
    assert "It keeps this for 14 days" in text   # tests/test_mirror_deploy.py test_log_keys_and_days: KEEP_DAYS=14


def test_stats_reads_a_line_the_server_writes(monkeypatch, capsys):
    """A line rendered from nginx.conf's log_format (its variables given values a tile request would have) is read
    by the publish tool's stats as a request of its dataset, with its version, and its refusing limit counted: a key
    renamed on one side makes it an unreadable line."""
    values = {"time_iso8601": "2026-11-16T10:00:00+00:00", "status": "429", "body_bytes_sent": "4096",
              "request_time": "0.012", "mirror_dataset": "madeira", "remote_addr": "203.0.113.7",
              "mirror_limit": "rate", "mirror_version": _versions_logged(cache.http_headers()["User-Agent"])[0]}
    rendered = re.sub(r"\$(\w+)", lambda m: values[m.group(1)], _log_format())
    record = json.loads(rendered)
    assert list(record) == LOG_KEYS

    class Remote:
        def __init__(self, rc, place):
            pass

        def listing(self, path):
            return ["access-2026-11-16.log"]

        def cat(self, path):
            return rendered + "\n"
    monkeypatch.setattr(mp, "Remote", Remote)
    assert mp.stats("remote:logs", None) == 0
    out = capsys.readouterr().out
    assert "not log records" not in out
    assert re.search(r"2026-11-16  madeira +1 requests", out)
    assert re.search(r"2026-11-16  rate +1\n", out)
    assert f"  {cache.VERSION:<20} {1:>9}" in out
    assert "203.0.113.7" not in out


# 5. The served patterns, the client's paths and the publish tool's layout

def _served(path: str) -> bool:
    """Whether nginx.conf serves a path (its exact locations, not the internal /__ ones, and its regular ones)."""
    conf = _nginx()
    exact = [p for p in re.findall(r"^\s*location = (\S+)", conf, re.M) if not p.startswith("/__")]
    return path in exact or any(re.search(p, path) for p in re.findall(r'^\s*location ~ "([^"]+)"', conf, re.M))


def test_served_patterns_take_the_clients_and_the_tools_paths():
    """Every path the client builds (<MIRROR_URL>/v1/tiles/<mirror folder>/index.json and grid_tile_name, for the three
    datasets' folders, their averaged resolutions and a 0.5 m folder) and every path the publish tool lays out under
    <root>/public (its tiles by _index_tiles, index.json, the card, datasets.json) is served; the tool's temporary list
    is not; its dataset names are the server's <dataset> part. The client's half with more names:
    tests/test_mirror_deploy.py test_served_patterns_match_the_names_of_the_client."""
    from sources.catalogue import SOURCES
    assert tilebases.TILES_PATH == "v1/tiles" and mp.TILES == "public/v1/tiles"
    assert mp.LIST == "public/v1/datasets.json" and _served("/v1/datasets.json")
    assert not _served("/" + mp.LIST_TMP.removeprefix("public/"))
    keys = [(0, 0), (12, 2), (-3, 4), (-301, -631), (40719, 33)]
    index = {"tiles": {f"{i}_{j}": "a" * 64 for i, j in keys}, "block": mp.BLOCK}
    for name, row in mp.PUBLISHABLE.items():
        assert _served(f"/v1/tiles/{name}/{mp.CARD}"), name
        for folder in mp.required_folders(row["source_id"]):
            assert folder.split("/")[0] == name
            native = float(folder.rsplit("/", 1)[1].removesuffix("m"))
            for res in {native, 0.5}:
                base = "/v1/tiles/" + renamed(folder, native, res)
                assert _served(f"{base}/index.json"), base
                for i, j in keys:
                    assert _served(f"{base}/{tilebases.grid_tile_name(i, j)}"), (base, i, j)
                for path in mp._index_tiles(index):
                    assert _served(f"{base}/{path}"), (base, path)
    assert res_name(0.5) == "0.5m"
    # The client's mirror folders are the tool's: every GridTiles reader with a mirror folder lies under a dataset
    # of PUBLISHABLE (the tool's own test: tests/test_mirror_publish.py test_publishable_datasets_are_the_mirrors_datasets)
    from sources.layers.gridtiles import GridTiles
    folders = {reader.mirror for src in SOURCES.values() for layer in (src.nmt, src.nmpt) if isinstance(layer, GridTiles)
               for reader in layer.readers.values() if reader.mirror}
    assert folders and {f.split("/")[0] for f in folders} <= set(mp.PUBLISHABLE)


def test_dataset_names_are_the_servers():
    """mirror_publish.DATASET_NAME is the <dataset> part of every served pattern, and every name of PUBLISHABLE fits the
    40 characters the server's log keeps of it (longer names are logged as "-": nginx.conf's map $mirror_dataset)."""
    part = mp.DATASET_NAME.pattern.removeprefix("^").removesuffix("$")
    patterns = re.findall(r'^\s*location ~ "\^/v1/tiles/([^/]+)/', _nginx(), re.M)
    assert len(patterns) == 3 and set(patterns) == {part}
    for name in mp.PUBLISHABLE:
        assert mp.DATASET_NAME.fullmatch(name)
        assert _mapped("mirror_dataset", f"/v1/tiles/{name}/README.md", "-") == name
        assert len(name) <= 40


# 6. The block size

def test_block_is_one_number():
    """BLOCK (tiles per folder side) of the publish tool, the cutting tools and the client's index check
    (tilebases.BLOCK, which grid_tile_name uses by default): one number, 10. The tool's own test:
    tests/test_mirror_publish.py test_block_is_the_tools_block."""
    assert mp.BLOCK == sk_tiles.BLOCK == mirror_tiles.BLOCK == tilebases.BLOCK == 10
    assert tilebases.grid_tile_name(12, 34) == tilebases.grid_tile_name(12, 34, mp.BLOCK) == "1_3/12_34.tif"


# 7. PUBLISHABLE against the catalogue and the cutting tools

def test_publishable_is_the_catalogues_and_the_tools():
    """PUBLISHABLE's datasets are tools/mirror_tiles.py DATASETS' folders and Slovakia; each source_id is a catalogue
    source whose GridTiles mirror folders lie under the dataset, and each DATASETS entry's source is the one its row
    names. The tool's own tests (skipped without rclone): tests/test_mirror_publish.py
    test_publishable_datasets_are_the_mirrors_datasets, test_resolutions_required_are_the_catalogues."""
    from sources.catalogue import SOURCES
    assert set(mp.PUBLISHABLE) == {spec["folder"] for spec in mirror_tiles.DATASETS.values()} | {"slovakia"}
    for name, row in mp.PUBLISHABLE.items():
        assert row["dataset"] == name and row["source_id"] in SOURCES, name
        folders = mp.required_folders(row["source_id"])
        assert folders and {f.split("/")[0] for f in folders} == {name}, name
    for spec in mirror_tiles.DATASETS.values():
        folder = mirror_tiles.tile_folder(spec)
        row = mp.PUBLISHABLE[spec["folder"]]
        assert folder in mp.required_folders(row["source_id"]), folder
