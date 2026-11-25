"""A data, cache or runs folder whose path holds "[" and "]" (user-inputs E3): every file listing that starts at
such a folder takes its name literally (glob.escape of the folder part only), so it finds what it should instead
of nothing. A test per module that lists (search, country, osmextract, the indexes and layers of sources/; the
regression harness' helpers are tested in tests/test_regression_harness.py), and a guard: every glob.glob and
glob.iglob call of the tracked non-test code escapes its folder part, or is named in ALLOWED with its reason."""

import ast
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio as rio
from rasterio.transform import from_origin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import country  # noqa: E402
import osmextract  # noqa: E402
import search  # noqa: E402
from grid import Grid  # noqa: E402
from sources.indexes import cartoteca, metalink, packages, sheetsets, versions  # noqa: E402
from sources.layers.geojson import GeoJsonTiles  # noqa: E402
from sources.layers.zipmembers import ZipMemberTiles  # noqa: E402
from sources.layers.zipsheets import ZipSheetTiles  # noqa: E402
from test_search_findings import _migrated, _plan, _unfinished  # noqa: E402

UTM = "EPSG:25832"
# A grid of 1 km over the UTM tile (500, 5600) in km
UTM_GRID = Grid(left=500_000.0, top=5_601_000.0, res=10.0, height=100, width=100, crs=UTM)


@pytest.fixture
def root(tmp_path):
    """A folder whose name holds "[" and "]" (as C:\\data\\[maps]\\findaline)."""
    folder = tmp_path / "x[1]"
    folder.mkdir()
    return str(folder)


def _touch(path, data=b""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


# --- search.py --------------------------------------------------------------------------------------------------

def test_search_resumes_a_run_in_a_runs_folder_with_brackets(root):
    """_open_run: the unfinished run of the same search is found (its progress.json) and its finished tiles
    counted."""
    runs = os.path.join(root, "runs")
    plan = _plan(_migrated(), None, runs)
    folder = _unfinished(runs, search._search_hash(plan))
    _touch(os.path.join(folder, "tiles", search.TILE_FILE.format("0_0")))
    said = []
    plan.emit = lambda kind, text: said.append(text)
    assert search._open_run(plan)["path"] == folder
    assert said == ["Resuming run unfinished: 1 of 4 tiles done"]


def test_search_removes_the_grids_of_a_work_folder_with_brackets(root):
    """_remove_grids: the grids of step 1 (*.npy of the work folder) are removed, the subfolders stay."""
    work = os.path.join(root, "work")
    grid = _touch(os.path.join(work, "elevation.npy"))
    kept = _touch(os.path.join(work, "tiles", "a.npy"))
    search._remove_grids(work)
    assert not os.path.exists(grid) and os.path.exists(kept)


# --- country.py -------------------------------------------------------------------------------------------------

def test_country_profile_in_a_data_folder_with_brackets(root, monkeypatch, capsys):
    """country.profile: the tiles of a band and the run's timelines are found (the tile's meta and the timeline's
    sums stubbed: only the listings are tested)."""
    folder = country.folder_of(root, "testland")
    _touch(os.path.join(folder, "tiles", "S", "1_2.npz"))
    timeline = _touch(os.path.join(folder, "logs", "samples-1.csv"))
    monkeypatch.setattr(country, "read_state", lambda f: {"config": None})
    monkeypatch.setattr(country.Country, "from_config", staticmethod(
        lambda config: SimpleNamespace(bands=[SimpleNamespace(name="S")])))
    monkeypatch.setattr(country, "_tile_meta", lambda path: {"seconds": {"prepare": 1.0, "count": 2.0}})
    read = []
    monkeypatch.setattr(country, "_profile_timeline", read.append)
    assert country.profile("testland", root) == 0
    assert "Band S: 1 tiles" in capsys.readouterr().out
    assert read == [timeline]


# --- osmextract.py ----------------------------------------------------------------------------------------------

def test_osm_extracts_in_a_cache_with_brackets(root):
    cache_dir = os.path.join(root, "cache")
    pbf = _touch(osmextract._paths(cache_dir, "poland", "malopolskie")[0])
    assert osmextract.extracts(cache_dir) == [("malopolskie", pbf)]


# --- sources/indexes --------------------------------------------------------------------------------------------

def test_cartoteca_cached_surveys_in_a_cache_with_brackets(root):
    """CartotecaVersions.cached (the surveys over a grid, with their files' extents) and cached_sheets."""
    cache_dir = os.path.join(root, "cache")
    layer = cartoteca.CartotecaVersions("test_it/tos-dtm", "dtm", "test_it/tos-urls")
    sheet = cartoteca.LidarSheet(2010, "12", 1.0, "abc", "", "", (0.0, 0.0, 0.0, 0.0))
    path = layer.path(cache_dir, sheet)
    os.makedirs(os.path.dirname(path))
    with rio.open(path, "w", driver="GTiff", width=10, height=10, count=1, dtype="float32",
                  crs=cartoteca.CARTOTECA_CRS, transform=from_origin(1_600_000, 4_801_000, 100, 100)) as out:
        out.write(np.zeros((1, 10, 10), dtype=np.float32))
    assert [s.godlo for s in layer.cached_sheets(cache_dir)] == ["abc"]
    grid = Grid(left=1_600_000.0, top=4_801_000.0, res=10.0, height=100, width=100, crs=cartoteca.CARTOTECA_CRS)
    assert [(s.godlo, s.extent) for s in layer.cached(grid, cache_dir)] == [
        ("abc", (1_600_000.0, 4_800_000.0, 1_601_000.0, 4_801_000.0))]


def test_sha_per_tile_cached_in_a_cache_with_brackets(root):
    """ShaPerTile.cached (metalink.py: _cached_tiles), a layer folder of two parts as every real one (bavaria/dgm1):
    glob gives an escaped folder's paths back with the system's separators, so each is compared with path() through
    os.path.normcase."""
    cache_dir = os.path.join(root, "cache")
    layer = metalink.ShaPerTile("test_sha/dgm1", UTM)
    tile = metalink.ShaTile(500, 5600, 2020, "abcdef12")
    _touch(layer.path(cache_dir, tile))
    assert layer.cached(UTM_GRID, cache_dir) == [tile]


def test_package_versions_cached_in_a_cache_with_brackets(root):
    """PackageVersions.cached (a layer folder of two parts, compared as ShaPerTile's), and forget_answers (the
    layer's 0.25 degree answers deleted)."""
    cache_dir = os.path.join(root, "cache")
    layer = packages.PackageVersions("test_pk/dgm1")
    tile = packages.PackageTile(UTM, 500, 5600, 2020, "abcdef12", size=10)
    path = _touch(layer.path(cache_dir, tile))
    assert [layer.path(cache_dir, t) for t in layer.cached(UTM_GRID, cache_dir)] == [path]
    answer = _touch(os.path.join(cache_dir, "test_pk", "sheet-index", "dgm1", "50.00_7.00.json"), b"[]")
    packages.forget_answers(cache_dir, "test_pk", "dgm1")
    assert not os.path.exists(answer)


@pytest.mark.skipif(sys.platform != "win32", reason="a folder typed in another case than on disk: Windows only")
def test_cached_tiles_of_a_folder_typed_in_another_case(tmp_path):
    """The data folder typed in another case than the disk spells it (maps[1] for Maps[1]): glob gives the
    bracketed part back as the disk spells it, so ShaPerTile and PackageVersions compare through os.path.normcase
    (layer folders of one part here: only the case differs)."""
    (tmp_path / "Maps[1]").mkdir()
    cache_dir = os.path.join(str(tmp_path), "maps[1]", "cache")
    sha = metalink.ShaPerTile("test_sha", UTM)
    tile = metalink.ShaTile(500, 5600, 2020, "abcdef12")
    _touch(sha.path(cache_dir, tile))
    assert sha.cached(UTM_GRID, cache_dir) == [tile]
    package = packages.PackageVersions("test_pk")
    _touch(package.path(cache_dir, packages.PackageTile(UTM, 500, 5600, 2020, "abcdef12", size=10)))
    assert len(package.cached(UTM_GRID, cache_dir)) == 1


def test_sheet_sets_cached_paths_in_a_cache_with_brackets(root):
    """SheetSets._cached_paths (what cached() and prune read; cached() needs the owners' answers too)."""
    cache_dir = os.path.join(root, "cache")
    layer = sheetsets.SheetSets("test_ss/lp", "EPSG:6676", 0.5, {})
    path = _touch(os.path.join(cache_dir, "test_ss", "lp", "s", "OF", "04", "2019_08OF0485_1a2b3c4d.tif"))
    assert layer._cached_paths(cache_dir) == [path]


def test_newest_per_sheet_cached_files_in_a_cache_with_brackets(root):
    """NewestPerSheet._cached_files (what cached() reads), with and without resolutions of their own."""
    cache_dir = os.path.join(root, "cache")
    plain = versions.NewestPerSheet("test_v/nmt", UTM, 1.0)
    path = _touch(os.path.join(cache_dir, "test_v", "nmt", "2020_a.tif"))
    assert plain._cached_files(UTM_GRID, cache_dir) == ([path], 1.0)
    sized = versions.NewestPerSheet("test_v/sized", UTM, 0.5, sizes={0.5: 1e6, 2.0: 1e5})
    path = _touch(os.path.join(cache_dir, "test_v", "sized", "10m", "2020_a.tif"))
    path = _touch(os.path.join(cache_dir, "test_v", "sized", "2m", "2020_a.tif"))
    assert sized._cached_files(UTM_GRID, cache_dir) == ([path], 2.0)


def test_composed_blocks_cached_paths_in_a_cache_with_brackets(root):
    """ComposedBlocks._cached_paths (what cached() and prune read)."""
    cache_dir = os.path.join(root, "cache")
    layer = versions.ComposedBlocks("test_cb/dem", 1000, 1.0)
    block = versions.Block("EPSG:26913", 10, 20, 1000, 2020, "k")
    path = _touch(layer.path(cache_dir, block))
    assert [os.path.normpath(p) for p in layer._cached_paths(cache_dir)] == [os.path.normpath(path)]


# --- sources/layers ---------------------------------------------------------------------------------------------

def _answer(cache_dir, top, prefix):
    return _touch(os.path.join(cache_dir, top, "sheet-index", prefix, "50.00_7.00.json"), b"[]")


def test_geojson_stale_link_forgets_the_answers_in_a_cache_with_brackets(root, monkeypatch):
    """GeoJsonTiles._stale: an outdated link forgets the layer's 0.25 degree answers (the documents' reading
    stubbed: no request)."""
    cache_dir = os.path.join(root, "cache")
    layer = GeoJsonTiles("Test", ["https://example.invalid/a.geojson"], r"(?P<east>\d+)_(?P<north>\d+)",
                         "test_gj/dgm1", UTM, "dgm1")
    layer.index.cache_dir = cache_dir
    monkeypatch.setattr(layer.listing, "forget", lambda cache_dir: None)
    monkeypatch.setattr(layer.listing, "table", lambda force=False: [])
    answer = _answer(cache_dir, "test_gj", "dgm1")
    assert layer._stale(SimpleNamespace(place="500_5600")) is None
    assert not os.path.exists(answer)


def test_zip_member_renew_forgets_the_answers_in_a_cache_with_brackets(root, monkeypatch):
    """ZipMemberTiles._renew: a member the directories list no more forgets the layer's 0.25 degree answers (the
    directories' reading stubbed: no request)."""
    cache_dir = os.path.join(root, "cache")
    layer = ZipMemberTiles("Test", ["https://example.invalid/a.zip"], r"(?P<east>\d+)_(?P<north>\d+)",
                           "test_zm/dom1", UTM, "dom1")
    layer.index.cache_dir = cache_dir
    monkeypatch.setattr(layer.listing, "table", lambda force=False: [])
    answer = _answer(cache_dir, "test_zm", "dom1")
    assert layer._renew(SimpleNamespace(godlo="500_5600", year=0, key="k", url="u", offset=0)) is None
    assert not os.path.exists(answer)


def test_zip_sheets_in_a_cache_with_brackets(root):
    """ZipSheetTiles._cached (the newest file of each sheet over the grid) and _renewed (a renewed sheet's other
    versions deleted)."""
    cache_dir = os.path.join(root, "cache")
    layer = ZipSheetTiles("Test", ["https://example.invalid/a.zip"], r"Sheet(\d+)\.txt",
                          {1: (500_000, 5_600_000, 501_000, 5_601_000)}, UTM, "test_zs/dtm10", "k", 10.0)
    older = _touch(os.path.join(cache_dir, "test_zs", "dtm10", "001_aaaa.tif"))
    newer = _touch(os.path.join(cache_dir, "test_zs", "dtm10", "001_bbbb.tif"))
    os.utime(older, (1_000_000_000, 1_000_000_000))
    assert layer._cached(UTM_GRID, cache_dir) == [newer]
    layer.index.cache_dir = None  # no row recorded: only the listing of the other versions is tested
    layer._renewed(newer, SimpleNamespace(sheet=1), None)
    assert not os.path.exists(older) and os.path.exists(newer)


def test_zip_sheets_renewed_keeps_the_file_it_wrote(root):
    """ZipSheetTiles._renewed with a cache path holding a doubled separator: glob gives the other versions back
    rebuilt (one separator), so the file just written is told apart through normpath and normcase, never deleted."""
    cache_dir = root + os.sep + os.sep + "cache"
    layer = ZipSheetTiles("Test", ["https://example.invalid/a.zip"], r"Sheet(\d+)\.txt",
                          {1: (500_000, 5_600_000, 501_000, 5_601_000)}, UTM, "test_zs/dtm10", "k", 10.0)
    older = _touch(os.path.join(cache_dir, "test_zs", "dtm10", "001_aaaa.tif"))
    newer = _touch(os.path.join(cache_dir, "test_zs", "dtm10", "001_bbbb.tif"))
    layer.index.cache_dir = None  # no row recorded
    layer._renewed(newer, SimpleNamespace(sheet=1), None)
    assert not os.path.exists(older) and os.path.exists(newer)


# --- tools ------------------------------------------------------------------------------------------------------

def test_end_zone_study_call_folders_in_a_folder_with_brackets(root, monkeypatch):
    """tools/end_zone_study.py call_folders (its pattern built from the folder: the guard does not see it): the
    capture's call folders, in their order. tools/ on sys.path and the module in sys.modules for this test only."""
    monkeypatch.syspath_prepend(os.path.join(REPO, "tools"))
    monkeypatch.setitem(sys.modules, "end_zone_study", None)  # what was there (or nothing) comes back afterwards
    del sys.modules["end_zone_study"]
    import end_zone_study
    calls = [os.path.join(root, "capture", f"call-{n}") for n in (10, 2)]
    for call in calls:
        os.makedirs(call)
    assert end_zone_study.call_folders(root) == calls[::-1]


# --- the guard --------------------------------------------------------------------------------------------------

# The listings left as they are: (file, the pattern as ast.unparse gives it) -> (how many such calls, why)
ALLOWED = {
    ("tools/clean_temp.py", "os.path.join(os.path.expanduser('~'), '.claude*')"):
        (1, "Claude Code's config folders: the pattern .claude* is meant"),
    ("tools/end_zone_study.py", "pattern"):
        (1, "built from glob.escape(folder) on the line before it"),
    ("tests/data/make_fixture.py", "os.path.join('cache', 'poland', kind, SHEET)"):
        (1, "a relative path of the fixture's maker"),
    ("docs/3d-view-research/scripts/r3/dem_sizes.py", "os.path.join(folder, '**', '*.tif')"):
        (1, "a research script, kept as it ran (left by the brief of the task)"),
}

HOW = ("glob.glob reads '[' in a folder's name as a pattern: in a data folder such as C:\\data\\[maps] it finds "
       "nothing. Wrap the folder part in glob.escape(...) (os.path.join(glob.escape(cache_dir), '*', 'x.tif')), "
       "give the folder as root_dir=, or name the call in ALLOWED of tests/test_glob_folders.py with its reason")
IMPORTS = ("import glob only as `import glob` and call glob.glob(...): tests/test_glob_folders.py checks the "
           "listings by that spelling")


def _is_glob(node, name):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "glob")


def unescaped_listings(text):
    """(line, pattern) of each glob.glob or glob.iglob call whose pattern (the first argument, or pathname=) holds
    no glob.escape; a call with root_dir= is accepted (the folder is taken literally there)."""
    found = []
    for node in ast.walk(ast.parse(text)):
        if not (_is_glob(node, "glob") or _is_glob(node, "iglob")):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        if "root_dir" in keywords:
            continue
        pattern = node.args[0] if node.args else keywords.get("pathname")
        if pattern is None:
            found.append((node.lineno, "<no pattern>"))
        elif not any(_is_glob(inner, "escape") for inner in ast.walk(pattern)):
            found.append((node.lineno, ast.unparse(pattern)))
    return sorted(found)


def other_imports(text):
    """(line, the statement) of each import of glob spelt otherwise than `import glob`, which the guard cannot
    follow: `from glob import ...`, `import glob as ...`."""
    found = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.ImportFrom) and node.module == "glob" or isinstance(node, ast.Import) and any(
                a.name == "glob" and a.asname not in (None, "glob") for a in node.names):
            found.append((node.lineno, ast.unparse(node)))
    return sorted(found)


def test_the_guard_finds_a_listing_without_the_escape():
    text = ("import glob, os\n"
            "a = glob.glob(os.path.join(cache_dir, '*', 'x.tif'))\n"
            "b = glob.glob(os.path.join(glob.escape(cache_dir), '*', 'x.tif'))\n"
            "c = list(glob.iglob(runs + '/*'))\n"
            "d = glob.escape(x)\n"
            "e = glob.glob(pathname=os.path.join(work, '*.npy'))\n"
            "f = glob.glob(pathname=os.path.join(glob.escape(work), '*.npy'))\n"
            "g = glob.glob('*/run.json', root_dir=runs)\n")
    assert unescaped_listings(text) == [(2, "os.path.join(cache_dir, '*', 'x.tif')"), (4, "runs + '/*'"),
                                        (6, "os.path.join(work, '*.npy')")]
    assert other_imports(text) == []
    text = "from glob import glob\nimport glob as g\nimport os, glob\nfrom glob import escape as e\n"
    assert other_imports(text) == [(1, "from glob import glob"), (2, "import glob as g"),
                                   (4, "from glob import escape as e")]


def _tracked_python():
    """The tracked Python files but the tests' own (tests/test_*.py); without git (not a checkout) the guard skips
    and so checks nothing."""
    try:
        result = subprocess.run(["git", "ls-files", "*.py"], cwd=REPO, capture_output=True, encoding="utf-8",
                                check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout: the guard checks nothing here")
    names = [n for n in result.stdout.split("\n") if n]
    return [n for n in names if not (n.startswith("tests/") and os.path.basename(n).startswith("test_"))]


def test_every_listing_escapes_its_folder():
    """Every glob.glob and glob.iglob call of the tracked non-test code escapes its folder part (or is allowed, as
    many times as ALLOWED says), and glob is imported only as `import glob`."""
    seen, bad, imports = {}, [], []
    for name in _tracked_python():
        path = os.path.join(REPO, name)
        if not os.path.exists(path):  # deleted in the working tree
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if "glob" not in text:
            continue
        imports += [f"{name}:{line}: {statement}" for line, statement in other_imports(text)]
        for line, argument in unescaped_listings(text):
            key = (name, argument)
            seen[key] = seen.get(key, 0) + 1
            if key not in ALLOWED or seen[key] > ALLOWED[key][0]:
                bad.append(f"{name}:{line}: glob of {argument}")
    assert not imports, IMPORTS + ":\n" + "\n".join(imports)
    assert not bad, HOW + ":\n" + "\n".join(bad)
    stale = sorted(key for key, (count, _) in ALLOWED.items() if seen.get(key, 0) != count)
    assert not stale, f"ALLOWED names calls that are no more (or fewer): {stale}"
