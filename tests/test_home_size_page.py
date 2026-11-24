"""A run's size on Home's card and in the line shown while a run downloads (line volume's round 7, step 2d as reduced:
app/c/Home.tsx `stateOf` and `SearchCard`'s body, size.ts, result/view/RunLoading.tsx loadingText): under its name a
finished run's card has two lines of their own, its counts with the thousands grouped by a no-break space, then the
time and its size as stored (run.json's store.bytes, which GET /api/runs sends as "bytes"; none for a run saved
without it); a running search's card keeps its one line and the example's tile shows no size. While the run's two
files download the page counts in the total's unit and cut, so the line ends at the card's number. The cut is
test_size_units' (a MB is 10^6 bytes); `size_text` below is this file's own reading of it.

Playwright's Edge over the public app on a thread (test_rename_home_page's `rename_site`: "a" owns RUN_A, a demo run,
and RUN_B, both the clip's run) and over the local app (test_web's `_server`), offline; a run's run.json rewritten
before the page opens for another size or none; the browser's time zone UTC. Run from PowerShell
(.claude/rules/browser-tests.md)."""

import ast
import json
import math
import os
import re
import sys
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("httpx2")

from test_rename_home_page import (NAME_A, NAME_B, RUN_A, RUN_B, WORDS, Browser, card, open_home,  # noqa: E402,F401
                                   rename_site)
from test_public import account_settings  # noqa: E402,F401
from test_shell_c import copy_clip  # noqa: E402
from test_shell_c_view_map import DESKTOP, SMALL_PHONE, view_clip  # noqa: E402,F401
from test_shell_c_view_map import WAIT as VIEW_WAIT  # noqa: E402
from test_size_units import SIZES  # noqa: E402
from test_web import EDGE, _playwright  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.exists(EDGE) or not _playwright(),
                                reason="needs Microsoft Edge and Playwright (group ui)")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The deadline of every wait for the page, ms (FINDALINE_SIZE_PAGE_WAIT lowers it for a run against a page without
# the change, where waits run out)
WAIT = int(os.environ.get("FINDALINE_SIZE_PAGE_WAIT", VIEW_WAIT))
UTC = {"timezone_id": "UTC"}  # the card's time in the browser's zone (time.ts when): the expected one from run.json
DESKTOP_UTC, PHONE_UTC = {**DESKTOP, **UTC}, {**SMALL_PHONE, **UTC}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
UNITS = re.compile(r"\b[MG]B\b")


def size_text(size) -> str:
    """A size in words by the cut, in exact decimals: "under 0.1 MB" where one decimal of a MB would read "0.0", one
    decimal below 10 MB, whole MB up to 999, then GB with one decimal, each rounded half up; "" for no size."""
    if not isinstance(size, (int, float)) or isinstance(size, bool) or not math.isfinite(size) or size < 0:
        return ""
    mb = Decimal(size) / 10 ** 6
    tenth = mb.quantize(Decimal("0.1"), ROUND_HALF_UP)
    if tenth == 0:
        return "under 0.1 MB"
    if tenth < 10:
        return f"{tenth} MB"
    whole = mb.quantize(Decimal("1"), ROUND_HALF_UP)
    if whole <= 999:
        return f"{whole} MB"
    return f"{(mb / 1000).quantize(Decimal('0.1'), ROUND_HALF_UP)} GB"


def grouped(n: int) -> str:
    """A count with a no-break space at the thousands: "1 048"."""
    return f"{n:,}".replace(",", " ")


def counted(key: str, n: int) -> str:
    """"1 spot", "1 048 lines": the catalogue's plural form of `key` with the count grouped."""
    return WORDS[f"{key}_{'one' if n == 1 else 'other'}"].replace("{{n}}", grouped(n))


def meta_of(data, run: str) -> dict:
    with open(data / "runs" / run / "run.json", encoding="utf-8") as f:
        return json.load(f)


def rewrite(data, run: str, change):
    """run.json of `run` with `change(meta)` applied (before the page asks for the list of runs)."""
    meta = meta_of(data, run)
    change(meta)
    with open(data / "runs" / run / "run.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


def with_bytes(size: int):
    def change(meta):
        meta["store"]["bytes"] = size
    return change


def without_bytes(meta):
    """A run saved without the number: its block `store` without "bytes" (the page still reads its format, so the
    run's map opens)."""
    del meta["store"]["bytes"]


def when_of(meta: dict) -> str:
    """The card's time of a run in UTC (time.ts when): "1 Oct 2026, 10:00"."""
    import cache
    d = datetime.fromisoformat(cache.utc_iso(meta["created"]))
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}, {d.hour:02}:{d.minute:02}"


def opened(browser, device: dict, who="a", script: str = ""):
    page = browser.page(device, who, script)
    page.set_default_timeout(WAIT)
    return page


# A card: its meta lines (class, tag, whether in the card's link, the text, the box, the number of line boxes its
# text takes), the link's children's classes in order, the name's box, the card's whole text
CARD = """(sel) => { const c = document.querySelector(sel), a = c.querySelector('a.c-card-open, div.c-card-open');
  const box = (e) => e.getBoundingClientRect(), rows = (e) => { const r = document.createRange(); r.selectNodeContents(e);
    return new Set([...r.getClientRects()].filter((x) => x.width > 0).map((x) => Math.round(x.top))).size; };
  const name = c.querySelector('.c-card-name');
  return {lines: [...c.querySelectorAll('.c-card-meta')].map((e) => ({cls: e.className, tag: e.tagName, inOpen: e.parentElement === a,
            text: e.textContent, top: box(e).top, bottom: box(e).bottom, rows: rows(e)})),
          link: a.tagName, children: [...a.children].map((e) => e.className), nameBottom: box(name).bottom,
          text: c.textContent}; }"""
META2 = "u-small c-card-meta c-card-meta2"


def two_lines(got: dict, meta: dict, size: str):
    """The checks of a finished run's card (`got`: CARD's) against its run.json: the name, then two lines in the
    card's link, each a line box of its own under the one before; the counts grouped; the time and `size`."""
    spots, lines = meta["summary"]["spots"], meta["summary"]["lines"]
    first, second = (got["lines"] + [None, None])[:2]
    assert len(got["lines"]) == 2, got["lines"]
    assert got["link"] == "A" and got["children"] == ["c-card-name", META2, META2], got
    assert all(line["cls"] == META2 and line["tag"] == "SPAN" and line["inOpen"] for line in got["lines"]), got["lines"]
    assert first["top"] >= got["nameBottom"] - 0.5 and second["top"] >= first["bottom"] - 0.5, got
    assert first["rows"] == 1 and second["rows"] == 1, got["lines"]  # neither broken over two line boxes
    assert first["text"] == f"{counted('ui.result.spots', spots)} · {counted('ui.result.lines', lines)}", first
    if lines >= 1000:
        assert " " in first["text"] and str(lines) not in first["text"], first
    want = f"{when_of(meta)} · {size}" if size else when_of(meta)
    assert second["text"] == want, (second, want)
    if size:
        assert second["text"].rsplit(" · ", 1)[1] == size, second


def test_size_oracle():
    """This file's size_text gives test_size_units' words for each of its sizes, and nothing for no size."""
    assert [(b, size_text(b)) for b, _ in SIZES] == SIZES
    assert [size_text(b) for b in (None, -1, float("nan"), float("inf"))] == [""] * 4


def test_a_finished_runs_card(rename_site):
    """A finished run's card, on a desktop of 1400 by 900 and on a small phone: under its name exactly two lines in
    the card's link (`span.u-small.c-card-meta.c-card-meta2`), each a line box of its own, the second under the
    first: "<spots> · <lines>" with the thousands grouped by a no-break space, then "<date, time> · <size>", the size
    run.json's store.bytes cut by the rule; the date and the time whole, as before."""
    site, data = rename_site
    meta = meta_of(data, RUN_A)
    assert isinstance(meta["store"]["bytes"], int) and meta["summary"]["lines"] > 0, meta.get("store")
    with Browser(site) as browser:
        seen = {}
        for name, device in (("desktop", DESKTOP_UTC), ("phone", PHONE_UTC)):
            page = opened(browser, device)
            open_home(page, site)
            seen[name] = page.evaluate(CARD, card(RUN_A))
    for name, got in seen.items():
        print(name, got["lines"])
        two_lines(got, meta, size_text(meta["store"]["bytes"]))


def test_sizes_by_the_cut(rename_site):
    """The card's size follows the cut: run.json's store.bytes of 38 000 reads "under 0.1 MB", 612 000 "0.6 MB",
    1 840 000 000 (rewritten and the page loaded again) "1.8 GB"."""
    site, data = rename_site
    rewrite(data, RUN_A, with_bytes(38_000))
    rewrite(data, RUN_B, with_bytes(612_000))
    with Browser(site) as browser:
        page = opened(browser, DESKTOP_UTC)
        open_home(page, site)
        page.wait_for_selector(card(RUN_B))
        small, b = page.evaluate(CARD, card(RUN_A)), page.evaluate(CARD, card(RUN_B))
        rewrite(data, RUN_A, with_bytes(1_840_000_000))
        page.reload()
        page.wait_for_selector(card(RUN_A))
        large = page.evaluate(CARD, card(RUN_A))
    assert [size_text(b) for b in (38_000, 612_000, 1_840_000_000)] == ["under 0.1 MB", "0.6 MB", "1.8 GB"]
    two_lines(small, meta_of(data, RUN_A), "under 0.1 MB")
    two_lines(b, meta_of(data, RUN_B), "0.6 MB")
    two_lines(large, meta_of(data, RUN_A), "1.8 GB")


def running_stub(created: str) -> str:
    """An init script (as test_rename_home_page's jobs_stub): the app's job list answered with one search of "a"
    still computing, without its run."""
    return """
const realFetchOfJobs = window.fetch;
window.fetch = (url, init) => String(url).replace(/^https?:\\/\\/[^/]+/, '').split('?')[0] !== '/api/jobs' || (init && init.method && init.method !== 'GET')
  ? realFetchOfJobs(url, init)
  : Promise.resolve(new Response(JSON.stringify({jobs: [{id: 'job-running', status: 'computing', run_id: null, title: 'A running search',
      created: '%s', finished: null, own: true}], seq: 1, worker: true}), {headers: {'content-type': 'application/json'}}));
""" % created


RUNNING = ".c-card[data-job='job-running']"
EXAMPLE = """(phone) => { const e = document.querySelector(phone ? 'a.c-example.c-example-phone' : 'a.c-example:not(.c-example-phone)');
  return e && {run: e.dataset.run, small: e.querySelector('.u-small').textContent, text: e.textContent}; }"""


def test_no_size_where_none_is_known(rename_site):
    """No size where none is known or none is due: (a) a run saved without the number (GET /api/runs sends "bytes":
    null) has the two lines, the second the time alone; (b) a search still running keeps its card's one line
    (`.c-card-meta`, not `.c-card-meta2`) and no MB or GB anywhere in its card; (c) the "Explore an example" tile of
    the demo run says "<name> · <lines grouped>" on a desktop and its name alone on a phone, no MB or GB in either."""
    site, data = rename_site
    rewrite(data, RUN_B, without_bytes)
    meta_a, meta_b = meta_of(data, RUN_A), meta_of(data, RUN_B)
    assert "bytes" not in meta_b["store"] and "format" in meta_b["store"], meta_b["store"]
    with Browser(site) as browser:
        page = opened(browser, DESKTOP_UTC, script=running_stub("2026-10-02T10:00:00+00:00"))
        open_home(page, site, RUN_B)
        page.wait_for_selector(RUNNING)
        page.wait_for_selector("a.c-example")
        listed = {r["id"]: r.get("bytes") for r in page.evaluate("() => fetch('/api/runs').then((r) => r.json())")["runs"]}
        unknown = page.evaluate(CARD, card(RUN_B))
        running = page.evaluate(CARD, RUNNING)
        running["meta2"] = page.evaluate("(sel) => document.querySelectorAll(sel + ' .c-card-meta2').length", RUNNING)
        example = page.evaluate(EXAMPLE, False)
        phone = opened(browser, PHONE_UTC)
        open_home(phone, site)
        phone.wait_for_selector("a.c-example.c-example-phone")
        on_phone = phone.evaluate(EXAMPLE, True)
    assert listed == {RUN_A: meta_a["store"]["bytes"], RUN_B: None}, listed
    two_lines(unknown, meta_b, "")
    assert " · " not in unknown["lines"][1]["text"] and not UNITS.search(unknown["text"]), unknown
    assert len(running["lines"]) == 1 and running["lines"][0]["cls"] == "u-small c-card-meta" and running["meta2"] == 0, running
    assert not UNITS.search(running["text"]), running["text"]
    assert example["run"] == RUN_A and example["small"] == f"{NAME_A} · {counted('ui.result.lines', meta_a['summary']['lines'])}", example
    assert not UNITS.search(example["text"]), example
    assert on_phone["run"] == RUN_A and on_phone["small"] == NAME_A and not UNITS.search(on_phone["text"]), on_phone


def test_the_local_apps_card(tmp_path, view_clip):
    """The local app's Home: the run's card has the same two lines, the second with its size as stored."""
    from test_web import _server
    data = tmp_path / "local"
    data.mkdir()
    copy_clip(view_clip, data, RUN_A, NAME_A)
    meta = meta_of(data, RUN_A)
    with _server(data) as port:
        site = f"http://127.0.0.1:{port}"
        with Browser(site) as browser:
            page = opened(browser, DESKTOP_UTC, who=None)
            open_home(page, site)
            got = page.evaluate(CARD, card(RUN_A))
    two_lines(got, meta, size_text(meta["store"]["bytes"]))


def store_loading() -> str:
    """tools/ui_shots.py's RUN_STORE_LOADING; FINDALINE_UI_SHOTS_ROOT names another checkout to read it from (its
    file's literal, nothing imported), for a run against a checkout whose tool lacks it."""
    root = os.environ.get("FINDALINE_UI_SHOTS_ROOT")
    if not root:
        sys.path.insert(0, os.path.join(REPO, "tools"))
        from ui_shots import RUN_STORE_LOADING
        return RUN_STORE_LOADING
    with open(os.path.join(root, "tools", "ui_shots.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(getattr(target, "id", None) == "RUN_STORE_LOADING" for target in node.targets))


LOADING = """() => { const box = document.querySelector('.c-result-wait'), bar = box.querySelector('.c-loading .u-prog');
  return {line: box.querySelector('.c-loading .u-progress').textContent, now: bar.getAttribute('aria-valuenow'),
          back: (box.querySelector('.c-back') || {}).textContent}; }"""


def test_the_loading_line(rename_site):
    """While the run's two files download (an init script stands in for their requests: 200 000 000 and 47 000 000
    bytes, 30 000 000 and 11 000 000 of them in) the app's page of the run reads "Downloading the run… 41 of 247 MB",
    its bar at 17, with the Back "Home"; with 1 500 000 000 and 340 000 000 bytes, 300 000 000 and 112 000 000 in,
    "Downloading the run… 0.4 of 1.8 GB" (the total's unit and cut: the card's number of that size)."""
    site, _ = rename_site
    script = store_loading()
    larger = script.replace("[200000000, 30000000]", "[1500000000, 300000000]") \
                   .replace("[47000000, 11000000]", "[340000000, 112000000]")
    assert larger.count("[1500000000, 300000000]") == 1 and larger.count("[340000000, 112000000]") == 1, larger
    seen = []
    with Browser(site) as browser:
        for stand_in, now in ((script, "17"), (larger, "22")):
            page = opened(browser, DESKTOP_UTC, script=stand_in)
            page.goto(f"{site}/?ui=c#run={RUN_A}")
            page.wait_for_function("(now) => document.querySelector('.c-result-wait .c-loading .u-prog:not(.u-busy)')"
                                   "?.getAttribute('aria-valuenow') === now", arg=now)
            seen.append(page.evaluate(LOADING))
    assert seen[0] == {"line": "Downloading the run… 41 of 247 MB", "now": "17", "back": "Home"}, seen[0]
    assert seen[1] == {"line": "Downloading the run… 0.4 of 1.8 GB", "now": "22", "back": "Home"}, seen[1]
    assert size_text(247_000_000) == "247 MB" and size_text(1_840_000_000) == "1.8 GB"
    assert WORDS["ui.app.home"] == "Home"
