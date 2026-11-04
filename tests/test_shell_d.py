"""Prototype D of the new interface (?ui=d, viewer/src/app/d) in headless Edge, offline: C's home and new search
(test_shell_c's fixtures and page helpers) with B's result (result/view/ResultWorkspace): the panel on the right,
the profile docked at the bottom of the page, "‹ Home", the line in the hash and in copied links, Back and
Forward, and phones (C's bottom navigation, B's sheet); no CSP violations anywhere."""

import json
import os
import urllib.parse

import pytest

from test_shell_c import BIG, SMALL, _edge, big_clip, data, stub_page  # noqa: F401 (fixtures)
from test_web import EDGE, _server

DESKTOP_SCRIPT = """
const BIG = "%(big)s", SMALL = "%(small)s", POINT = {lat: 50.1559508, lng: 19.7562722};
const model = () => window.FINDALINE_RESULT && window.FINDALINE_RESULT.model;
const near = (a, b) => Math.abs(a - b) <= 16;
let job = "";
run({
  home(next) { wait(() => card("run", SMALL) && card("run", BIG) && $(".c-account-btn"), () => {
    result.home = [$$(".c-card").map((c) => c.dataset.run || c.dataset.job), !!$(".ui.u-app-d.c-app"), !!$(".c-top")];
    $(".c-account-btn").click();
    later(() => { result.account = text(".c-account-links"); $(".c-account-btn").click(); next(); });
  }); },
  newSearch(next) {
    $(".c-new").click();
    wait(() => window.FINDALINE_PLACE && $(".s-panel") && $(".c-bar .s-start"), () => {
      result.newPage = [location.hash, text(".s-card.u-on b")];
      // The place box: Enter looks the name up, ↓ and Enter pick the second match, the map goes there
      const box = $(".s-placebox input"), key = (k) => box.dispatchEvent(new KeyboardEvent("keydown", {key: k, bubbles: true}));
      box.value = "Giewont";
      box.dispatchEvent(new Event("input", {bubbles: true}));
      later(() => { key("Enter"); wait(() => $$(".s-placebox-list li").length === 2, () => {
        result.places = [PLACES.slice(), $$(".s-placebox-list li b").map((b) => b.textContent)];
        key("ArrowDown");
        later(() => { key("Enter"); later(() => {
          const c = window.FINDALINE_PLACE.map.getCenter();
          result.went = [Math.abs(c.lat - 49.2508) < 1e-3 && Math.abs(c.lng - 19.9339) < 1e-3,
                         window.FINDALINE_PLACE.map.getZoom(), box.value, !$(".s-placebox-list")];
          // Leaving draw mode ends an unfinished polygon (its shape would join the search unseen)
          const place = window.FINDALINE_PLACE;
          place.setMode("draw");
          place.map.pm.enableDraw("Polygon");
          const drawing = place.map.pm.globalDrawModeEnabled();
          place.setMode("point");
          result.draw = [drawing, place.map.pm.globalDrawModeEnabled()];
          window.FINDALINE_PLACE.map.fire("click", {latlng: POINT});
          wait(() => text(".c-bar .s-bar-line").startsWith("Ready"), () => {
            $(".c-bar .s-start").click();
            wait(() => location.hash === "#home" && $(".c-card-new"), () => {
              job = $(".c-card-new").dataset.job;
              result.started = [job, $(".c-card-new").dataset.status];
              next();
            });
          });
        }); }, 100);
      }); }, 100);
    });
  },
  progress(next) {
    pushEvent({seq: 1000001, job, kind: "status", data: {status: "computing"}});
    wait(() => card("job", job).dataset.status === "running", () => {
      pushEvent({seq: 1000002, job, kind: "status", data: {status: "done", run_id: SMALL}});
      wait(() => card("job", job).dataset.status === "done" && card("job", job).dataset.run === SMALL, () => {
        result.done = $$(`.c-card[data-run="${SMALL}"]`).length;
        next();
      });
    });
  },
  open(next) {
    card("job", job).querySelector("a.c-card-open").click();
    wait(() => $(".b-results .r-rows .r-row") && $(".d-map.leaflet-container") && model(), () => {
      const panel = $(".b-results").getBoundingClientRect(), dock = $(".b-dock").getBoundingClientRect();
      result.layout = {hash: location.hash, header: !!$(".c-top"), panelRight: near(panel.right, innerWidth - 12),
                       panelTall: panel.height > innerHeight - 40, dockBottom: near(dock.bottom, innerHeight - 12),
                       dockLeftOfPanel: dock.right <= panel.left, home: !!button("Home"), edit: !!button("Edit & run again"),
                       actions: $$(".b-run-actions .r-actions button").map((b) => b.getAttribute("aria-label") || b.textContent.trim()),
                       name: text(".b-pill-name"), sort: text(".r-col.r-on")};
      result.sorted = model().rows.slice(0, 5).every((r, k, all) => k === 0 || all[k - 1].line.clr >= r.line.clr);
      // The map's controls follow the theme: in the dark one the zoom buttons are the panel's colour, also
      // focused (after a click) and disabled (at the last zoom), where Leaflet's own are light grey
      const root = $(".ui"), map = window.FINDALINE_MAP, colour = (q) => getComputedStyle($(q)).backgroundColor;
      root.dataset.theme = "dark";
      map.setZoom(map.getMaxZoom(), {animate: false});
      $(".leaflet-control-zoom-out").focus();
      later(() => {
        result.dark = {panel: colour(".b-results"), zoom: colour(".leaflet-control-zoom-in"), layers: colour(".leaflet-control-layers"),
                       disabled: $(".leaflet-control-zoom-in").classList.contains("leaflet-disabled"),
                       focused: colour(".leaflet-control-zoom-out")};
        delete root.dataset.theme;
        $(".leaflet-control-zoom-out").blur();
        next();
      });
    });
  },
  select(next) {
    $$(".b-results .r-rows > .r-spot > .r-row")[0].click();
    wait(() => $(".b-results .r-dtitle") && $(".b-dock .fal-profile-title"), () => {
      const m = model(), dock = $(".b-dock .r-dock").getBoundingClientRect();
      result.selected = [text(".b-results .r-eyebrow"), text(".b-dock .fal-profile-title"),
                         decodeURIComponent(location.hash) === `#run=${SMALL}&line=${m.lineLink(m.selected.line)}`,
                         near(dock.bottom, innerHeight - 12)];
      button("Next spot").click();
      later(() => {
        result.stepped = [text(".b-results .r-eyebrow"), m.position,
                          decodeURIComponent(location.hash) === `#run=${SMALL}&line=${m.lineLink(m.selected.line)}`];
        next();
      });
    });
  },
  leave(next) {
    // The profile closed with × comes back with "Profile" and when the spot is selected again; Escape, a
    // click beside the lines and × of the details end the selection; › keeps the focus on itself
    const m = model(), dock = () => !!$(".b-dock .fal-profile-title");
    $(".b-dock .fal-close").click();
    later(() => {
      const closed = [dock(), !!$(".r-reprofile")];
      $(".r-reprofile").click();
      later(() => {
        const shownAgain = dock();
        $(".b-dock .fal-close").click();
        later(() => {
          const rows = () => $$(".b-results .r-rows > .r-spot > .r-row");
          const k = rows().indexOf($(".b-results .r-row.r-sel")), row = () => rows()[k];
          row().click();  // the selected row: unselects
          later(() => { row().click(); later(() => {  // the same spot again: its profile is back
            const reselected = [!!m.selected, dock()];
            document.activeElement.blur();
            document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
            const escaped = !m.selected;
            later(() => { row().click(); later(() => {
              // A click takes the nearest line within reach, and the spot just shown lies about the centre:
              // click where no line reaches, beyond a finger's reach too
              const map = window.FINDALINE_MAP, view = window.FINDALINE_RESULT.view, size = map.getSize();
              let beside = null;
              for (let y = 20; y < size.y && !beside; y += 20)
                for (let x = 20; x < size.x && !beside; x += 20) {
                  const at = map.containerPointToLatLng([x, y]);
                  if (!view.near(at, 40).length) beside = at;
                }
              map.fire("click", {latlng: beside || map.getCenter()});
              const clicked = !!beside && !m.selected;
              later(() => { row().click(); later(() => {
                button("Close the spot").click();
                const closedSpot = !m.selected;
                later(() => { row().click(); later(() => {
                  const nextButton = $(".b-results .r-details button[aria-label='Next spot']");
                  nextButton.focus();
                  nextButton.click();
                  later(() => {
                    result.leave = {closed, shownAgain, reselected, escaped, clicked, closedSpot,
                                    focus: (document.activeElement || {}).getAttribute?.("aria-label") || "",
                                    stepped: m.position === k + 1};
                    next();
                  });
                }); });
              }); });
            }); });
          }); });
        });
      });
    });
  },
  audit(next) {
    // The profile's point goes with its line; a popover closed with Esc gives the focus back to its button
    const view = window.FINDALINE_RESULT.view, chart = $(".b-dock .fal-hover"), box = chart.getBoundingClientRect();
    chart.dispatchEvent(new PointerEvent("pointerdown", {pointerType: "touch", pointerId: 7, bubbles: true,
                                                        clientX: box.left + box.width / 2, clientY: box.top + 5}));
    const dot = !!view.marker;
    button("Next spot").click();
    later(() => {
      const dotGone = !view.marker;
      button("Compare").click();
      later(() => {
        const inside = !!document.activeElement.closest(".r-pop");
        document.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
        later(() => {
          result.audit = {dot, dotGone, inside, closed: !$(".r-pop"), back: document.activeElement.textContent.trim()};
          next();
        });
      });
    });
  },
  filter(next) {
    const m = model(), before = m.shown.spots;
    button("Clearance").click();
    wait(() => $(".r-editor input[type=number]"), () => {
      const input = $(".r-editor input[type=number]");
      input.value = "1000";
      input.dispatchEvent(new Event("change", {bubbles: true}));
      later(() => {
        result.filtered = [before, m.shown.spots, $$(".u-chip.u-on").map((c) => c.textContent.trim())];
        button("Remove the clearance filter").click();
        later(() => {
          result.cleared = m.shown.spots;
          if (!m.selected) $$(".b-results .r-rows > .r-spot > .r-row")[1].click();
          next();
        });
      });
    });
  },
  copy(next) {
    wait(() => $(".b-results .r-copy"), () => {
      $(".b-results .r-copy").click();
      later(() => { result.copied = COPIED[0] || ""; result.line = model().lineLink(model().selected.line); next(); });
    });
  },
  goHome(next) {
    button("Home").click();
    wait(() => location.hash === "#home" && $(".c-cards") && !$(".d-map"), () => { result.home2 = location.hash; next(); });
  },
  back(next) {
    history.back();
    wait(() => location.hash.startsWith("#run=") && model() && model().selected && $(".b-results .r-dtitle"), () => {
      result.back = [decodeURIComponent(location.hash), model().lineLink(model().selected.line)];
      history.forward();
      wait(() => location.hash === "#home" && $(".c-cards"), () => { result.forward = location.hash; next(); });
    });
  },
  link(next) {
    // the copied link has no ?ui=, so it would load the page again (and this script with it): its hash only
    result.copiedPage = COPIED[0].split("#")[0] === location.origin + location.pathname;
    location.hash = COPIED[0].slice(COPIED[0].indexOf("#"));
    wait(() => $(".b-results .r-dtitle") && model() && model().selected, () => {
      result.linked = [model().lineLink(model().selected.line), !!$(".u-app-d")];
      next();
    });
  },
  folders(next) {
    // The favourite button's folders: a new folder, the line saved into it
    const favs = () => fetch("/api/favourites").then((r) => r.json());
    const poll = (ok, then, tries = 30) => favs().then((b) => ok(b) || !tries ? then(b) : later(() => poll(ok, then, tries - 1)));
    const type = (input, value) => { input.value = value; input.dispatchEvent(new Event("input", {bubbles: true})); };
    $(".b-results .r-details .r-fav").click();
    later(() => {
      result.picker = $$(".r-pop .r-folder").map((b) => b.textContent.trim());
      $$(".r-pop button").find((b) => b.textContent.trim().startsWith("New folder")).click();
      later(() => {
        type($(".r-newfolder input"), "Trip");
        later(() => { $(".r-newfolder button[type=submit]").click(); poll((b) => b.favourites.length === 1, (b) => {
          const trip = b.folders[0];
          result.saved = [b.folders.map((f) => f.name), b.favourites[0].folder_id === trip.id, text(".b-results .r-fav")];
          location.hash = "#favourites";
          wait(() => $(".c-shelf .c-folder-row"), () => {
            result.shelf = {tree: $$(".c-tree-name").map((b) => b.textContent.replace(/\\d+$/, "").trim()),
                            top: $$(".c-shelf-main .c-folder-row b").map((b) => b.textContent)};
            $(".c-folder-row .c-folder-open").click();
            wait(() => location.hash === `#favourites&folder=${trip.id}` && $(".c-shelf-main .c-fav[data-line]"), () => {
              $(".c-new-folder").click();
              later(() => { type($(".c-folder-name input"), "Day 1"); later(() => {
                $(".c-folder-name button[type=submit]").click();
                poll((b) => b.folders.length === 2, (b) => {
                  const day = b.folders.find((f) => f.name === "Day 1");
                  result.sub = [day && day.parent_id === trip.id];
                  // Move to… of the line's menu
                  wait(() => $(".c-shelf-main .c-folder-row"), () => {
                    $(".c-fav[data-line] .c-row-menu").click();
                    later(() => {
                      $$(".r-pop .c-menu-item").find((b) => b.textContent.includes("Move to")).click();
                      later(() => {
                        const targets = $$(".r-pop .c-move-target");
                        result.targets = targets.map((b) => [b.textContent.trim(), b.disabled]);
                        targets.find((b) => b.textContent.trim() === "Day 1").click();
                        poll((b) => b.favourites[0].folder_id === day.id, (b) => {
                          result.moved = b.favourites[0].folder_id === day.id;
                          // Dragged: Day 1 onto the top level of the tree (native drag events)
                          const source = $(`.c-folder-row[data-folder="${day.id}"]`), top = $(".c-shelf-tree .c-tree-row");
                          const dt = new DataTransfer(), box = top.getBoundingClientRect();
                          const at = {bubbles: true, cancelable: true, dataTransfer: dt, clientX: box.left + 20, clientY: box.top + 10};
                          source.dispatchEvent(new DragEvent("dragstart", at));
                          later(() => {
                            top.dispatchEvent(new DragEvent("dragenter", at));
                            top.dispatchEvent(new DragEvent("dragover", at));
                            later(() => {
                              result.over = top.classList.contains("c-drop-over");
                              top.dispatchEvent(new DragEvent("drop", at));
                              source.dispatchEvent(new DragEvent("dragend", at));
                              poll((b) => b.folders.find((f) => f.id === day.id).parent_id === null, (b) => {
                                result.dragged = b.folders.find((f) => f.id === day.id).parent_id === null;
                                // Trip deleted with what is in it (Day 1 is not in it any more)
                                location.replace("#favourites");
                                wait(() => $$(".c-shelf-main .c-folder-row").length === 2, () => {
                                  $(`.c-folder-row[data-folder="${day.id}"] .c-row-menu`).click();
                                  later(() => {
                                    $$(".r-pop .c-menu-item").find((b) => b.textContent.includes("Delete")).click();
                                    wait(() => $(".c-confirm-delete"), () => {
                                      result.confirm = [text(".c-shelf .c-confirm span"),
                                                        document.activeElement.textContent.trim()];
                                      $(".c-confirm-delete").click();
                                      // (a listing during the deletion may see its folders gone, its lines not yet)
                                      poll((b) => b.folders.length === 1 && !b.favourites.length, (b) => {
                                        result.deleted = [b.folders.map((f) => f.name), b.favourites.length];
                                        next();
                                      });
                                    });
                                  });
                                });
                              });
                            }, 300);
                          }, 300);
                        });
                      });
                    });
                  });
                });
              }); });
            });
          });
        }); });
      });
    });
  },
});
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_shell_d_desktop(data, tmp_path):
    """C's home with the runs as cards and its account menu (Try interface B, Try interface C); New search returns home
    with the new card, which runs and turns done; its card opens B's result on a full-screen map: the panel on
    the right, the profile docked at the bottom left of it, "‹ Home", Edit & run again and the run's actions,
    sorted by clearance, the map's controls dark in the dark theme (focused and disabled too); a row selects its line (details under the row, the profile in the dock, the hash),
    ‹ › and a filter chip; Copy link gives the address without ?ui=; Home returns; Back and Forward; the copied
    link opens the line (in D, the interface remembered); no CSP violations."""
    page = stub_page(data, "dtest", DESKTOP_SCRIPT % {"big": BIG, "small": SMALL})
    with _server(data) as port:
        r = _edge(port, page + "?ui=d", tmp_path / "edge")
    assert "timeout" not in r and "error" not in r, json.dumps(r)
    assert set(r["home"][0]) == {SMALL, BIG} and r["home"][1] and r["home"][2], r
    assert all(t in r["account"] for t in ("Try interface B", "Try interface C")) and "Try interface D" not in r["account"], r
    assert "Old interface" not in r["account"], r
    assert r["newPage"] == ["#new", "Typical highline"] and r["started"][1] == "waiting" and r["done"] == 1, r
    assert r["leave"] == {"closed": [False, True], "shownAgain": True, "reselected": [True, True], "escaped": True,
                          "clicked": True, "closedSpot": True, "focus": "Next spot", "stepped": True}, r
    assert r["audit"] == {"dot": True, "dotGone": True, "inside": True, "closed": True, "back": "Compare"}, r
    assert r["draw"] == [True, False], r
    assert r["places"] == [["Giewont"], ["Kraków", "Giewont"]] and r["went"] == [True, 15, "Giewont", True], r
    layout = r["layout"]
    assert layout["hash"] == f"#run={SMALL}" and not layout["header"] and layout["name"] == "Small run", r
    assert layout["panelRight"] and layout["panelTall"] and layout["dockBottom"] and layout["dockLeftOfPanel"], r
    assert layout["home"] and layout["edit"] and {"Compare", "Download"} <= set(layout["actions"])
    assert any(a.startswith("Measure") for a in layout["actions"]), r
    assert layout["sort"].startswith("Clear.") and r["sorted"], r
    dark = r["dark"]
    assert dark["disabled"] and dark["zoom"] == dark["layers"] == dark["panel"] != "rgb(255, 255, 255)", r
    assert dark["focused"] not in (dark["panel"], "rgb(244, 244, 244)"), r
    assert r["selected"][0].startswith("Spot 1 of ") and r["selected"][1].startswith("Profile"), r
    assert r["selected"][2] and r["selected"][3], r
    assert r["stepped"][0].startswith("Spot 2 of ") and r["stepped"][1] == 1 and r["stepped"][2], r
    before, after, chips = r["filtered"]
    assert after < before and any(c.startswith("Clearance ≥") for c in chips) and r["cleared"] == before, r
    assert "ui=" not in r["copied"] and r["copiedPage"], r  # the reader's interface opens it
    assert r["copied"].endswith(f"#run={SMALL}&line=" + urllib.parse.quote(r["line"], safe="")), r
    assert r["home2"] == "#home", r
    assert r["back"] == [f"#run={SMALL}&line={r['line']}", r["line"]], r
    assert r["forward"] == "#home" and r["linked"] == [r["line"], True], r
    assert r["picker"] == ["Favourites (top level)"] and r["saved"] == [["Trip"], True, "Favourite"], r
    assert r["shelf"] == {"tree": ["Favourites", "Trip"], "top": ["Trip"]} and r["sub"] == [True], r
    assert r["targets"] == [["Favourites (top level)", False], ["Trip", True], ["Day 1", False]] and r["moved"], r
    assert r["over"] and r["dragged"], r
    assert r["confirm"] == ["Delete “Day 1” and 1 favourite line? This cannot be undone.", "Keep it"], r
    assert r["deleted"] == [["Trip"], 0], r
    assert r["csp"] == []


PICK_SCRIPT = """
const SMALL = "%(small)s";
const model = () => window.FINDALINE_RESULT && window.FINDALINE_RESULT.model;
const map = () => window.FINDALINE_MAP, view = () => window.FINDALINE_RESULT.view;
const box = () => map().getContainer().getBoundingClientRect();
// A point of the map's container (without Leaflet's rounding of layer points)
const point = (lat, lon) => map().layerPointToContainerPoint(map().project([lat, lon]).subtract(map().getPixelOrigin()));
const dist = (p, l) => {
  const a = point(l.lat1, l.lon1), b = point(l.lat2, l.lon2), dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
  return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy);
};
// The lines drawn: the shown line of each spot, all lines of the selected one
const drawn = () => {
  const m = model(), sel = m.selected && m.selected.group, out = [];
  m.groups.forEach((g) => (g === sel ? g.members : [m.shownOf(g)]).forEach((l) => out.push({l, g})));
  return out;
};
const free = (p) => {
  const el = document.elementFromPoint(box().left + p.x, box().top + p.y);
  return !!el && el.tagName === "CANVAS" && !!el.closest(".leaflet-overlay-pane");
};
// A whole pixel `offset` px beside the middle of a drawn line that `want` takes, where that line is the nearest
// of its spot's and the other spots' lines are `margin` px farther; `avoid`: spots to keep 40 px away
const beside = (want, offset, margin, avoid = []) => {
  const all = drawn();
  for (const {l, g} of all) {
    if (!want(l, g)) continue;
    const a = point(l.lat1, l.lon1), b = point(l.lat2, l.lon2), len = Math.hypot(b.x - a.x, b.y - a.y);
    if (len < 2 * offset + 30) continue;
    for (const side of [1, -1]) {
      const p = {x: Math.round((a.x + b.x) / 2 - side * offset * (b.y - a.y) / len),
                 y: Math.round((a.y + b.y) / 2 + side * offset * (b.x - a.x) / len)};
      const mine = dist(p, l);
      if (!free(p) || all.some((o) => o.l !== l && (o.g === g ? dist(p, o.l) < mine : dist(p, o.l) < mine + margin))) continue;
      if (avoid.some((h) => h.members.some((x) => dist(p, x) < 40))) continue;
      return {p, l, g};
    }
  }
  return null;
};
// What the browser sends for a click of the mouse (or a tap of a finger) at a point: to the element there
const click = (p, finger) => {
  const x = box().left + p.x, y = box().top + p.y, init = {bubbles: true, cancelable: true, clientX: x, clientY: y, view: window};
  document.elementFromPoint(x, y).dispatchEvent(finger ? new PointerEvent("click", {...init, pointerType: "touch"})
                                                       : new MouseEvent("click", init));
};
const move = (p) => {
  const x = box().left + p.x, y = box().top + p.y;
  document.elementFromPoint(x, y).dispatchEvent(new MouseEvent("mousemove", {bubbles: true, clientX: x, clientY: y, view: window}));
};
const selectedIs = (g) => !!model().selected && model().selected.group === g;
run({
  open(next) { wait(() => model() && map() && $(".b-results .r-rows .r-row"), () => {
    result.zoom = map().getZoom();
    next();
  }); },
  near(next) {
    // 4 px beside a spot with similar lines (once its lines had a second canvas over the map), then beside
    // another: zoomed in on the first spot of the list until both are found
    let a = null, b = null;
    const first = model().rows[0].line, centre = [(first.lat1 + first.lat2) / 2, (first.lon1 + first.lon2) / 2];
    for (let z = result.zoom + 1; z <= map().getMaxZoom() && !b; z++) {
      map().setView(centre, z, {animate: false});
      a = beside((l, g) => g.members.length > 1, 4, 6);
      b = a && beside((l, g) => g !== a.g, 4, 6, [a.g]);
    }
    result.found = [!!a, !!b];
    model().select(null);
    click(a.p);
    result.near = selectedIs(a.g);
    click(b.p);
    result.switched = selectedIs(b.g);
    // the mouse shows the line a click takes, and Leaflet's pointer
    model().select(null);
    later(() => {
      move(a.p);
      later(() => {
        result.hover = [view().mapHovered === a.l, !!$(".leaflet-overlay-pane canvas.leaflet-interactive")];
        // beside every line: the selection ends, the pointer goes
        const empty = (() => {
          const w = box().width, h = box().height;
          for (let y = 80; y < h - 80; y += 10) for (let x = 20; x < w - 420; x += 10)
            if (free({x, y}) && drawn().every((d) => dist({x, y}, d.l) > 40)) return {x, y};
          return null;
        })();
        move(empty);
        click(a.p);  // selected again, then a click beside every line
        later(() => {
          result.unhover = !$(".leaflet-overlay-pane canvas.leaflet-interactive");
          click(empty);
          result.beside = [!!empty, !model().selected];
          // a thin line of a selected spot, clear of its other lines (taken, it is the one its spot shows)
          let v = null;
          for (const g of model().groups.filter((h) => h.members.length > 1).slice(0, 40)) {
            model().select(g);
            v = beside((l, h) => h === g && l !== model().selected.line, 2, 3);
            if (v) break;
          }
          if (v) click(v.p);
          result.variant = v ? [selectedIs(v.g), model().selected.line === v.l] : "none";
          next();
        }, 100);
      }, 100);
    }, 100);
  },
  finger(next) {
    // 14 px: a finger's tap takes the line, the mouse's click does not (no other spot within 8 px more)
    let f = null;
    model().select(null);
    const first = model().rows[0].line, centre = [(first.lat1 + first.lat2) / 2, (first.lon1 + first.lon2) / 2];
    for (let z = result.zoom + 1; z <= map().getMaxZoom() && !f; z++) {
      map().setView(centre, z, {animate: false});
      f = beside(() => true, 14, 9);
    }
    result.fingerFound = !!f;
    model().select(null);
    click(f.p);
    const mouse = !!model().selected;
    click(f.p, true);
    result.finger = [mouse, selectedIs(f.g)];
    // WebKit's click after a tap: a "mouse" PointerEvent, the press before it a "touch" one
    model().select(null);
    const x = box().left + f.p.x, y = box().top + f.p.y, init = {bubbles: true, cancelable: true, clientX: x, clientY: y, view: window};
    document.elementFromPoint(x, y).dispatchEvent(new PointerEvent("pointerdown", {...init, pointerType: "touch"}));
    document.elementFromPoint(x, y).dispatchEvent(new PointerEvent("click", {...init, pointerType: "mouse"}));
    result.webkitTap = selectedIs(f.g);
    document.elementFromPoint(x, y).dispatchEvent(new PointerEvent("pointerdown", {...init, pointerType: "mouse"}));
    // measuring: a click on a line is a point, not a selection
    model().select(null);
    let measured = null;
    view().startMeasure((p, q) => { measured = [p, q]; });
    click(beside(() => true, 0, 6).p);
    result.measuring = [view().isMeasuring, !model().selected];
    view().cancelMeasure();
    view().clearMeasure();
    next();
  },
  choose(next) {
    // Zoomed out, a click where several spots lie about as near: the list of them; the second one taken
    model().select(null);
    map().setZoom(result.zoom - 2, {animate: false});
    later(() => {
      let at = null, near = [];
      for (const {l} of drawn()) {
        const p = point((l.lat1 + l.lat2) / 2, (l.lon1 + l.lon2) / 2), q = {x: Math.round(p.x), y: Math.round(p.y)};
        if (!free(q)) continue;
        near = view().near(map().containerPointToLatLng([q.x, q.y]), 8);
        if (near.length > 1 && near[1].px <= near[0].px + 3) { at = q; break; }
      }
      result.crowd = !!at;
      click(at);
      later(() => {
        const rows = $$(".r-choose [role=option]");
        result.list = [rows.length, Math.min(6, near.filter((c) => c.px <= near[0].px + 3).length),
                       !!document.activeElement.closest(".r-choose")];
        rows[1].click();
        later(() => {
          result.chosen = [selectedIs(near[1].group), !$(".r-choose")];
          // the list again (the selected spot's lines drawn now), closed with Esc
          click(at);
          later(() => {
            const reopened = !!$(".r-choose");
            document.activeElement.dispatchEvent(new KeyboardEvent("keydown", {key: "Escape", bubbles: true, cancelable: true}));
            later(() => { result.escaped = [reopened, !$(".r-choose"), selectedIs(near[1].group)]; next(); });
          });
        });
      });
    });
  },
});
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_shell_d_pick(data, tmp_path):
    """Lines taken on the map with the events a browser sends to whatever lies at a point (the canvas): a click 4 px
    beside a line takes it, also while a spot with similar lines is selected (a second canvas of those lines once
    lay over the map and took every click), a thin line of the selected spot is taken; the mouse shows the line and
    the pointer; a click beside every line ends the selection; 14 px away a finger's tap takes the line (also as
    WebKit sends it: a "mouse" click after a "touch" press), the mouse's click does not; while measuring a click is a
    point; where spots lie about as near, a list of them: its second row taken, Esc closes it and the selection
    stays; no CSP violations."""
    page = stub_page(data, "dpick", PICK_SCRIPT % {"small": SMALL})
    with _server(data) as port:
        r = _edge(port, page + f"?ui=d#run={SMALL}", tmp_path / "edge-pick")
    assert "timeout" not in r and "error" not in r, json.dumps(r)
    assert r["found"] == [True, True] and r["near"] and r["switched"], r
    assert r["variant"] == [True, True], r
    assert r["hover"] == [True, True] and r["unhover"] and r["beside"] == [True, True], r
    assert r["fingerFound"] and r["finger"] == [False, True] and r["webkitTap"] and r["measuring"] == [True, True], r
    assert r["crowd"] and r["list"][0] == r["list"][1] >= 2 and r["list"][2], r
    assert r["chosen"] == [True, True] and r["escaped"] == [True, True, True], r
    assert r["csp"] == []


PHONE_SCRIPT = """
const SMALL = "%(small)s";
run({
  home(next) { wait(() => card("run", SMALL) && $(".u-bnav"), () => {
    result.home = {width: innerWidth, nav: $$(".u-bnav-item").map((b) => b.textContent.trim()), overflow: overflow()};
    next();
  }); },
  result(next) {
    card("run", SMALL).querySelector("a.c-card-open").click();
    wait(() => $(".u-sheet .r-rows .r-row") && window.FINDALINE_RESULT, () => {
      result.sheet = {sheet: !!$(".d-layer .u-sheet"), panel: !!$(".b-results"), nav: !!$(".u-bnav"), top: !!$(".b-top-run .b-pill"),
                      peek: text(".u-sheet-head"), overflow: overflow()};
      $$(".u-sheet .r-rows > .r-spot > .r-row")[0].click();
      wait(() => $(".u-sheet-head .r-eyebrow"), () => { result.peek = text(".u-sheet-head .r-eyebrow"); next(); });
    });
  },
  heights(next) {
    // From the sheet's style (headless Edge does not run the transition): half the map, full under the top bar
    const sheet = () => ({snap: $(".u-sheet").className, height: parseFloat($(".u-sheet").style.height), inner: innerHeight,
                          bar: $(".b-top").getBoundingClientRect().bottom});
    result.half = sheet();
    $(".u-sheet-handle").click();
    later(() => { result.full = sheet(); $(".u-sheet-handle").click(); later(next); });
  },
  step(next) {
    button("Next spot").click();
    later(() => {
      result.stepped = text(".u-sheet-head .r-eyebrow");
      result.after = overflow();
      button("Home").click();
      wait(() => location.hash === "#home" && $(".u-bnav"), () => { result.home2 = location.hash; next(); });
    });
  },
});
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_shell_d_phone(data, tmp_path):
    """Below 768 px: C's home with the bottom navigation; the result is B's sheet over the map ("Spot k of N" with
    ‹ ›, no panel, no bottom navigation) under a top bar whose Home returns; a selected line leaves the sheet at
    half the map, and at full it stays below the top bar; nothing wider than the window; no CSP violations."""
    page = stub_page(data, "dphone", PHONE_SCRIPT % {"small": SMALL})
    with _server(data) as port:
        r = _edge(port, page + "?ui=d", tmp_path / "edge-phone", size="500,900")
    assert "timeout" not in r and "error" not in r, json.dumps(r)
    assert r["home"]["width"] < 768 and r["home"]["nav"] == ["Home", "Favourites", "Account"] and not r["home"]["overflow"], r
    sheet = r["sheet"]
    assert sheet["sheet"] and not sheet["panel"] and not sheet["nav"] and sheet["top"] and not sheet["overflow"], r
    assert r["peek"].startswith("Spot 1 of ") and r["stepped"].startswith("Spot 2 of ") and not r["after"], r
    half, full = r["half"], r["full"]
    assert "u-half" in half["snap"] and half["height"] <= half["inner"] / 2 + 1, r  # a selected line keeps it half
    assert "u-full" in full["snap"] and full["inner"] - full["height"] >= full["bar"], r
    assert r["home2"] == "#home", r
    assert r["csp"] == []



INTRO_SCRIPT = """
const SMALL = "%(small)s";
const seen = (name) => localStorage.getItem("findaline.intro." + name);
const dialog = () => $(".n-intro[open]");
run({
  search(next) { wait(() => $(".s-panel") && dialog(), () => {
    result.search = {title: text(".n-intro[open] h2"), checked: $(".n-intro[open] .n-again input").checked,
                     limits: text(".n-intro[open] .n-limits"),
                     examples: $$(".n-intro[open] .n-examples li b").length, before: seen("search")};
    button("Got it").click();
    later(() => {
      result.search.closed = !dialog();
      result.search.after = seen("search");
      location.hash = "#home";
      wait(() => $(".c-new"), () => { $(".c-new").click(); wait(() => $(".s-panel"), () => later(() => {
        result.search.again = !!dialog();  // put away: not opened again
        $(".s-intro .n-intro-link").click();
        later(() => {
          result.search.link = text(".n-intro[open] h2");
          $(".n-intro[open] .n-again input").click();  // unchecked: shown on the next page load
          button("Got it").click();
          later(() => { result.search.unchecked = [!dialog(), seen("search")]; next(); });
        });
      })); });
    });
  }); },
  result(next) {
    location.hash = "#run=" + SMALL;
    wait(() => $(".r-filters") && dialog(), () => {
      result.result = {title: text(".n-intro[open] h2"), swatches: $$(".n-intro[open] .n-colours .r-sw").length,
                       spot: text(".n-intro[open] i")};
      button("Got it").click();
      later(() => {
        result.result.closed = [!dialog(), seen("result")];
        $(".r-filters .n-intro-link").click();
        later(() => { result.result.link = text(".n-intro[open] h2"); button("Got it").click(); later(next); });
      });
    });
  },
});
"""


@pytest.mark.skipif(not os.path.exists(EDGE), reason="needs Microsoft Edge")
def test_shell_d_intros(data, tmp_path):
    """The intro of a new search ("How a search works") opens once: Got it with "Do not show again" (checked at
    first) puts it away in localStorage, so the next new search opens none; the link in the panel opens it again,
    and Got it without "Do not show again" forgets it. The local app has no limits. A result opens "How to read the
    result" once (the colours' swatches), and its link in the filters opens it again."""
    from test_shell_c import C_STUBS
    from test_web import INTROS_SEEN
    stubs = C_STUBS.replace(INTROS_SEEN, "") + 'try { localStorage.removeItem("findaline.intro.search"); localStorage.removeItem("findaline.intro.result"); } catch (e) {}\n'
    page = stub_page(data, "dintro", INTRO_SCRIPT % {"small": SMALL}, stubs=stubs)
    with _server(data) as port:
        r = _edge(port, page + "?ui=d#new", tmp_path / "edge-intro")
    assert "timeout" not in r and "error" not in r, json.dumps(r)
    search = r["search"]
    assert search["title"] == "How a search works" and search["checked"] and search["before"] is None, r
    assert search["limits"] == "This computer has no limits." and search["examples"] >= 10, r
    assert search["closed"] and search["after"] == "seen" and not search["again"], r
    assert search["link"] == "How a search works" and search["unchecked"] == [True, None], r
    assert r["result"] == {"title": "How to read the result", "swatches": 3, "spot": "spot", "closed": [True, "seen"],
                           "link": "How to read the result"}, r
    assert r["csp"] == []
