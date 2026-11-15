"""tools/mirror_publish.py: publishing the mirror's datasets (docs/mirror-hosting/spec.md, solution B), on fixture
mirrors in tmp_path with rclone's local backend standing in for the server (an alias remote of a folder: the root
of the remote is the server's <root>). Skipped where rclone is not installed (FINDALINE_RCLONE or PATH)."""

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import mirror_publish as mp  # noqa: E402
import mirror_tiles  # noqa: E402
import sk_tiles  # noqa: E402
import sources as src  # noqa: E402
from sources.catalogue import SOURCES  # noqa: E402

RCLONE = os.environ.get(mp.RCLONE_ENV) or shutil.which("rclone")
pytestmark = pytest.mark.skipif(not RCLONE, reason="rclone is not installed (FINDALINE_RCLONE or PATH)")

REAL_CALL = mp.Rclone._call  # rclone itself, before any test's patch
REMOTE = "mirrorfixture"  # the remote's name: no line of the tool's output may hold it
# The fixture datasets: the real dataset names (their rows, cards and catalogue sources are used), tiny tiles
DATASETS = {
    "slovakia": {f"{p}/{r}": [(1, 2), (-3, 4), (12, 2)] for p in ("dmr5", "dmp1") for r in ("1m", "2m", "5m")},
    "madeira": {"dtm/2m": [(143, 1833), (144, 1833), (150, 1840)]},
    "aosta": {"dtm/2m": [(176, 2518), (177, 2519)]},
}
NULLS = [(0, 0)]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_dataset(mirror, name, products=None):
    """A dataset folder as tools/sk_tiles.py lays it out: tiles of random bytes, an index.json per product folder
    (a null tile too). {path below the dataset: sha256} of the tiles and indexes."""
    files = {}
    for folder, keys in (products or DATASETS[name]).items():
        index = {"tiles": {f"{i}_{j}": None for i, j in NULLS}, "block": 10}
        for n, (i, j) in enumerate(keys):
            rel = f"{folder}/{src.grid_tile_name(i, j)}"
            data = os.urandom(3000 + 7 * n)
            path = mirror / name / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            index["tiles"][f"{i}_{j}"] = files[rel] = _sha(data)
        data = json.dumps(index).encode()
        (mirror / name / folder / "index.json").write_bytes(data)
        files[f"{folder}/index.json"] = _sha(data)
    return files


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A master mirror with the three datasets, a server folder (<root>), an rclone config naming it, and no
    trace of the user's own setup (FINDALINE_MIRROR, the mirror's address, the rclone config)."""
    mirror, server = tmp_path / "master", tmp_path / "server"
    mirror.mkdir()
    server.mkdir()
    files = {name: make_dataset(mirror, name) for name in DATASETS}
    config = tmp_path / "rclone.conf"
    config.write_text(f"[{REMOTE}]\ntype = alias\nremote = {server.as_posix()}\n", encoding="utf-8")
    monkeypatch.delenv("FINDALINE_MIRROR", raising=False)
    monkeypatch.setenv("FINDALINE_MIRROR_URL", "")
    monkeypatch.setenv("RCLONE_CONFIG", str(config))  # also for a call that would forget --config
    monkeypatch.setenv(mp.RCLONE_ENV, RCLONE)
    monkeypatch.setattr(mp, "MARGIN_BYTES", 1000)  # the real 10 GB margin is its own test

    class World:
        pass
    w = World()
    w.tmp, w.mirror, w.server, w.files, w.config = tmp_path, mirror, server, files, str(config)

    def run(*args):
        return mp.main([*args, "--config", w.config])
    w.run = run
    w.to = f"{REMOTE}:"
    return w


def _clean_output(text, world):
    """No line of the tool's output names the remote or the master's place."""
    assert REMOTE not in text
    assert str(world.mirror) not in text and world.mirror.as_posix() not in text
    assert str(world.server) not in text and world.server.as_posix() not in text


def tree(folder):
    """{path below folder: bytes} of every file under folder ({} when it does not exist)."""
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def published_ok(world, name, card=None):
    """public/v1/tiles/<name> holds exactly the master's listed files and the card."""
    got = tree(world.server / "public" / "v1" / "tiles" / name)
    assert {k: _sha(v) for k, v in got.items() if k != "README.md"} == world.files[name]
    assert got["README.md"].decode("utf-8") == (card or mp.cards()[name])


def test_publish_unpublish_and_the_list(world, capsys):
    """A publish copies exactly the listed files and the card into public, writes datasets.json from the server's
    copy (the indexes' sha256 the master's, the credit the catalogue's), leaves no lock and no staging; a stray .part
    and a file of another name beside the tiles stay behind; unpublish leaves no file of the dataset under public
    and no entry in datasets.json."""
    (world.mirror / "madeira" / "dtm" / "2m" / "14_183" / "143_1833.tif.part").write_bytes(b"stray")
    (world.mirror / "madeira" / "dtm" / "2m" / "notes.txt").write_bytes(b"stray")
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 0
    assert world.run("publish", "aosta", "--to", world.to, "--mirror", str(world.mirror)) == 0
    published_ok(world, "madeira")
    published_ok(world, "aosta")
    public = world.server / "public" / "v1"
    assert not any(".part" in p or "notes.txt" in p for p in tree(public))
    assert not (world.server / "staging" / ".lock").exists() and not (world.server / "staging" / "madeira").exists()
    listing = json.loads((public / "datasets.json").read_text(encoding="utf-8"))
    assert listing["version"] == 1 and listing["generated"].endswith("Z")
    by_id = {d["id"]: d for d in listing["datasets"]}
    assert set(by_id) == {"madeira", "aosta"}
    for name, entry in by_id.items():
        row = mp.PUBLISHABLE[name]
        assert (entry["title"], entry["licence"], entry["source"]) == (row["title"], row["licence"], row["basis_url"])
        assert entry["attribution"] == SOURCES[row["source_id"]].attribution
        [product] = entry["products"]
        assert product["path"] == f"{name}/dtm/2m"
        index = (world.mirror / name / "dtm" / "2m" / "index.json").read_bytes()
        assert product["index_sha256"] == _sha(index)
        tiles = [p for p in world.files[name] if p.endswith(".tif")]
        assert product["tiles"] == len(tiles)
        assert product["bytes"] == len(index) + sum((world.mirror / name / p).stat().st_size for p in tiles)
    assert not (public / ".datasets.json.new").exists()

    assert world.run("unpublish", "madeira", "--to", world.to) == 0
    assert not (public / "tiles" / "madeira").exists()
    listing = json.loads((public / "datasets.json").read_text(encoding="utf-8"))
    assert [d["id"] for d in listing["datasets"]] == ["aosta"]
    [trashed] = os.listdir(world.server / "trash")
    assert trashed.startswith("madeira-") and mp.trash_age_days(trashed, mp._now()) < 1
    assert not (world.server / "staging" / ".lock").exists()
    _clean_output(capsys.readouterr().out, world)


def test_slovakia_with_its_averaged_folders(world, capsys):
    """A dataset of two products at three resolutions each: every folder published, each in datasets.json."""
    assert world.run("publish", "slovakia", "--to", world.to, "--mirror", str(world.mirror)) == 0
    published_ok(world, "slovakia")
    listing = json.loads((world.server / "public" / "v1" / "datasets.json").read_text(encoding="utf-8"))
    paths = [p["path"] for p in listing["datasets"][0]["products"]]
    assert sorted(paths) == sorted(f"slovakia/{f}" for f in DATASETS["slovakia"])
    _clean_output(capsys.readouterr().out, world)


def _nothing_written(world):
    assert tree(world.server) == {}


@pytest.mark.parametrize("case, reason", [
    ("unlisted", "no row in PUBLISHABLE"),
    ("unapproved", "not approved"),
    ("empty field", "notes is empty"),
    ("partial", "partial"),
    ("damaged", "sha256 differs from its index"),
    ("missing tile", "missing"),
    ("unlisted tile", "not listed in its index"),
    ("no resolution", "<mirror>/slovakia/dmr5/5m: no index.json"),
])
def test_refusals(world, monkeypatch, capsys, case, reason):
    """Each refusal says why, and nothing is written on the server."""
    name = "slovakia" if case == "no resolution" else "madeira"
    folder = world.mirror / "madeira" / "dtm" / "2m"
    tile = folder / "14_183" / "143_1833.tif"
    if case == "unlisted":
        name = "nowhere"
        make_dataset(world.mirror, "nowhere", {"dtm/2m": [(1, 1)]})
    elif case == "unapproved":
        monkeypatch.setitem(mp.PUBLISHABLE, "madeira", {**mp.PUBLISHABLE["madeira"], "approved": ""})
    elif case == "empty field":
        monkeypatch.setitem(mp.PUBLISHABLE, "madeira", {**mp.PUBLISHABLE["madeira"], "notes": " "})
    elif case == "partial":
        index = json.loads((folder / "index.json").read_text())
        (folder / "index.json").write_text(json.dumps({**index, "partial": True}))
    elif case == "damaged":
        data = bytearray(tile.read_bytes())
        data[100] ^= 1
        tile.write_bytes(bytes(data))
    elif case == "missing tile":
        tile.unlink()
    elif case == "unlisted tile":
        (folder / "14_183" / "149_1833.tif").write_bytes(b"x")
    elif case == "no resolution":
        shutil.rmtree(world.mirror / "slovakia" / "dmr5" / "5m")
    assert world.run("publish", name, "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "refused:" in out and reason in out, out
    _clean_output(out, world)
    _nothing_written(world)


def test_free_space_refused(world, monkeypatch, capsys):
    monkeypatch.setattr(mp, "MARGIN_BYTES", 10 ** 18)
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "refused:" in out and "GB to keep" in out
    _nothing_written(world)


def test_no_sha256_on_the_remote(world, monkeypatch, capsys):
    """A remote that reports no sha256 is refused; --read-back hashes by reading the files back instead."""
    monkeypatch.setattr(mp.Remote, "hashes", lambda self: ["md5", "sha1"])
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "no sha256" in out and "--read-back" in out
    _nothing_written(world)
    calls = []
    real = mp.Rclone._call

    def spy(self, argv, data, progress):
        calls.append(argv)
        return real(self, argv, data, progress)
    monkeypatch.setattr(mp.Rclone, "_call", spy)
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror), "--read-back") == 0
    published_ok(world, "madeira")
    assert any("checksum" in a and "--download" in a for a in calls)


def test_one_letter_remote_refused(world, capsys):
    assert world.run("publish", "madeira", "--to", "z:mirror", "--mirror", str(world.mirror)) == 1
    assert "one letter" in capsys.readouterr().out


def test_rclone_missing_or_too_old(world, monkeypatch, capsys):
    monkeypatch.setenv(mp.RCLONE_ENV, str(world.tmp / "no-rclone.exe"))
    monkeypatch.setenv("PATH", "")
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "rclone was not found" in out and "1.76" in out
    monkeypatch.setenv(mp.RCLONE_ENV, RCLONE)
    monkeypatch.setattr(mp.Rclone, "_call", lambda self, argv, data, progress: subprocess.CompletedProcess(
        argv, 0, b"rclone v1.75.2\n- os/version: test\n", b""))
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "1.75.2 is too old" in out and "1.76" in out
    _nothing_written(world)


def _public_never_partial(world, names):
    """After every rclone call: each of the datasets under public is absent or complete."""
    for name in names:
        folder = world.server / "public" / "v1" / "tiles" / name
        if folder.exists():
            got = {k for k in tree(folder) if k != "README.md"}
            assert got == set(world.files[name]), f"public held a partial {name} ({len(got)} files)"
            assert (folder / "README.md").exists()


def _watch(monkeypatch, world, names, before=None, after=None):
    """rclone's calls run for real, with the public tree checked after every one; before(argv) may change the
    arguments, after(argv, done) the result."""
    calls = []

    def call(self, argv, data, progress):
        argv = before(argv) if before else argv
        done = REAL_CALL(self, argv, data, progress)
        done = after(argv, done) if after else done
        calls.append(argv)
        _public_never_partial(world, names)
        return done
    monkeypatch.setattr(mp.Rclone, "_call", call)
    return calls


def _cut_copy(world, n):
    """An rclone that copies only the first n files of its list and stops (exit 5)."""
    state = {}

    def before(argv):
        if "copy" in argv and "--files-from" in argv:
            k = argv.index("--files-from") + 1
            names = open(argv[k], encoding="utf-8").read().splitlines()[:n]
            short = world.tmp / "short.txt"
            short.write_text("\n".join(names) + "\n", encoding="utf-8")
            state["cut"] = True
            return argv[:k] + [str(short)] + argv[k + 1:]
        return argv

    def after(argv, done):
        if state.pop("cut", False):
            return subprocess.CompletedProcess(argv, 5, done.stdout, done.stderr)
        return done
    return before, after


def test_interrupted_publish_resumes(world, monkeypatch, capsys):
    """rclone stopped after 2 files: the publish stops, the lock is released, public never held the dataset in
    part; the next publish copies only the rest and completes. A re-publish with --same-values swaps it in through
    the trash, public never partial either."""
    before, after = _cut_copy(world, 2)
    calls = _watch(monkeypatch, world, ["madeira"], before, after)
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "stopped:" in out and "publish again" in out
    assert not (world.server / "public").exists() and not (world.server / "staging" / ".lock").exists()
    assert len(tree(world.server / "staging" / "madeira")) == 2
    _watch(monkeypatch, world, ["madeira"])
    combined = []
    real_run = mp.Rclone.run

    def run(self, *args, **kw):
        if args and args[0] == "copy":
            args = args + ("--combined", str(world.tmp / "combined.txt"))
        return real_run(self, *args, **kw)
    monkeypatch.setattr(mp.Rclone, "run", run)
    code = world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror))
    assert code == 0, capsys.readouterr().out
    combined = (world.tmp / "combined.txt").read_text(encoding="utf-8").splitlines()
    assert sorted(line[0] for line in combined) == sorted("==" + "+" * (len(world.files["madeira"]) - 2))
    published_ok(world, "madeira")
    assert calls

    # the same values again: refused without --same-values, swapped in with it
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    assert "--same-values" in capsys.readouterr().out
    calls = _watch(monkeypatch, world, ["madeira"])
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror), "--same-values") == 0
    published_ok(world, "madeira")
    [trashed] = os.listdir(world.server / "trash")
    assert {k for k in tree(world.server / "trash" / trashed) if k != "README.md"} == set(world.files["madeira"])
    assert sum("moveto" in a for a in calls) == 3  # to trash, staging to public, datasets.json
    _clean_output(capsys.readouterr().out, world)


def test_staged_file_changed_is_caught_before_any_move(world, monkeypatch, capsys):
    """A staged tile changed on the server after the copy, its size and time kept (a copy would skip it): the
    staged verify finds it, no move happens, the file is deleted from staging, the next publish completes."""
    target = world.server / "staging" / "madeira" / "dtm" / "2m" / "14_183" / "143_1833.tif"
    state = {"done": False}

    def after(argv, done):
        if "copy" in argv and not state["done"]:
            state["done"] = True
            stat = target.stat()
            data = bytearray(target.read_bytes())
            data[10] ^= 0xFF
            target.write_bytes(bytes(data))
            os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        return done
    calls = _watch(monkeypatch, world, ["madeira"], after=after)
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "differs" in out and "publish again" in out
    assert not any("moveto" in a for a in calls)
    assert not (world.server / "public").exists() and not target.exists()
    assert not (world.server / "staging" / ".lock").exists()
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 0
    published_ok(world, "madeira")
    _clean_output(capsys.readouterr().out, world)


def test_second_publish_refused_on_the_lock(world, capsys):
    lock = world.server / "staging" / ".lock"
    lock.parent.mkdir(parents=True)
    held = json.dumps({"pc": "other-pc", "time": "2026-11-16T10:00:00Z", "command": "publish aosta"})
    lock.write_text(held)
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "locked by other-pc" in out and "--break-lock" in out
    assert lock.read_text() == held and not (world.server / "public").exists()
    assert world.run("unpublish", "madeira", "--to", world.to) == 1
    assert lock.read_text() == held
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror), "--break-lock") == 0
    published_ok(world, "madeira")
    assert not lock.exists()


def test_a_published_folder_without_a_row_stops_the_list(world, capsys):
    stray = world.server / "public" / "v1" / "tiles" / "unknown"
    stray.mkdir(parents=True)
    (stray / "README.md").write_text("x")
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "no row in PUBLISHABLE" in out and "lock" in out
    assert (world.server / "staging" / ".lock").exists()  # kept: the server's state needs a look


@pytest.mark.parametrize("where", ["folder", "remote"])
def test_verify_finds_each_fault(world, capsys, where):
    """verify on a folder (hashed by the tool) and on a remote (hashed by rclone checksum) finds a flipped byte, a
    missing tile and an unlisted file, and passes a whole dataset."""
    place = str(world.mirror / "aosta") if where == "folder" else f"{REMOTE}:aosta"
    if where == "remote":
        (world.tmp / "rclone.conf").write_text(f"[{REMOTE}]\ntype = alias\nremote = {world.mirror.as_posix()}\n")
    assert world.run("verify", place) == 0
    assert "0 faults" in capsys.readouterr().out
    folder = world.mirror / "aosta" / "dtm" / "2m"
    flipped = folder / "17_251" / "176_2518.tif"
    data = bytearray(flipped.read_bytes())
    data[5] ^= 1
    flipped.write_bytes(bytes(data))
    (folder / "17_251" / "177_2519.tif").unlink()
    (folder / "17_251" / "178_2519.tif").write_bytes(b"unlisted")
    assert world.run("verify", place) == 1
    out = capsys.readouterr().out
    assert "176_2518.tif: sha256 differs from its index" in out
    assert "177_2519.tif: missing" in out
    assert "178_2519.tif: not listed in its index" in out
    assert "3 faults" in out
    _clean_output(out, world)


def test_stats_prints_no_address(world, capsys):
    """stats on a recorded log: the counts per day and dataset, refusals per limit, client versions; no address,
    and a malformed line or a forged field is counted, not echoed."""
    logs = world.server / "logs"
    logs.mkdir()
    lines = [
        {"t": "2026-11-15T10:00:00Z", "s": 200, "b": 5_000_000, "rt": 1.2, "ds": "slovakia", "a": "203.0.113.7",
         "lim": "-", "v": "1.4.0"},
        {"t": "2026-11-15T10:00:01Z", "s": 206, "b": 1_000_000, "rt": 0.2, "ds": "slovakia", "a": "2001:db8::1",
         "lim": "-", "v": "other"},
        {"t": "2026-11-15T10:00:02Z", "s": 429, "b": 0, "rt": 0.0, "ds": "madeira", "a": "198.51.100.9",
         "lim": "rate", "v": "1.4.0"},
        {"t": "2026-11-15T10:00:03Z", "s": 404, "b": 150, "rt": 0.0, "ds": "198.51.100.10", "a": "198.51.100.10",
         "lim": "-", "v": "<script>198.51.100.11"},
    ]
    text = "\n".join(json.dumps(line) for line in lines) + "\nnot json from 192.0.2.44\n"
    (logs / "access-2026-11-15.log").write_text(text, encoding="utf-8")
    (logs / "access-2026-11-16.log").write_text(json.dumps({**lines[0], "t": "2026-11-16T00:00:00Z"}) + "\n")
    (logs / "heartbeat").write_text("x")
    assert world.run("stats", "--from", f"{REMOTE}:logs") == 0
    out = capsys.readouterr().out
    for address in ("203.0.113.7", "2001:db8::1", "198.51.100", "192.0.2.44"):
        assert address not in out
    assert "2026-11-15  slovakia             2 requests       0.006 GB" in out
    assert "2026-11-15  madeira              1 requests" in out
    assert "2026-11-15  rate                 1" in out
    assert "2026-11-16  slovakia             1 requests" in out
    assert "1 lines that are not log records" in out
    assert "  1.4.0" in out and "other" in out and "<script>" not in out
    _clean_output(out, world)


def test_clean_removes_old_trash_only(world, capsys):
    now = mp._now()
    old = (now - datetime.timedelta(days=8)).strftime(mp.STAMP)
    new = (now - datetime.timedelta(days=2)).strftime(mp.STAMP)
    for name in (f"madeira-{old}", f"aosta-{new}", f"a-b-c-{old}", "nostamp"):
        (world.server / "trash" / name).mkdir(parents=True)
        (world.server / "trash" / name / "f.txt").write_text("x")
    assert world.run("clean", "--to", world.to) == 0
    assert sorted(os.listdir(world.server / "trash")) == sorted([f"aosta-{new}", "nostamp"])
    assert world.run("clean", "--to", world.to, "--keep-days", "1") == 0
    assert os.listdir(world.server / "trash") == ["nostamp"]
    assert not (world.server / "staging" / ".lock").exists()
    _clean_output(capsys.readouterr().out, world)


# The pairs

def test_publishable_datasets_are_the_mirrors_datasets():
    """PUBLISHABLE's datasets: tools/mirror_tiles.py DATASETS and Slovakia (tools/sk_tiles.py); every one has a
    card; source_id names the catalogue source whose mirror folders lie under the dataset."""
    assert set(mp.PUBLISHABLE) == {spec["folder"] for spec in mirror_tiles.DATASETS.values()} | {"slovakia"}
    assert set(mp.cards()) == set(mp.PUBLISHABLE)
    assert mp.cards()["slovakia"] == sk_tiles.CARD
    for name, row in mp.PUBLISHABLE.items():
        assert row["dataset"] == name and row["source_id"] in SOURCES
        folders = mp.required_folders(row["source_id"])
        assert folders and all(f.split("/")[0] == name for f in folders)


def test_rows_complete_and_approved():
    for name, row in mp.PUBLISHABLE.items():
        assert mp.row_faults(row) == [], name
        assert set(row) == set(mp.ROW_FIELDS), name
        datetime.date.fromisoformat(row["basis_checked"])
        assert "2026-11-1" in row["approved"]
    assert mp.PUBLISHABLE["madeira"]["licence"] == mp.PUBLISHABLE["madeira"]["licence_url"] == "none"
    assert mp.row_faults({**mp.PUBLISHABLE["aosta"], "approved": ""}) == ["not approved (no `approved`)"]


def test_resolutions_required_are_the_catalogues():
    """The folders publish requires are each GridTiles layer's native and averaged ones (GridTiles(averaged=));
    each row's `changes` names every one of them."""
    sk = SOURCES["slovakia"]
    assert sk.nmt.averaged == (2, 5) and sk.nmpt.averaged == (2, 5)
    assert sorted(mp.required_folders("slovakia")) == sorted(
        f"slovakia/{p}/{r}" for p in ("dmr5", "dmp1") for r in ("1m", "2m", "5m"))
    assert mp.required_folders("madeira") == ["madeira/dtm/2m"]
    assert mp.required_folders("aosta_valley") == ["aosta/dtm/2m"]
    for name, row in mp.PUBLISHABLE.items():
        assert {f"{name}/{k}" for k in row["changes"]} == set(mp.required_folders(row["source_id"]))


def test_layout_is_grid_tile_name():
    """The tiles publish copies are named as GridTiles reads them (grid_tile_name, sk_tiles.tile_name)."""
    index = {"tiles": {"-3_4": "a", "12_2": "b", "0_0": None}, "block": 10}
    assert mp._index_tiles(index) == {src.grid_tile_name(-3, 4): "a", sk_tiles.tile_name(12, 2): "b"}
    assert set(mp._index_tiles(index)) == {"-1_0/-3_4.tif", "1_0/12_2.tif"}


def test_cards_state_the_changes():
    """Each served card says what was changed (Slovakia's names the 2 m and 5 m averaging) and that it is not
    endorsed; Valle d'Aosta's carries the credit sentence and the licence's link."""
    def changes(card):
        return " ".join(card.split("Changes made:", 1)[1].split("\n\n", 1)[0].split())

    for name, card in mp.cards().items():
        assert "5 mm" in changes(card) and "Values are not otherwise changed" in changes(card), name
        assert "not endorsed by" in card
    sk = changes(mp.cards()["slovakia"])
    assert "2 m and 5 m" in sk and "mean" in sk and "2 × 2" in sk and "5 × 5" in sk
    aosta = mp.cards()["aosta"]
    assert SOURCES["aosta_valley"].attribution in aosta and mp.PUBLISHABLE["aosta"]["licence_url"] in aosta
