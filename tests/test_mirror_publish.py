"""tools/mirror_publish.py: publishing the mirror's datasets (docs/mirror-hosting/spec.md, solution B), on fixture
mirrors in tmp_path with rclone's local backend standing in for the server (an alias remote of a folder: the root
of the remote is the server's <root>). Skipped where rclone is not installed (FINDALINE_RCLONE or PATH)."""

import contextlib
import datetime
import hashlib
import io
import json
import os
import re
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
REAL_MARGIN = mp.MARGIN_BYTES  # before the fixture lowers it
REMOTE = "mirrorfixture"  # the remote's name: no line of the tool's output may hold it
# The fixture datasets: the real dataset names (their rows, cards and catalogue sources are used), tiny tiles
DATASETS = {
    "slovakia": {f"{p}/{r}": [(1, 2), (-3, 4), (12, 2), (-301, -631)]
                 for p in ("dmr5", "dmp1") for r in ("1m", "2m", "5m")},
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
    monkeypatch.setenv("FINDALINE_MIRROR_URL", "off")
    monkeypatch.setenv("RCLONE_CONFIG", str(config))  # also for a call that would forget --config
    monkeypatch.setenv(mp.RCLONE_ENV, RCLONE)
    monkeypatch.setattr(mp, "MARGIN_BYTES", 1000)  # the real 10 GB margin is its own test

    class World:
        pass
    w = World()
    w.tmp, w.mirror, w.server, w.files, w.config = tmp_path, mirror, server, files, str(config)

    def run(*args):
        """The tool in this process; every line it prints checked by _clean_output, then printed again (capsys)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = mp.main([*args, "--config", w.config])
        _clean_output(out.getvalue(), w)
        sys.stdout.write(out.getvalue())
        return code
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
    capsys.readouterr()
    # the server's copy verified remotely: Slovakia's tile numbers are negative (S-JTSK), so are the SUM's paths
    assert world.run("verify", f"{REMOTE}:public/v1/tiles/slovakia") == 0
    tiles = sum(1 for p in world.files["slovakia"] if p.endswith(".tif"))
    assert f"{tiles} tiles checked, 0 faults" in capsys.readouterr().out
    target = world.server / "public" / "v1" / "tiles" / "slovakia" / "dmr5" / "5m" / "-31_-64" / "-301_-631.tif"
    data = bytearray(target.read_bytes())
    data[0] ^= 1
    target.write_bytes(bytes(data))
    assert world.run("verify", f"{REMOTE}:public/v1/tiles/slovakia") == 1
    assert "dmr5/5m/-31_-64/-301_-631.tif: sha256 differs from its index" in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["nothing moved", "part moved"])
def test_a_move_checked_wrong_stops_with_the_lock(world, monkeypatch, capsys, mode):
    """Step 4's check: a moveto that reports success but moved nothing, or only part, stops the tool with the lock
    kept and says where the complete copy is."""
    staging = world.server / "staging" / "madeira"
    public = world.server / "public" / "v1" / "tiles" / "madeira"

    def call(self, argv, data, progress):
        if "moveto" in argv and argv[-2].endswith("staging/madeira"):
            if mode == "part moved":
                some = sorted(p for p in staging.rglob("*.tif"))[:1]
                for p in some:
                    to = public / p.relative_to(staging)
                    to.parent.mkdir(parents=True, exist_ok=True)
                    p.replace(to)
            return subprocess.CompletedProcess(argv, 0, b"", b"")
        return REAL_CALL(self, argv, data, progress)
    monkeypatch.setattr(mp.Rclone, "_call", call)
    assert world.run("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)) == 1
    out = capsys.readouterr().out
    assert "stopped:" in out and "the lock staging/.lock is kept" in out
    assert (world.server / "staging" / ".lock").exists()
    if mode == "nothing moved":
        assert "the complete copy is in staging/madeira" in out
    else:
        assert "the complete copy is in neither" in out


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
    assert "locked since 2026-11-16T10:00:00Z (publish aosta)" in out and "--break-lock" in out
    assert "other-pc" not in out  # the other PC's name stays in the lock file, never in the output
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
        {"t": "2026-11-15T10:00:04Z", "s": 200, "b": 10, "rt": 0.0, "ds": "-", "a": "198.51.100.12",
         "lim": "-", "v": "198.51.100.12"},
    ] + [  # an address spelt other ways, in every free field
        {"t": "2026-11-15T10:00:05Z", "s": 429, "b": 0, "rt": 0.0, "ds": spelt, "a": "203.0.113.7", "lim": spelt,
         "v": spelt} for spelt in ("203-0-113-7", "203.0.113_7", "1.2.3.4", "ip-203-0-113-7", "3405803783",
                                   "203_0_113_7")]
    text = "\n".join(json.dumps(line) for line in lines) + "\nnot json from 192.0.2.44\n"
    (logs / "access-2026-11-15.log").write_text(text, encoding="utf-8")
    (logs / "access-2026-11-16.log").write_text(json.dumps({**lines[0], "t": "2026-11-16T00:00:00Z"}) + "\n")
    (logs / "heartbeat").write_text("x")
    assert world.run("stats", "--from", f"{REMOTE}:logs") == 0
    out = capsys.readouterr().out
    for address in ("203.0.113.7", "2001:db8::1", "198.51.100", "192.0.2.44", "203-0-113-7", "203.0.113_7",
                    "1.2.3.4", "3405803783", "203_0", "113"):
        assert address not in out
    assert "2026-11-15  other                7 requests" in out  # the spelt addresses' "ds"
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

# The datasets tools/mirror_tiles.py cuts that have no PUBLISHABLE row (no approval to publish them): Madeira's
# islets of batch 6. A new one is named here when it is added; a row is added only on the user's word
CUT_WITHOUT_A_ROW = set()  # Madeira's islets got their rows (U55, 2026-11-17)


def test_publishable_datasets_are_the_mirrors_datasets():
    """Every PUBLISHABLE row's dataset is cut by tools/mirror_tiles.py (DATASETS, by its folder name) or is Slovakia
    (tools/sk_tiles.py); the datasets cut without a row are allowed and named (CUT_WITHOUT_A_ROW); every dataset has a
    card, Madeira's and Valle d'Aosta's the fixed texts of before; source_id names the catalogue source whose mirror
    folders lie under the dataset."""
    cut = {mirror_tiles.dataset(key).name for key in mirror_tiles.DATASETS}
    assert set(mp.PUBLISHABLE) <= cut | {"slovakia"}
    assert cut - set(mp.PUBLISHABLE) == CUT_WITHOUT_A_ROW
    assert set(mp.cards()) == cut | {"slovakia"}
    assert mp.cards()["slovakia"] == sk_tiles.CARD
    assert mp.cards()["madeira"] == mirror_tiles.MADEIRA_CARD and mp.cards()["aosta"] == mirror_tiles.AOSTA_CARD
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
    a, b = "a" * 64, "b" * 64
    index = {"tiles": {"-3_4": a, "12_2": b, "0_0": None}, "block": 10}
    assert mp._index_tiles(index) == {src.grid_tile_name(-3, 4): a, sk_tiles.tile_name(12, 2): b}
    assert set(mp._index_tiles(index)) == {"-1_0/-3_4.tif", "1_0/12_2.tif"}


def test_cards_state_the_changes():
    """Each served card says what was changed (Slovakia's names the 2 m and 5 m averaging) and that it is not
    endorsed; Valle d'Aosta's carries the credit sentence and the licence's link."""
    def changes(card):
        return " ".join(card.split("Changes made:", 1)[1].split("\n\n", 1)[0].split())

    served = {name: card for name, card in mp.cards().items() if name in mp.PUBLISHABLE}
    assert set(served) == {"slovakia", "madeira", "aosta", "porto-santo", "desertas", "selvagens"}
    for name, card in served.items():
        # the fixed cards of before say it as a sentence of its own, the generated ones after "Heights ...;"
        fixed = name in ("slovakia", "madeira", "aosta")
        said = "Values are not otherwise changed" if fixed else "; values are not otherwise changed"
        assert "5 mm" in changes(card) and said in changes(card), name
        assert "not endorsed by" in card
    # the islets' own changes (U56): the Desertas' label replaced, Porto Santo's float64 stored as float32
    assert ("the file's reference-system label replaced: it is labelled EPSG:3061, its coordinates are in EPSG:5016 "
            "(PTRA08 / UTM zone 28N); nothing reprojected") in changes(served["desertas"])
    assert "the values, float64 in the file, stored as float32 (within those 5 mm)" in changes(served["porto-santo"])
    assert "label replaced" not in served["selvagens"] and "float64" not in served["selvagens"]
    sk = changes(mp.cards()["slovakia"])
    assert "2 m and 5 m" in sk and "mean" in sk and "2 × 2" in sk and "5 × 5" in sk
    aosta = mp.cards()["aosta"]
    assert SOURCES["aosta_valley"].attribution in aosta and mp.PUBLISHABLE["aosta"]["licence_url"] in aosta


# Fix round 1 (the code and scope reviews of 2026-11-16)

REAL_SHA = getattr(mp.Remote, "sha256_of", None)  # getattr: these tests also ran against the tool before it
SECRET = b"ERROR : sftp://secretuser@secret-host.example:2222//srv/secret-root/staging: failed\n"


def _publish(world, name, *more):
    return world.run("publish", name, "--to", world.to, "--mirror", str(world.mirror), *more)


def _other_lock():
    return json.dumps({"pc": "other-pc", "time": "2026-11-16T11:00:00Z", "command": "publish aosta",
                       "token": "b" * 32})


@pytest.mark.parametrize("name", ["slovakia/dmr5", "..", "../../../logs", "", ".", "/abs/path", "C:\\abs", "a\\b",
                                  "Madeira", "madeira/", "madeira\n"])
def test_bad_dataset_names_refused_before_any_request(world, monkeypatch, capsys, name):
    """F1: publish and unpublish refuse a name outside [a-z0-9_-]+ before any rclone call; the server's tree byte for
    byte as before."""
    assert _publish(world, "madeira") == 0 and _publish(world, "aosta") == 0
    before = tree(world.server)
    calls = _watch(monkeypatch, world, ["madeira", "aosta"])
    capsys.readouterr()
    for args in (("unpublish", name, "--to", world.to), ("publish", name, "--to", world.to, "--mirror",
                                                          str(world.mirror))):
        assert world.run(*args) == 1
        out = capsys.readouterr().out
        assert "refused:" in out and "not a dataset's name" in out
    assert calls == [] and tree(world.server) == before


def test_unpublish_only_a_published_folder(world, capsys):
    """F1: unpublish of a valid name that public/v1/tiles does not list: refused, nothing moved, datasets.json as it
    was, no lock left."""
    assert _publish(world, "madeira") == 0
    before = tree(world.server)
    assert world.run("unpublish", "slovakia", "--to", world.to) == 1
    out = capsys.readouterr().out
    assert "refused:" in out and "slovakia is not published" in out
    assert tree(world.server) == before


def test_release_leaves_another_runs_lock(world, monkeypatch, capsys):
    """F3 and N1: a lock overwritten by another run during this run's copy: this run stops at its next check point
    (before the move), touches nothing more and leaves the other run's lock as it is."""
    lock = world.server / "staging" / ".lock"

    def after(argv, done):
        if "copy" in argv:
            lock.write_text(_other_lock())
        return done
    calls = _watch(monkeypatch, world, ["madeira"], after=after)
    assert _publish(world, "madeira") == 1
    out = capsys.readouterr().out
    assert "another run took the lock (or it was broken) before the move of staging/madeira" in out
    assert lock.read_text() == _other_lock()
    assert not any("moveto" in a or "deletefile" in a for a in calls) and not (world.server / "public").exists()


def test_a_run_reading_another_token_after_its_write_stops(world, monkeypatch, capsys):
    """F3: two runs write the lock at the same moment: the one that reads back the other's token stops without
    touching anything (the other's lock stays)."""
    lock = world.server / "staging" / ".lock"
    real_write = mp.Remote.write

    def write(self, rel, data):
        real_write(self, rel, data)
        if rel == mp.LOCK:
            lock.write_text(_other_lock())
    monkeypatch.setattr(mp.Remote, "write", write)
    calls = _watch(monkeypatch, world, ["madeira"])
    assert _publish(world, "madeira") == 1
    out = capsys.readouterr().out
    assert "refused:" in out and "another run took the lock" in out
    assert lock.read_text() == _other_lock()
    assert not any("copy" in a or "deletefile" in a or "moveto" in a for a in calls)
    assert set(tree(world.server)) == {"staging/.lock"}


def test_server_hashing_proven_on_the_lock(world, monkeypatch, capsys):
    """U35: a server that does not give the lock file's sha256 (its config claims a hash it cannot compute) is
    refused right after the lock is taken: the lock released, nothing copied. The real server hashes it."""
    monkeypatch.setattr(mp.Remote, "sha256_of", lambda self, rel: None)
    calls = _watch(monkeypatch, world, ["madeira"])
    assert _publish(world, "madeira") == 1
    out = capsys.readouterr().out
    assert "could not hash the lock file" in out and "sha256sum_command = sha256sum" in out
    assert not any("copy" in a for a in calls) and tree(world.server) == {}
    monkeypatch.setattr(mp.Remote, "sha256_of", REAL_SHA)
    calls.clear()
    assert _publish(world, "madeira") == 0
    assert any("hashsum" in a for a in calls)
    calls.clear()
    assert world.run("unpublish", "madeira", "--to", world.to) == 0
    assert _publish(world, "madeira", "--read-back") == 0
    assert not any("hashsum" in a for a in calls)  # --read-back: no server hashing to prove


def test_a_failed_check_between_the_moves_keeps_the_lock(world, monkeypatch, capsys):
    """Scope R19 (a): a listing that fails inside the check of the first move keeps the lock and says where the
    complete copy is."""
    assert _publish(world, "madeira") == 0
    state = {"moved": False, "failed": False}

    def call(self, argv, data, progress):
        if state["moved"] and not state["failed"] and "lsjson" in argv and "-R" in argv:
            state["failed"] = True
            return subprocess.CompletedProcess(argv, 1, b"", SECRET)
        done = REAL_CALL(self, argv, data, progress)
        state["moved"] |= "moveto" in argv
        return done
    monkeypatch.setattr(mp.Rclone, "_call", call)
    assert _publish(world, "madeira", "--same-values") == 1
    out = capsys.readouterr().out
    assert "could not be checked; the complete copy is in one of them" in out
    assert "the lock staging/.lock is kept" in out and (world.server / "staging" / ".lock").exists()


@pytest.mark.parametrize("command", ["publish", "unpublish", "clean"])
def test_rclone_gone_after_the_lock(world, monkeypatch, capsys, command):
    """F9: rclone that cannot be started once the lock is written: the message says the lock is left and names
    --break-lock."""
    if command == "unpublish":
        assert _publish(world, "madeira") == 0
    state = {"locked": False}

    def call(self, argv, data, progress):
        if state["locked"]:
            raise OSError("gone")
        done = REAL_CALL(self, argv, data, progress)
        state["locked"] |= "rcat" in argv and argv[-1].endswith(".lock")
        return done
    monkeypatch.setattr(mp.Rclone, "_call", call)
    args = {"publish": ("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)),
            "unpublish": ("unpublish", "madeira", "--to", world.to), "clean": ("clean", "--to", world.to)}[command]
    capsys.readouterr()
    assert world.run(*args) == 1
    out = capsys.readouterr().out
    assert "rclone could not be started" in out and "the lock staging/.lock is left" in out and "--break-lock" in out
    assert (world.server / "staging" / ".lock").exists()


@pytest.mark.parametrize("where", ["folder", "remote"])
def test_verify_tiles_without_an_index(world, capsys, where):
    """F5: a product folder that has lost its index.json (its tiles still there) is a fault."""
    place = str(world.mirror / "slovakia") if where == "folder" else f"{REMOTE}:slovakia"
    if where == "remote":
        (world.tmp / "rclone.conf").write_text(f"[{REMOTE}]\ntype = alias\nremote = {world.mirror.as_posix()}\n")
    (world.mirror / "slovakia" / "dmr5" / "1m" / "index.json").unlink()
    assert world.run("verify", place) == 1
    assert "dmr5/1m/: tiles without an index.json" in capsys.readouterr().out


@pytest.mark.parametrize("bad", ["block 0", "block text", "block true", "block 5", "no block", "short digest",
                                 "digest with a newline", "path as a key", "tiles not an object"])
def test_verify_malformed_index_is_a_fault(world, capsys, bad):
    """F6: a malformed index is a fault on a folder and on a remote, never a crash or a line injected into the SUM
    file."""
    path = world.mirror / "aosta" / "dtm" / "2m" / "index.json"
    index = json.loads(path.read_text())
    if bad == "no block":
        del index["block"]
    elif bad.startswith("block"):
        index["block"] = {"block 0": 0, "block text": "x", "block true": True, "block 5": 5}[bad]
    elif bad == "short digest":
        index["tiles"]["176_2518"] = "abc"
    elif bad == "digest with a newline":
        index["tiles"]["176_2518"] = "a" * 64 + "\n" + "b" * 64 + "  ../../outside.tif"
    elif bad == "path as a key":
        index["tiles"]["../x"] = None
    else:
        index["tiles"] = ["176_2518"]
    path.write_text(json.dumps(index))
    (world.tmp / "rclone.conf").write_text(f"[{REMOTE}]\ntype = alias\nremote = {world.mirror.as_posix()}\n")
    for place in (str(world.mirror / "aosta"), f"{REMOTE}:aosta"):
        assert world.run("verify", place) == 1
        out = capsys.readouterr().out
        assert "dtm/2m/index.json: malformed" in out and "Traceback" not in out, out


@pytest.mark.parametrize("args", [("publish", "madeira", "--to", "localword"), ("unpublish", "madeira", "--to", "word"),
                                  ("clean", "--to", "word"), ("stats", "--from", "logs"),
                                  ("publish", "madeira", "--to", "C:/x")])
def test_to_and_from_name_a_remote(world, monkeypatch, capsys, args):
    """F8: --to and --from must name an rclone remote; a bare word (a folder of the PC to rclone) is refused and
    nothing is written anywhere."""
    cwd = world.tmp / "cwd"
    for word in ("localword", "word", "logs"):  # folders of those names: rclone would take them as the server
        (cwd / word).mkdir(parents=True)
    (cwd / "logs" / "access-2026-11-16.log").write_text("{}\n")
    before = tree(cwd)
    monkeypatch.chdir(cwd)
    extra = ("--mirror", str(world.mirror)) if args[0] == "publish" else ()
    assert world.run(*args, *extra) == 1
    assert "refused:" in capsys.readouterr().out
    assert tree(cwd) == before and tree(world.server) == {}


def test_free_space_rule_with_the_real_margin(world, monkeypatch, capsys):
    """The real margin (10 GB) beyond the bytes not staged yet (a partly staged dataset): one byte less is refused,
    exactly enough is accepted."""
    assert REAL_MARGIN == 10 * 10 ** 9
    monkeypatch.setattr(mp, "MARGIN_BYTES", REAL_MARGIN)
    pre = sorted(p for p in world.files["madeira"] if p.endswith(".tif"))[:2]
    for rel in pre:
        target = world.server / "staging" / "madeira" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(world.mirror / "madeira" / rel, target)
    need = sum((world.mirror / "madeira" / rel).stat().st_size for rel in world.files["madeira"] if rel not in pre)
    need += len(mp.cards()["madeira"].encode("utf-8"))
    monkeypatch.setattr(mp.Remote, "free", lambda self: need + REAL_MARGIN - 1)
    assert _publish(world, "madeira") == 1
    assert "GB to keep" in capsys.readouterr().out
    assert not (world.server / "staging" / ".lock").exists()
    monkeypatch.setattr(mp.Remote, "free", lambda self: need + REAL_MARGIN)
    assert _publish(world, "madeira") == 0
    published_ok(world, "madeira")


def test_free_space_unknown_or_no_root(world, monkeypatch, capsys):
    monkeypatch.setattr(mp.Remote, "free", lambda self: None)
    assert _publish(world, "madeira") == 1
    assert "does not tell its free space" in capsys.readouterr().out
    assert tree(world.server) == {}
    (world.tmp / "rclone.conf").write_text(f"[{REMOTE}]\ntype = alias\nremote = {(world.tmp / 'nothere').as_posix()}\n")
    assert _publish(world, "madeira") == 1
    assert "<root> does not exist on the server" in capsys.readouterr().out
    assert not (world.tmp / "nothere").exists()


def test_a_move_never_lands_on_an_existing_target(world, monkeypatch, capsys):
    """Remote.move's guard: a trash folder of the same name stops the swap before any move; public intact, the lock
    kept."""
    assert _publish(world, "madeira") == 0
    monkeypatch.setattr(mp, "_stamp", lambda: "20260101T000000Z")
    trash = world.server / "trash" / "madeira-20260101T000000Z"
    trash.mkdir(parents=True)
    (trash / "x").write_text("x")
    assert _publish(world, "madeira", "--same-values") == 1
    out = capsys.readouterr().out
    assert "trash/madeira-20260101T000000Z exists" in out and "kept" in out
    published_ok(world, "madeira")
    assert tree(trash) == {"x": b"x"} and (world.server / "staging" / ".lock").exists()


def test_verify_read_back(world, monkeypatch, capsys):
    """verify --read-back on a remote: rclone checksum --download, faults found."""
    (world.tmp / "rclone.conf").write_text(f"[{REMOTE}]\ntype = alias\nremote = {world.mirror.as_posix()}\n")
    flipped = world.mirror / "aosta" / "dtm" / "2m" / "17_251" / "176_2518.tif"
    data = bytearray(flipped.read_bytes())
    data[1] ^= 1
    flipped.write_bytes(bytes(data))
    calls = _watch(monkeypatch, world, [])
    assert world.run("verify", f"{REMOTE}:aosta", "--read-back") == 1
    assert "176_2518.tif: sha256 differs from its index" in capsys.readouterr().out
    assert any("checksum" in a and "--download" in a for a in calls)
    assert not any("backend" in a for a in calls)  # no hash check with --read-back


def test_rclone_stderr_never_printed(world, monkeypatch, capsys):
    """Every command against a runner whose stderr names a user, a host, a port and a path (what rclone writes over
    SFTP): none of it in the tool's output or an exception's text, when the calls succeed and when they all fail;
    --log FILE gets it."""
    log = world.tmp / "rclone.log"
    words = ("secretuser", "secret-host", "2222", "/srv/secret-root", "sftp://")

    def noisy(self, argv, data, progress):
        done = REAL_CALL(self, argv, data, progress)
        return subprocess.CompletedProcess(argv, done.returncode, done.stdout, done.stderr + SECRET)

    def failing(self, argv, data, progress):
        if argv[-1] == "version":
            return REAL_CALL(self, argv, data, progress)
        return subprocess.CompletedProcess(argv, 1, b"", SECRET)
    (world.server / "logs").mkdir()
    (world.server / "logs" / "access-2026-11-16.log").write_text("")
    runs = [("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror), "--log", str(log)),
            ("verify", f"{REMOTE}:public/v1/tiles"), ("stats", "--from", f"{REMOTE}:logs"),
            ("clean", "--to", world.to), ("unpublish", "madeira", "--to", world.to)]
    for runner in (noisy, failing):
        monkeypatch.setattr(mp.Rclone, "_call", runner)
        for args in runs:
            try:
                world.run(*args)
            except Exception as e:  # noqa: BLE001 - the text of anything that escapes is checked too
                assert not any(w in str(e) for w in words), e
            out = capsys.readouterr().out
            assert not any(w in out for w in words), out
        assert b"secret-host" in log.read_bytes()


def test_a_lock_written_although_rclone_reports_a_failure(world, monkeypatch, capsys):
    """U35 over SFTP: on a server that cannot compute the hash the remote claims, rclone writes the lock and then
    reports the upload failed. The tool takes the lock as its own (its token is in it), the hash proof refuses, and
    the lock is released: nothing left on the server."""
    real_write = mp.Remote.write

    def write(self, rel, data):
        real_write(self, rel, data)
        if rel == mp.LOCK:
            raise mp.Failed("rclone could not write staging/.lock (exit 1: an error)")
    monkeypatch.setattr(mp.Remote, "write", write)
    monkeypatch.setattr(mp.Remote, "sha256_of", lambda self, rel: None)
    assert _publish(world, "madeira") == 1
    assert "could not hash the lock file" in capsys.readouterr().out
    assert tree(world.server) == {}


# Fix round 2 (the reviews' round 2, 2026-11-16)

def _lock_taken_over_after(world, monkeypatch, trigger):
    """Run B's lock written right after the first rclone call trigger(argv) matches (run A's read-back of its own
    lock, a move, ...); the calls of run A after that point are returned."""
    lock = world.server / "staging" / ".lock"
    state = {"done": False, "after": []}

    def call(self, argv, data, progress):
        if state["done"]:
            state["after"].append(argv)
        done = REAL_CALL(self, argv, data, progress)
        if not state["done"] and trigger(argv):
            lock.write_text(_other_lock())
            state["done"] = True
        return done
    monkeypatch.setattr(mp.Rclone, "_call", call)
    return state["after"]


def _moves(calls):
    return [a for a in calls if "moveto" in a]


@pytest.mark.parametrize("point", ["first move", "second move", "datasets.json"])
def test_another_run_taking_the_lock_stops_this_one(world, monkeypatch, capsys, point):
    """N1: run B's lock written at each point of run A's publish (right after A read its own lock back, the
    reviewer's interleaving; after A's first move of a swap; after A's move into public): A stops at its next check
    point, makes no further move, writes no datasets.json and leaves B's lock alone."""
    lock = world.server / "staging" / ".lock"
    if point == "first move":
        trigger, more = (lambda argv: "cat" in argv and argv[-1].endswith(".lock")), ()
    elif point == "second move":
        assert _publish(world, "madeira") == 0
        trigger, more = (lambda argv: "moveto" in argv and "trash" in argv[-1]), ("--same-values",)
    else:
        trigger, more = (lambda argv: "moveto" in argv and argv[-1].endswith("tiles/madeira")), ()
    listing = (world.server / "public" / "v1" / "datasets.json").read_bytes() if more else None
    capsys.readouterr()
    after = _lock_taken_over_after(world, monkeypatch, trigger)
    assert _publish(world, "madeira", *more) == 1
    out = capsys.readouterr().out
    assert "another run took the lock (or it was broken)" in out and "left that lock alone" in out
    assert lock.read_text() == _other_lock()
    # (the copy into staging/ comes before the first check point and may run: never a move, a delete or the list)
    assert _moves(after) == [] and not any("deletefile" in a for a in after)
    assert not any(a[-1].endswith(".datasets.json.new") for a in after)
    if point == "first move":
        assert not (world.server / "public").exists()
    elif point == "second move":
        assert "the dataset is complete in public/v1/tiles/madeira or in trash/" in out
        assert not (world.server / "public" / "v1" / "tiles" / "madeira").exists()
        assert (world.server / "public" / "v1" / "datasets.json").read_bytes() == listing
    else:
        published_ok(world, "madeira")
        assert not (world.server / "public" / "v1" / "datasets.json").exists()
        assert f"{mp.LIST} is written" in out


def test_another_run_taking_the_lock_before_the_staged_deletes(world, monkeypatch, capsys):
    """N1: a staged file found changed and run B's lock there: run A deletes nothing from staging."""
    lock = world.server / "staging" / ".lock"
    target = world.server / "staging" / "madeira" / "dtm" / "2m" / "14_183" / "143_1833.tif"

    def call(self, argv, data, progress):
        done = REAL_CALL(self, argv, data, progress)
        if "copy" in argv:
            target.write_bytes(b"changed")
            lock.write_text(_other_lock())
        return done
    monkeypatch.setattr(mp.Rclone, "_call", call)
    assert _publish(world, "madeira") == 1
    out = capsys.readouterr().out
    assert "before the staged copy's faults are deleted" in out
    assert target.read_bytes() == b"changed" and lock.read_text() == _other_lock()


@pytest.mark.parametrize("command", ["unpublish", "clean"])
def test_another_run_taking_the_lock_stops_unpublish_and_clean(world, monkeypatch, capsys, command):
    """N1: the same check before unpublish's move and before each removal of clean."""
    assert _publish(world, "madeira") == 0
    old = (mp._now() - datetime.timedelta(days=9)).strftime(mp.STAMP)
    (world.server / "trash" / f"aosta-{old}").mkdir(parents=True)
    (world.server / "trash" / f"aosta-{old}" / "x").write_text("x")
    before = tree(world.server / "public")
    after = _lock_taken_over_after(world, monkeypatch, lambda argv: "cat" in argv and argv[-1].endswith(".lock"))
    args = ("unpublish", "madeira", "--to", world.to) if command == "unpublish" else ("clean", "--to", world.to)
    assert world.run(*args) == 1
    assert "another run took the lock" in capsys.readouterr().out
    assert tree(world.server / "public") == before and (world.server / "trash" / f"aosta-{old}" / "x").exists()
    assert not any("purge" in a or "moveto" in a for a in after)


@pytest.mark.parametrize("command", ["publish", "unpublish", "clean"])
def test_the_final_release_failing_says_the_work_is_done(world, monkeypatch, capsys, command):
    """N2: the work done, only the lock's deletion fails: the message says what is done and names --break-lock; the
    exit code is 1."""
    if command != "publish":
        assert _publish(world, "madeira") == 0
    real_delete = mp.Remote.delete

    def delete(self, rel):
        if rel == mp.LOCK:
            raise mp.Failed("rclone could not delete staging/.lock (exit 1: an error)")
        return real_delete(self, rel)
    monkeypatch.setattr(mp.Remote, "delete", delete)
    capsys.readouterr()
    args = {"publish": ("publish", "madeira", "--to", world.to, "--mirror", str(world.mirror)),
            "unpublish": ("unpublish", "madeira", "--to", world.to), "clean": ("clean", "--to", world.to)}[command]
    assert world.run(*args) == 1
    out = capsys.readouterr().out
    said = {"publish": "madeira is published and public/v1/datasets.json written",
            "unpublish": "madeira is unpublished (in trash/) and public/v1/datasets.json written",
            "clean": "the old trash is removed"}[command]
    assert f"done, but: {said}; only the lock staging/.lock could not be removed" in out and "--break-lock" in out
    if command == "publish":
        published_ok(world, "madeira")


def test_a_failed_lock_write_that_left_a_file(world, monkeypatch, capsys):
    """N3: rclone reports the lock's write failed and a broken file is left: this run says a lock file may be left
    and names --break-lock; the file is not removed (it is not this run's)."""
    lock = world.server / "staging" / ".lock"

    def write(self, rel, data):
        if rel == mp.LOCK:
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_bytes(data[:10])
            raise mp.Failed("rclone could not write staging/.lock (exit 1: an error)")
        raise AssertionError("nothing else is written")
    monkeypatch.setattr(mp.Remote, "write", write)
    assert _publish(world, "madeira") == 1
    out = capsys.readouterr().out
    assert "a lock file may be left on the server: --break-lock" in out and lock.exists()


@pytest.mark.parametrize("where", ["copy", "second move"])
def test_ctrl_c_under_the_lock(world, monkeypatch, capsys, where):
    """N4: Ctrl+C during the copy releases the lock, after the first move keeps it; one line says which."""
    more = ()
    if where == "second move":
        assert _publish(world, "madeira") == 0
        more = ("--same-values",)
    state = {"moved": False}

    def call(self, argv, data, progress):
        if (where == "copy" and "copy" in argv) or (where == "second move" and state["moved"] and "moveto" in argv):
            raise KeyboardInterrupt
        done = REAL_CALL(self, argv, data, progress)
        state["moved"] |= "moveto" in argv
        return done
    monkeypatch.setattr(mp.Rclone, "_call", call)
    capsys.readouterr()
    assert _publish(world, "madeira", *more) == 130
    out = capsys.readouterr().out
    lock = world.server / "staging" / ".lock"
    if where == "copy":
        assert "interrupted (KeyboardInterrupt): the lock was released; nothing public was touched" in out
        assert not lock.exists()
    else:
        assert "interrupted (KeyboardInterrupt): the lock staging/.lock is kept:" in out and lock.exists()


def test_stats_counts_the_clients_versions(world, capsys):
    """N5 and R3: the client's versions are counted by their numbers (two or three, at most three digits each) and the
    kind of a pre-release, .dev or .post, their numbers and any local label dropped; "unknown" stays; no written form
    of an address is printed with four numbers."""
    logs = world.server / "logs"
    logs.mkdir()
    sent = {"0.1.0": "0.1.0", "0.1.0+local": "0.1.0", "0.2.0rc1": "0.2.0rc", "1.0.0.dev3": "1.0.0.dev",
            "1.2.3.post4": "1.2.3.post", "unknown": "unknown",
            # the reviewer's forms: at most three numbers of them are printed
            "203.0.113.dev7": "203.0.113.dev", "203.0.113rc7": "203.0.113rc", "203.0.113.post7": "203.0.113.post",
            "0.1.0+ip203x0x113x7": "0.1.0", "0.1.0+203.0.113.7": "0.1.0",
            # never a version
            "1.2.3.4": "other", "203.0.113.7.dev1": "other", "1.2.3.4rc1": "other", "1000.1.1": "other",
            "203-0-113-7": "other", "0.1.0\n": "other"}
    lines = [{"t": "2026-11-16T10:00:00Z", "s": 200, "b": 1, "rt": 0.1, "ds": "-", "a": "203.0.113.7", "lim": "-",
              "v": v} for v in sent]
    (logs / "access-2026-11-16.log").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert world.run("stats", "--from", f"{REMOTE}:logs") == 0
    versions = capsys.readouterr().out.split("Client versions", 1)[1]
    counts = {}
    for printed in sent.values():
        counts[printed] = counts.get(printed, 0) + 1
    for printed, n in counts.items():
        assert f"  {printed:<20} {n:>9}" in versions, printed
    printed_names = [line.split()[0] for line in versions.strip().splitlines() if line.strip()]
    assert not [n for n in printed_names if re.search(r"\d+\D+\d+\D+\d+\D+\d+", n)]  # never four numbers
    for v in ("203.0.113.dev7", "203.0.113rc7", "203.0.113.post7", "ip203x0x113x7", "113x7", "203.0.113.7"):
        assert v not in versions
    import cache
    assert mp.client_version(cache.VERSION) == cache.VERSION  # the client's own version today, 0.1.0


def test_a_refusal_under_the_lock_leaves_no_staging_folder(world, monkeypatch, capsys):
    """N7: a refusal under the lock on a fresh <root>: the lock and the staging/ folder it made are gone."""
    monkeypatch.setattr(mp.Remote, "free", lambda self: None)
    assert _publish(world, "madeira") == 1
    assert "does not tell its free space" in capsys.readouterr().out
    assert list(world.server.iterdir()) == []


def test_block_is_the_tools_block():
    """Item 9: the block size an index must carry is the cutting tools' (and the client's, 10)."""
    assert mp.BLOCK == sk_tiles.BLOCK == mirror_tiles.BLOCK == 10
    assert src.grid_tile_name(12, 34) == src.grid_tile_name(12, 34, mp.BLOCK)


def test_indexes_written_by_the_tools_pass_verify(tmp_path, monkeypatch):
    """Item 9: the indexes tools/sk_tiles.py (cut, average) and tools/mirror_tiles.py (cut) write pass verify's
    checks (their "block" included)."""
    import test_sources
    import test_mirror_tiles as tmt
    (tmp_path / "sk").mkdir()
    mirror, root, *_ = test_sources._cut(tmp_path / "sk", monkeypatch)
    sk_tiles.average("test", str(mirror / "slovakia"), (2, 5))
    faults, files = mp.read_master(str(mirror / "slovakia"), "<folder>")
    assert faults == [] and {p for p in files if p.endswith("index.json")} == {
        f"test/{r}/index.json" for r in ("1m", "2m", "5m")}
    tmt._spec(monkeypatch, "asc", url="https://example.org/dl/test.zip", member="T.ASC")
    work, out = tmp_path / "work", tmp_path / "mirror"
    tmt._zip(work, "T.ASC", tmt._asc_text(tmt._asc_values()), "test.zip")
    mirror_tiles.extract("asc", str(work))
    mirror_tiles.cut("asc", str(work), str(out))
    faults, files = mp.read_master(str(out / "aosta"), "<folder>")
    assert faults == [] and "dtm/2m/index.json" in files


# Round 3 of the code review (R1, R3, R4; the hash proof's foreign token)

def test_another_runs_lock_at_the_hash_proof(world, monkeypatch, capsys):
    """Another run's lock written between this run's read-back and its hash proof: the proof's hash differs, the
    token is read again, and the run stops as overtaken (not as "could not hash"), leaving that lock alone."""
    lock = world.server / "staging" / ".lock"

    def sha256_of(self, rel):
        lock.write_text(_other_lock())
        return REAL_SHA(self, rel)
    monkeypatch.setattr(mp.Remote, "sha256_of", sha256_of)
    calls = _watch(monkeypatch, world, ["madeira"])
    assert _publish(world, "madeira") == 1
    out = capsys.readouterr().out
    assert "another run took the lock (or it was broken) before the server's hash of the lock file is checked" in out
    assert "could not hash" not in out and lock.read_text() == _other_lock()
    assert not any("copy" in a or "moveto" in a or "deletefile" in a for a in calls)


def test_ctrl_c_right_after_the_lock_write(world, monkeypatch, capsys):
    """R1: Ctrl+C when the lock's write reached the server but take() had not counted it yet: the lock (this run's
    token) is released, and the line says so truthfully."""
    def call(self, argv, data, progress):
        done = REAL_CALL(self, argv, data, progress)
        if "rcat" in argv and argv[-1].endswith(".lock"):
            raise KeyboardInterrupt
        return done
    monkeypatch.setattr(mp.Rclone, "_call", call)
    assert _publish(world, "madeira") == 130
    assert "interrupted (KeyboardInterrupt): the lock was released; nothing public was touched" in \
        capsys.readouterr().out
    assert tree(world.server) == {}


def test_rclone_gone_at_the_staging_rmdir(world, monkeypatch, capsys):
    """R4: rclone cannot be started for the rmdir of an empty staging/ after the lock was removed: the publish is
    done and says so; nothing claims the lock could not be removed."""
    def call(self, argv, data, progress):
        if "rmdir" in argv:
            raise OSError("gone")
        return REAL_CALL(self, argv, data, progress)
    monkeypatch.setattr(mp.Rclone, "_call", call)
    assert _publish(world, "madeira") == 0
    out = capsys.readouterr().out
    assert "published madeira" in out and "could not be removed" not in out
    published_ok(world, "madeira")
    assert not (world.server / "staging" / ".lock").exists()


# F4 of the acceptance run: a refused move says why, in rclone's own words

# rclone 1.76's lines over SFTP, as recorded on the throw-away OpenSSH server (publish/e2e-sftp-log.txt and the
# milestone 1 trial): public/ owned by root, and staging/ and public/ on two mounts
PERMISSION_LINES = (
    b"2026/11/16 16:15:02 NOTICE: sftptrial: No host key validation is being performed.\n"
    b"2026/11/16 16:15:02 ERROR : sftp://pub@127.0.0.1:22923//data/f/public/v1/tiles/madeira: Server side directory "
    b"move failed: DirMove mkParentDir dst failed: mkdir \"/data/f/public/v1\" failed: permission denied\n"
    b"2026/11/16 16:15:02 ERROR : Attempt 1/1 failed with 1 errors and: DirMove mkParentDir dst failed: mkdir "
    b"\"/data/f/public/v1\" failed: permission denied\n"
    b"2026/11/16 16:15:02 NOTICE: Failed to moveto: DirMove mkParentDir dst failed: mkdir \"/data/f/public/v1\" "
    b"failed: permission denied\n")
CROSS_MOUNT_LINES = (
    b"2026/11/16 00:12:24 ERROR : sftp://pub@127.0.0.1:22922//data/b/public/v1/tiles/madeira: Server side directory "
    b"move failed: DirMove Rename(\"/data/b/staging/madeira\",\"/data/b/public/v1/tiles/madeira\") failed: sftp: "
    b"\"Failure\" (SSH_FX_FAILURE)\n"
    b"2026/11/16 00:12:24 NOTICE: Failed to moveto: DirMove Rename(\"/data/b/staging/madeira\","
    b"\"/data/b/public/v1/tiles/madeira\") failed: sftp: \"Failure\" (SSH_FX_FAILURE)\n")


@pytest.mark.parametrize("cause, lines, reason", [
    ("permission", PERMISSION_LINES, "failed: permission denied"),
    ("two mounts", CROSS_MOUNT_LINES, "failed: sftp: \"Failure\" (SSH_FX_FAILURE)")])
def test_a_refused_move_says_rclones_reason(world, monkeypatch, capsys, cause, lines, reason):
    """F4: the move into public refused by the server: the stop text carries rclone's own last error lines (masked:
    no address, account, port or server path) and names both likely causes; the lock is kept, the copy stays
    complete in staging. Simulated: the local backend renames whatever the rights, so the moveto answers with the
    lines rclone wrote over SFTP for each cause (real in the SFTP end-to-end run)."""
    def call(self, argv, data, progress):
        if "moveto" in argv and argv[-2].endswith("staging/madeira"):
            return subprocess.CompletedProcess(argv, 1, b"", lines)
        return REAL_CALL(self, argv, data, progress)
    monkeypatch.setattr(mp.Rclone, "_call", call)
    assert _publish(world, "madeira") == 1
    out = capsys.readouterr().out
    assert "stopped: the server refused the move of staging/madeira to public/v1/tiles/madeira" in out
    assert reason in out
    assert ("Likely causes: the publishing account may not write public/ or a folder below it (their owner; "
            "rclone's line above names the folder), or staging/ and public/ (or a folder below either) are on "
            "different disks") in out
    for secret in ("127.0.0.1", "pub@", "sftp://", "2292", "/data/", "host key"):
        assert secret not in out, secret
    assert (world.server / "staging" / ".lock").exists() and "the lock staging/.lock is kept" in out
    assert len(tree(world.server / "staging" / "madeira")) == len(world.files["madeira"]) + 1


def test_rclones_lines_are_cut_and_masked():
    """Remote.says: at most SAYS_LINES lines of SAYS_CHARS characters; URLs, user@host, addresses, dialled hosts,
    the remote's name, places of the PC and absolute server paths outside <root> never pass."""
    class Answers:
        def run(self, *args, **kw):
            return subprocess.CompletedProcess(args, 0, json.dumps(
                {"Name": "door", "Root": "/srv/mirror", "String": "sftp://door@192.0.2.5:2222//srv/mirror"}).encode(),
                b"")
    remote = mp.Remote(Answers(), "door:/srv/mirror")
    remote.local.append(r"C:\data\master")
    lines = (b"2026/11/16 10:00:00 ERROR : sftp://door@192.0.2.5:2222//srv/mirror/x: mkdir \"/srv/mirror/public\": "
             b"permission denied\n"
             b"2026/11/16 10:00:01 NOTICE: Failed to copy: couldn't connect SSH: dial tcp 192.0.2.5:2222: refused; "
             b"lookup nas.example: no such host; key file /home/someone/.ssh/id: denied; door:x; [2001:db8::1]:22\n"
             rb"2026/11/16 10:00:02 ERROR : open C:\data\master\madeira\a.tif: denied " + b"y" * 400 + b"\n")
    said = remote.says(subprocess.CompletedProcess([], 1, b"", lines))
    parts = said.split(" | ")
    assert len(parts) == mp.SAYS_LINES and all(len(p) <= mp.SAYS_CHARS for p in parts)
    for secret in ("192.0.2.5", "2222", "nas.example", "/home/someone", "door", "2001:db8", r"C:\data", "/srv/"):
        assert secret not in said, secret
    assert "dial tcp <host>" in said and "lookup <host>" in said and "<mirror>" in said
    first = remote.says(subprocess.CompletedProcess([], 1, b"", lines.split(b"\n")[0]))
    assert first == "<remote>/x: mkdir \"<root>/public\": permission denied"


# After batch 6's tools/mirror_tiles.py (main 75615fc): its files in the master

def test_the_cutters_own_files_never_leave_the_master(world, capsys):
    """A final product folder of tools/mirror_tiles.py holds inputs.jsonl and verify.json, the dataset its card
    README.md, the mirror's root .locks and .staging (a cut in progress: tiles without an index yet). verify of the
    master (the dataset and the whole mirror) passes; publish copies none of them (the staged verify passes, the
    server holds exactly the listed files and the tool's card)."""
    product = world.mirror / "madeira" / "dtm" / "2m"
    (product / "inputs.jsonl").write_text('{"id": "MDT_2m.zip!MDT_2m.tif", "stamp": "x"}\n')
    (product / "verify.json").write_text('{"ok": true}\n')
    (world.mirror / "madeira" / "README.md").write_text("the cutter's card\n")
    (world.mirror / ".locks").mkdir()
    (world.mirror / ".locks" / "madeira.dtm.2m.lock").write_text("pid 1")
    staged = world.mirror / ".staging" / "porto-santo" / "dtm" / "5m" / "0_0"
    staged.mkdir(parents=True)
    (staged / "1_1.tif").write_bytes(b"a tile of a cut in progress")
    assert world.run("verify", str(world.mirror / "madeira")) == 0
    assert world.run("verify", str(world.mirror)) == 0
    assert "0 faults" in capsys.readouterr().out
    assert _publish(world, "madeira") == 0
    published_ok(world, "madeira")  # exactly the listed files and the tool's card
    names = {p.rsplit("/", 1)[-1] for p in tree(world.server)}
    assert not names & {"inputs.jsonl", "verify.json", "madeira.dtm.2m.lock", "1_1.tif"}
    assert not any(".staging" in p or ".locks" in p for p in tree(world.server))
    assert tree(world.server / "public" / "v1" / "tiles" / "madeira")["README.md"].decode() == mirror_tiles.MADEIRA_CARD


def test_a_cut_dataset_without_a_row_is_refused(world, monkeypatch, capsys):
    """A dataset cut by tools/mirror_tiles.py without a PUBLISHABLE row (a stand-in: every cut dataset has a row
    today) is refused with the tool's text for a dataset without a row, before any request."""
    stand_in = mirror_tiles.replace(mirror_tiles.dataset("selvagens"), name="islet-without-a-row")
    monkeypatch.setitem(mirror_tiles.DATASETS, "islet-without-a-row", stand_in)
    assert "islet-without-a-row" in mp.cards() and "islet-without-a-row" not in mp.PUBLISHABLE
    make_dataset(world.mirror, "islet-without-a-row", {"dtm/5m": [(199, 1661)]})
    assert _publish(world, "islet-without-a-row") == 1
    assert "refused: islet-without-a-row: no row in PUBLISHABLE" in capsys.readouterr().out
    assert tree(world.server) == {}


def test_a_first_publish_says_what_its_log_holds(world, capsys):
    """A first publish with --log says that rclone's log gets "directory not found" lines (the tool's checks of
    folders it has not made yet), and the log does hold such lines while the publish succeeds; a publish without
    --log, or of a dataset already published, says nothing of it."""
    log = world.tmp / "rclone.log"
    assert _publish(world, "madeira", "--log", str(log)) == 0
    out = capsys.readouterr().out
    assert "first publish of madeira: rclone's log (--log) gets \"directory not found\" lines" in out
    assert "directory not found" in log.read_text(encoding="utf-8", errors="replace")
    assert _publish(world, "madeira", "--same-values", "--log", str(log)) == 0
    assert "first publish" not in capsys.readouterr().out
    assert _publish(world, "aosta") == 0
    assert "first publish" not in capsys.readouterr().out


# The islets' served cards, word for word as the user saw them (Selvagens) or approved them after U56 (Porto
# Santo, Desertas): a change of the generator or a record shows here first
ISLET_CARDS = {
    'porto-santo': (
        '# Porto Santo: DTM 5 m (DROTe, 2018-2019) as 2 km tiles\n'
        '\n'
        'Made from the data of **Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da '
        'Madeira** '
        '(https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/metadata/abba9a83-cb1c-4d2c-ad1d-ccb59'
        '2247754).\n'
        'Licence: No conditions apply (SNIG record abba9a83). Attribution: DTM 5 m: Direção Regional do '
        'Ordenamento do Território (DROTe), Região Autónoma da Madeira, 2018-2019.\n'
        '\n'
        '## `dtm/5m`: MDT 5 m, Porto Santo (DROTe, photogrammetry 2018-2019)\n'
        '\n'
        'Source: PortoSanto_5m.tif of https://irig-storage.madeira.gov.pt/irig-catalogo/mdt_5m.zip (Porto '
        'Santo 1995 / UTM zone 28N, EPSG:3061); Porto Santo and its islets; the sea written as 0 there.\n'
        '\n'
        'Changes made: cut into 2 km x 2 km Cloud Optimized GeoTIFFs on its own 5 m pixel grid in EPSG:3061 '
        "(tile (i, j) starts at x = 2000 i + 2.5, y = 2000 j + 2.5); the files' own no-data value and the "
        "sea's value 0 made no data; stored with LERC compression with a maximum error of 5 mm; the values, "
        'float64 in the file, stored as float32 (within those 5 mm). Heights as published (metres); values are '
        'not otherwise changed.\n'
        '\n'
        'Layout: `<product>/<res>m/<i//10>_<j//10>/<i>_<j>.tif`; `<product>/<res>m/index.json` lists every tile '
        'of the extent with its sha256 (null: no data). Made for Find-a-Line (a highline finder); not endorsed '
        'by DROTe.\n'
    ),
    'desertas': (
        '# Desertas: DTM 5 m (DROTe, 2018-2019) as 2 km tiles\n'
        '\n'
        'Made from the data of **Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da '
        'Madeira** '
        '(https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/metadata/abba9a83-cb1c-4d2c-ad1d-ccb59'
        '2247754).\n'
        'Licence: No conditions apply (SNIG record abba9a83). Attribution: DTM 5 m: Direção Regional do '
        'Ordenamento do Território (DROTe), Região Autónoma da Madeira, 2018-2019.\n'
        '\n'
        '## `dtm/5m`: MDT 5 m, Desertas (DROTe, photogrammetry 2018-2019)\n'
        '\n'
        'Source: Desertas_5m.tif of https://irig-storage.madeira.gov.pt/irig-catalogo/mdt_5m.zip (PTRA08 / UTM '
        'zone 28N, EPSG:5016; the file is labelled EPSG:3061); Deserta Grande, Bugio and Ilhéu Chão.\n'
        '\n'
        'Changes made: cut into 2 km x 2 km Cloud Optimized GeoTIFFs on its own 5 m pixel grid in EPSG:5016 (tile '
        "(i, j) starts at x = 2000 i + 2.5, y = 2000 j + 2.5); the files' own no-data value, the values "
        '-32768, -999 and every value below -1 m made no data; stored with LERC compression with a maximum error of '
        "5 mm; the file's reference-system label replaced: it is labelled EPSG:3061, its coordinates are in "
        'EPSG:5016 (PTRA08 / UTM zone 28N); nothing reprojected. Heights as published (metres); values are '
        'not otherwise changed.\n'
        '\n'
        'Layout: `<product>/<res>m/<i//10>_<j//10>/<i>_<j>.tif`; `<product>/<res>m/index.json` lists every tile '
        'of the extent with its sha256 (null: no data). Made for Find-a-Line (a highline finder); not endorsed '
        'by DROTe.\n'
    ),
    'selvagens': (
        '# Selvagens: DTM 5 m (DROTe, 2018-2019) as 2 km tiles\n'
        '\n'
        'Made from the data of **Direção Regional do Ordenamento do Território (DROTe), Região Autónoma da '
        'Madeira** '
        '(https://snig.dgterritorio.gov.pt/rndg/srv/por/catalog.search#/metadata/abba9a83-cb1c-4d2c-ad1d-ccb59'
        '2247754).\n'
        'Licence: No conditions apply (SNIG record abba9a83). Attribution: DTM 5 m: Direção Regional do '
        'Ordenamento do Território (DROTe), Região Autónoma da Madeira, 2018-2019.\n'
        '\n'
        '## `dtm/5m`: MDT 5 m, Selvagens (DROTe, photogrammetry 2018-2019)\n'
        '\n'
        'Source: Selvagens_5m.tif of https://irig-storage.madeira.gov.pt/irig-catalogo/mdt_5m.zip (PTRA08 / UTM zone '
        '28N, EPSG:5016); Selvagem Grande, Selvagem Pequena and Ilhéu de Fora.\n'
        '\n'
        'Changes made: cut into 2 km x 2 km Cloud Optimized GeoTIFFs on its own 5 m pixel grid in EPSG:5016 (tile '
        "(i, j) starts at x = 2000 i + 2.5, y = 2000 j + 2.5); the files' own no-data value, the values -32768, "
        '-999 and every value below -1 m made no data; stored with LERC compression with a maximum error of '
        '5 mm. Heights as published (metres); values are not otherwise changed.\n'
        '\n'
        'Layout: `<product>/<res>m/<i//10>_<j//10>/<i>_<j>.tif`; `<product>/<res>m/index.json` lists every tile '
        'of the extent with its sha256 (null: no data). Made for Find-a-Line (a highline finder); not endorsed '
        'by DROTe.\n'
    ),
}


def test_the_islets_cards_word_for_word():
    """The three generated cards publish serves (card_text): the Selvagens' as the user saw it, Porto Santo's and
    the Desertas' with the change U56 asked named under "Changes made"; Madeira's and Valle d'Aosta's fixed cards
    unchanged."""
    for name, text in ISLET_CARDS.items():
        assert mp.cards()[name] == text, name
    assert mp.cards()["madeira"] == mirror_tiles.MADEIRA_CARD and mp.cards()["aosta"] == mirror_tiles.AOSTA_CARD


def test_a_5m_islet_published_end_to_end(world, capsys):
    """An islet of 5 m (Porto Santo's row) published in the local backend: its tiles, its index and its generated
    card (the float64 change named) served, datasets.json listing it with the catalogue's credit."""
    files = make_dataset(world.mirror, "porto-santo", {"dtm/5m": [(186, 1828), (187, 1829), (-1, 1830)]})
    world.files["porto-santo"] = files
    assert world.run("verify", str(world.mirror / "porto-santo")) == 0
    assert _publish(world, "porto-santo") == 0
    published_ok(world, "porto-santo")
    card = tree(world.server / "public" / "v1" / "tiles" / "porto-santo")["README.md"].decode("utf-8")
    assert card == ISLET_CARDS["porto-santo"] and "float64 in the file, stored as float32" in card
    listing = json.loads((world.server / "public" / "v1" / "datasets.json").read_text(encoding="utf-8"))
    [entry] = [d for d in listing["datasets"] if d["id"] == "porto-santo"]
    assert entry["attribution"] == SOURCES["porto_santo"].attribution and entry["licence"] == "none"
    assert [p["path"] for p in entry["products"]] == ["porto-santo/dtm/5m"] and entry["products"][0]["tiles"] == 3
    assert "published porto-santo" in capsys.readouterr().out
