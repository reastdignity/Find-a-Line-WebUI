"""What the area download's window shows and does, without the window (tools/area_rows.py), offline: a row for every area
of the coverage map, the settings, where a row's tiles go, the links to a share, a detached start and a stop."""

import json
import os
import subprocess
import sys
import time

import psutil
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))
import area_download as ad  # noqa: E402
import area_rows as ar  # noqa: E402

UTAH = {"name": "utah", "title": "United States: Utah", "continent": "North America", "area": "osm:Utah",
        "source": "usa", "km2": 219900}


def _write(tmp_path, **more):
    settings = {"state_dir": str(tmp_path / "state"), "default_target": "cache",
                "targets": {"cache": {"data_dir": str(tmp_path / "app")},
                            "NAS": {"data_dir": str(tmp_path / "local"), "tiles": str(tmp_path / "share"),
                                    "min_free_gb": 200}}}
    settings.update(more)
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return str(path)


@pytest.fixture
def settings(tmp_path):
    return ar.load_settings(_write(tmp_path, extra=[UTAH], rows={
        "poland": {"target": "NAS", "host_slots": ["opendata.geoportal.gov.pl=2"]}, "utah": {"target": "NAS"}}))


def _row(rows, name):
    return next(row for row in rows if row.name == name)


def test_every_area_of_the_map_is_a_row():
    """A new source's area without a name here fails: it would be missing from the window."""
    with open(os.path.join(ar.COVERAGE, "coverage.json"), encoding="utf-8") as f:
        areas = json.load(f)["areas"]
    rows = ar.catalogue()
    assert set(ar.OSM_NAMES) == set(areas)
    assert len(rows) == len(areas)
    assert len({row.name for row in rows}) == len(rows)
    for row in rows:
        assert row.title and row.area.startswith("osm:") and row.km2 > 0 and row.resolution > 0
        assert row.continent in ar.CONTINENTS


def test_the_names_of_the_downloads_that_ran():
    """A row's name is its state files' name: Poland's and Czechia's were started by hand under these."""
    rows = ar.catalogue()
    assert _row(rows, "poland").area == "osm:Polska" and _row(rows, "poland").source == "geoportal"
    assert _row(rows, "czechia").resolution == 2.0
    assert ar.slug("Germany: Baden-W\u00fcrttemberg") == "germany-baden-wurttemberg"
    assert ar.slug("\u00c5land") == "aland"


def test_a_region_takes_its_countrys_continent():
    rows = ar.catalogue()
    assert _row(rows, "spain-canary-islands").continent == "Europe"
    assert _row(rows, "norway-svalbard").continent == "Europe"
    assert _row(rows, "united-states-alaska").continent == "North America"
    assert _row(rows, "greenland").continent == "North America"
    assert _row(rows, "australia-tasmania").continent == "Oceania"


def test_the_list_by_continent_with_its_settings(settings):
    rows = ar.rows_of(settings)
    assert [row.continent for row in rows] == sorted((row.continent for row in rows),
                                                     key=ar.CONTINENTS.index)
    assert sum(row.continent == "Oceania" for row in rows) == 3
    utah = _row(rows, "utah")
    assert (utah.title, utah.source, utah.resolution, utah.km2) == ("United States: Utah", "usa", 1.0, 219900)
    assert _row(rows, "poland").host_slots == ("opendata.geoportal.gov.pl=2",)


def test_a_row_may_ask_another_resolution(tmp_path):
    settings = ar.load_settings(_write(tmp_path, rows={"austria": {"resolution": 2}}))
    assert _row(ar.rows_of(settings), "austria").resolution == 2.0


@pytest.mark.parametrize("more, text", [
    ({"default_target": "elsewhere"}, "no target named elsewhere"),
    ({"rows": {"poland": {"target": "elsewhere"}}}, "no target named elsewhere"),
    ({"targets": {"cache": {}}}, "needs state_dir and targets"),
    ({"targets": {}}, "needs state_dir and targets"),
])
def test_settings_that_cannot_be_used(tmp_path, more, text):
    with pytest.raises(ar.SettingsError, match=text):
        ar.load_settings(_write(tmp_path, **more))


def test_settings_file_unreadable(tmp_path):
    with pytest.raises(ar.SettingsError):
        ar.load_settings(str(tmp_path / "none.json"))
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(ar.SettingsError, match="not JSON"):
        ar.load_settings(str(tmp_path / "bad.json"))


@pytest.mark.parametrize("more, text", [
    ({"rows": {"atlantis": {}}}, "atlantis"),
    ({"extra": [{"name": "x", "area": "osm:X", "source": "no_such_source"}]}, "extra area x"),
])
def test_rows_that_cannot_be_used(tmp_path, more, text):
    with pytest.raises(ar.SettingsError, match=text):
        ar.rows_of(ar.load_settings(_write(tmp_path, **more)))


def test_the_target_of_a_row(settings):
    """The window's choice over the settings' over the default, kept when the window closes."""
    rows = ar.rows_of(settings)
    poland, austria = _row(rows, "poland"), _row(rows, "austria")
    assert ar.target_of(poland, settings, {}) == "NAS"
    assert ar.target_of(austria, settings, {}) == "cache"
    ar.save_target("austria", "NAS", settings)
    ar.save_target("poland", "cache", settings)
    chosen = ar.targets_chosen(settings)
    assert ar.target_of(poland, settings, chosen) == "cache"
    assert ar.target_of(austria, settings, chosen) == "NAS"


def test_a_target_that_went_away_is_forgotten(settings):
    ar.save_target("austria", "NAS", settings)
    del settings.targets["NAS"]
    assert ar.targets_chosen(settings) == {}


def test_free_space_of_a_share_out_of_reach(tmp_path):
    assert ar.free_gb(str(tmp_path)) > 0
    assert ar.free_gb(str(tmp_path / "away")) is None


def test_states_without_a_state_folder(settings):
    assert ar.states(settings) == {}


def test_states_by_name(settings):
    os.makedirs(settings.state_dir)
    ad.write_state(settings.state_dir, "poland", {"name": "poland", "stage": "stopped"})
    assert ar.states(settings)["poland"]["stage"] == "stopped"


def _nas(settings):
    return settings.targets["NAS"]


def _poland(settings):
    return _row(ar.rows_of(settings), "poland")


def test_a_target_on_this_disk_needs_no_links(settings):
    assert ar.links_of(_poland(settings), settings.targets["cache"]) == ([], None)


def test_links_of_the_tile_folders(settings):
    """One for each layer's folder, the folder at the same place on the share."""
    needed, problem = ar.links_of(_poland(settings), _nas(settings))
    assert problem is None
    assert [os.path.relpath(link.path, _nas(settings).data_dir) for link in needed] == [
        os.path.join("cache", "poland", "nmt"), os.path.join("cache", "poland", "nmpt")]
    assert [os.path.relpath(link.target, _nas(settings).tiles) for link in needed] == [
        os.path.join("poland", "nmt"), os.path.join("poland", "nmpt")]


def test_a_source_without_a_surface_model_has_one_link(settings):
    needed, _ = ar.links_of(_row(ar.rows_of(settings), "utah"), _nas(settings))
    assert [link.target.replace("\\", "/").rsplit("/", 2)[1:] for link in needed] == [["usa", "3dep-1m"]]


def test_links_that_are_there_are_kept(settings, monkeypatch):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    links = {link.path: link.target for link in needed}
    monkeypatch.setattr(os.path, "islink", lambda path: path in links)
    # As Windows gives them
    monkeypatch.setattr(os, "readlink", lambda path: "\\\\?\\UNC" + links[path][1:] if links[path][:2] == "\\\\"
                        else links[path])
    assert ar.links_of(_poland(settings), _nas(settings)) == ([], None)


def test_a_link_to_another_folder_stops_a_row(settings, monkeypatch):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    monkeypatch.setattr(os.path, "islink", lambda path: path == needed[0].path)
    monkeypatch.setattr(os, "readlink", lambda path: os.path.join("elsewhere", "nmt"))
    links, problem = ar.links_of(_poland(settings), _nas(settings))
    assert links == [] and "another folder" in problem


def test_tiles_on_this_disk_stop_a_row(settings):
    """A link in their place would hide them."""
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    os.makedirs(needed[0].path)
    with open(os.path.join(needed[0].path, "tile.tif"), "wb") as f:
        f.write(b"x")
    links, problem = ar.links_of(_poland(settings), _nas(settings))
    assert links == [] and "holds tiles on this disk" in problem


def test_an_empty_folder_gives_way_to_its_link(settings):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    os.makedirs(needed[0].path)
    assert ar.links_of(_poland(settings), _nas(settings)) == (needed, None)
    assert not os.path.exists(needed[0].path)


def test_a_new_cache_with_real_links_is_a_cache(settings):
    """The links are its first content: without LAYOUT before them the download's first pass refuses the cache."""
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    if ar.make_links(needed, settings.state_dir, elevated=lambda links, state_dir: None):
        pytest.skip("no symbolic links without an administrator here")
    cache_dir = needed[0].cache
    assert os.listdir(cache_dir)
    ar.cache.check_layout(cache_dir)      # exits for a cache of another layout
    assert ar.links_of(_poland(settings), _nas(settings)) == ([], None)
    with open(os.path.join(needed[0].path, "tile.tif"), "wb") as f:
        f.write(b"x")
    assert os.path.exists(os.path.join(needed[0].target, "tile.tif"))


def test_a_new_cache_is_marked_before_its_links(settings, monkeypatch):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    order = []

    def linked(target, path, target_is_directory=False):
        order.append(os.path.exists(os.path.join(needed[0].cache, "LAYOUT")))
    monkeypatch.setattr(os, "symlink", linked)
    monkeypatch.setattr(os.path, "islink", lambda path: True)
    assert ar.make_links(needed, settings.state_dir, elevated=pytest.fail) == []
    assert order == [True, True]


def test_a_cache_of_another_layout_is_an_error_not_an_exit(settings):
    """The window's thread would end without a word."""
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    os.makedirs(needed[0].cache)
    with open(os.path.join(needed[0].cache, "old.txt"), "w", encoding="utf-8") as f:
        f.write("x")
    with pytest.raises(OSError, match="another layout"):
        ar.make_links(needed, settings.state_dir, elevated=pytest.fail)


def _privilege_error(*args, **kwargs):
    error = OSError("A required privilege is not held by the client")
    error.winerror = ar.ERROR_PRIVILEGE_NOT_HELD
    raise error


def test_links_without_a_window_when_the_system_allows(settings, monkeypatch):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    made = {}
    monkeypatch.setattr(os, "symlink", lambda target, path, target_is_directory=False: made.update({path: target}))
    monkeypatch.setattr(os.path, "islink", lambda path: path in made)
    assert ar.make_links(needed, settings.state_dir, elevated=pytest.fail) == []
    assert made == {link.path: link.target for link in needed}
    assert all(os.path.isdir(link.target) for link in needed)


def test_links_by_one_uac_window_on_windows_without_the_privilege(settings, monkeypatch):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    monkeypatch.setattr(os, "symlink", _privilege_error)
    made, calls = set(), []

    def elevated(links, state_dir):
        calls.append(list(links))
        made.update(link.path for link in links)
    monkeypatch.setattr(os.path, "islink", lambda path: path in made)
    assert ar.make_links(needed, settings.state_dir, elevated=elevated) == []
    assert calls == [needed]


def test_links_refused_at_the_uac_window_are_reported(settings, monkeypatch):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))
    monkeypatch.setattr(os, "symlink", _privilege_error)
    assert ar.make_links(needed, settings.state_dir, elevated=lambda links, state_dir: None) == needed


def test_another_link_error_is_raised(settings, monkeypatch):
    needed, _ = ar.links_of(_poland(settings), _nas(settings))

    def fail(*args, **kwargs):
        raise OSError("the share went away")
    monkeypatch.setattr(os, "symlink", fail)
    with pytest.raises(OSError, match="went away"):
        ar.make_links(needed, settings.state_dir, elevated=pytest.fail)


def test_the_elevated_script(settings, monkeypatch, tmp_path):
    """Windows PowerShell 5.1 reads non-ASCII paths only with the BOM; a quote in a path is doubled."""
    seen = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: seen.append(command))
    os.makedirs(settings.state_dir)
    ar._elevated([ar.Link("C:\\data\\it's", "\\\\nas\\Udost\u0119pnione\\poland", "C:\\data")], settings.state_dir)
    with open(os.path.join(settings.state_dir, "links.ps1"), "rb") as f:
        script = f.read()
    assert script.startswith(b"\xef\xbb\xbf")
    assert "cmd /c mklink /D 'C:\\data\\it''s' '\\\\nas\\Udost\u0119pnione\\poland'" in script.decode("utf-8-sig")
    assert "-Verb RunAs" in seen[0][-1] and "-Wait" in seen[0][-1]


def test_the_command_is_the_one_by_hand(settings, monkeypatch):
    """`run` reads what the window starts: the row and the target become the same Area."""
    row = _poland(settings)
    command = ar.command_of(row, _nas(settings), settings)
    assert command[0] == sys.executable and command[2] == "run"
    seen = []
    monkeypatch.setattr(ad, "supervise", lambda area, passes: seen.append((area, passes)) or 0)
    assert ad.main(command[2:]) == 0
    area, passes = seen[0]
    assert (area.name, area.area, area.source, area.resolution) == ("poland", "osm:Polska", "geoportal", 1.0)
    assert area.data_dir == _nas(settings).data_dir and area.state_dir == settings.state_dir
    assert area.min_free_gb == 200 and area.host_slots == (("opendata.geoportal.gov.pl", 2),)
    assert "--number" in passes


def test_the_contact_stays_out_of_the_command(tmp_path):
    """A command line can be read by anyone on the machine, and lands in logs."""
    settings = ar.load_settings(_write(tmp_path, contact="someone@example.org"))
    row = ar.rows_of(settings)[0]
    assert "someone@example.org" not in " ".join(ar.command_of(row, settings.targets["cache"], settings))


def test_start_detached_with_the_contact_in_its_environment(tmp_path, monkeypatch):
    settings = ar.load_settings(_write(tmp_path, contact="someone@example.org"))
    seen = {}

    class Process:
        pid = 1234

        def __init__(self, command, **kwargs):
            seen.update(kwargs, command=command)
    monkeypatch.setattr(subprocess, "Popen", Process)
    row = ar.rows_of(settings)[0]
    assert ar.start(row, settings.targets["cache"], settings) == 1234
    assert seen["env"]["FINDALINE_CONTACT"] == "someone@example.org"
    assert seen["stdin"] == subprocess.DEVNULL and seen["cwd"] == ar.REPO
    if os.name == "nt":
        assert seen["creationflags"] & subprocess.CREATE_NO_WINDOW
    else:
        assert seen["start_new_session"] is True


def test_a_started_process_outlives_who_started_it(tmp_path):
    """The window's process ends, the download goes on (a process of its own, on either system)."""
    pid_file = tmp_path / "pid.txt"
    child = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(30)"
    parent = ("import subprocess, sys\n"
              f"sys.path.insert(0, {os.path.join(REPO, 'tools')!r})\n"
              "import area_rows as ar\n"
              f"subprocess.Popen([sys.executable, '-c', {child!r}, {str(pid_file)!r}], stdin=subprocess.DEVNULL,\n"
              "                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **ar._detached())\n")
    subprocess.run([sys.executable, "-c", parent], check=True, timeout=60)
    deadline = time.monotonic() + 15
    while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < deadline:
        time.sleep(0.05)
    process = psutil.Process(int(pid_file.read_text()))
    try:
        assert process.is_running()
    finally:
        process.kill()


def test_stop_writes_what_the_supervisor_waits_for(settings):
    os.makedirs(settings.state_dir)
    ar.stop(["poland", "utah"], settings)
    assert os.path.exists(ad.state_file(settings.state_dir, "poland", ".stop"))
    assert os.path.exists(ad.state_file(settings.state_dir, "utah", ".stop"))


def test_the_tui_command_without_the_group(tmp_path, monkeypatch, capsys):
    """No textual: a line saying what to do, not a traceback."""
    monkeypatch.setitem(sys.modules, "area_download_tui", None)
    assert ad.main(["tui", "--settings", str(tmp_path / "none.json")]) == 2
    assert "uv sync --group tui" in capsys.readouterr().err
