"""
The window of the area download (`tools/area_download.py tui --settings <file>`, the group `tui` of pyproject.toml): the
catalogue's areas by continent, a checkbox each, Start and Stop asking first, where each area's tiles go, and how far
each download is. What it does is tools/area_rows.py; the downloads themselves run detached (`area_download.py run`) and
go on when the window closes: its state comes from the state folder, as `status` and status.html.

The mouse works in Windows Terminal, the VS Code terminal and the usual Linux terminals; everything has a key too, for
a text console without one or a tmux without `set -g mouse on`.
"""

import os
import sys
from typing import Callable, Dict, List, Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Collapsible, Footer, Input, Static

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import area_download as ad  # noqa: E402
import area_rows as ar  # noqa: E402

STATE_SECONDS = 2
FREE_SECONDS = 60
STARTING_SECONDS = 30       # a row started shows "starting" until its state says more, at most this long
BAR_CELLS = 8
LIVE = ("listing", "downloading", "waiting")


def bar(share: float) -> str:
    full = round(BAR_CELLS * share)
    return "█" * full + "·" * (BAR_CELLS - full)


def km2_text(value: int) -> str:
    return (f"{value:,}".replace(",", " ") + " km²") if value else "-"


def state_text(state: Dict) -> str:
    """A row's state in a line: stage, how far, speed, time left."""
    stage = state["stage"]
    if stage == "downloading" and state["share"] is not None:
        speed = "-" if state["mb_s"] is None else f"{state['mb_s']:.1f} MB/s"
        text = f"{bar(state['share'])} {100 * state['share']:3.0f} %  {speed}  {ad.duration(state['eta'])}"
    elif stage == "listing" and state.get("index_total"):
        text = f"listing, index {state['index_done']:,} of {state['index_total']:,}"
    elif stage == "done":
        text = f"done, {state['gb']:.1f} GB" if state["gb"] >= 1 else f"done, {1000 * state['gb']:.0f} MB"
    elif stage in ("waiting", "needs attention") and state["message"]:
        text = f"{stage}: {state['message']}"
    else:
        text = stage
    if state["failed"] and stage != "needs attention":
        text += f", {state['failed']:,} failed"
    return text + ", no news" if state["stale"] else text


def is_live(state: Optional[Dict]) -> bool:
    return bool(state) and state["stage"] in LIVE and not state["stale"]


class Box(Checkbox):
    """A checkbox that looks like one; up and down go through the list, past the rows that cannot be ticked."""
    BINDINGS = [Binding("up", "app.previous_row", show=False), Binding("down", "app.next_row", show=False)]

    def render(self) -> Content:
        return Content("[x]" if self.value else "[ ]")


class TargetCell(Static):
    """Where a row's tiles go: a click takes the next target."""

    def __init__(self, row: "AreaRow"):
        super().__init__(row.target, classes="target", markup=False)
        self.row = row

    def on_click(self):
        self.app.next_target(self.row)


class AreaRow(Horizontal):
    def __init__(self, row: ar.Row, target: str):
        super().__init__(classes="row", id=f"row-{row.name}")
        self.row, self.target = row, target
        self.state: Optional[Dict] = None
        self.starting = 0.0

    def compose(self) -> ComposeResult:
        row = self.row
        yield Box("", compact=True, id=f"box-{row.name}")
        yield Static(row.title, classes="name", markup=False)
        yield Static(f"{row.resolution:g} m", classes="res")
        yield Static("DTM+DSM" if row.surface else "DTM", classes="layers")
        yield Static(km2_text(row.km2), classes="km2", markup=False)
        yield Static("-", classes="state", markup=False)
        yield TargetCell(self)

    @property
    def box(self) -> Box:
        return self.query_one(Box)

    @property
    def ticked(self) -> bool:
        return self.box.value

    def show(self, state: Optional[Dict], starting: bool):
        """The row's state from the state folder, and what can be done with it."""
        self.state = state
        cell = self.query_one(".state", Static)
        cell.update("starting" if starting else state_text(state) if state else "-")
        stage = state["stage"] if state else ""
        cell.set_class(stage == "done", "-done")
        cell.set_class(stage == "needs attention", "-attention")
        cell.set_class(bool(state) and state["stale"], "-stale")
        done = stage == "done" and not starting
        if done and self.box.value:
            self.box.value = False
        self.box.disabled = done

    def set_target(self, label: str, share: bool):
        self.target = label
        cell = self.query_one(TargetCell)
        cell.update(label)
        cell.set_class(share, "-share")


class Confirm(ModalScreen[bool]):
    """What Start or Stop is about to do. Nothing happens before its button; the first focus is on Cancel."""
    AUTO_FOCUS = "#cancel"
    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel")]

    def __init__(self, title: str, lines: List[str], button: str):
        super().__init__()
        self.heading, self.lines, self.button = title, lines, button

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(self.heading, id="dialog-title", markup=False)
            yield Static("\n".join(self.lines), id="dialog-text", markup=False)
            with Horizontal(id="dialog-buttons"):
                yield Button("Cancel", id="cancel", compact=True)
                yield Button(self.button, id="yes", variant="primary", compact=True)

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


def areas_word(count: int) -> str:
    return f"{count} area" + ("" if count == 1 else "s")


class Downloads(App):
    TITLE = "Find-a-Line: area download"
    AUTO_FOCUS = "Box"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { layout: vertical; }
    #top { height: 1; padding: 0 1; background: $panel; }
    #top-title { width: 1fr; text-style: bold; }
    #top-free { width: auto; }
    #filter { margin: 0 1; }
    #head { height: 1; padding: 0 0 0 2; color: $text-muted; text-style: bold; }
    #head .pad { width: 4; }
    #areas { height: 1fr; }
    Collapsible { padding: 0; margin: 0; border-top: none; background: transparent; }
    CollapsibleTitle { text-style: bold; }
    Collapsible Contents { padding: 0 0 0 2; }
    .row { height: 1; width: 100%; }
    .row:hover, .row:focus-within { background: $boost; }
    Box { width: 4; height: 1; padding: 0; border: none; background: transparent; color: $text-muted; }
    Box.-on { color: $success; text-style: bold; }
    Box:focus { background: $accent 30%; }
    .name, .state, .target { text-wrap: nowrap; text-overflow: ellipsis; }
    .name { width: 33; }
    .res { width: 7; }
    .layers { width: 9; }
    .km2 { width: 16; text-align: right; padding-right: 2; }
    .state { width: 1fr; padding-right: 1; }
    .state.-done { color: $success; }
    .state.-attention { color: $error; text-style: bold; }
    .state.-stale { color: $warning; }
    .target { width: 8; color: $text-muted; text-style: underline; }
    .target.-share { color: $accent; text-style: bold underline; }
    #head .target { text-style: none; }
    #bottom { height: 1; padding: 0 1; dock: bottom; margin-bottom: 1; background: $panel; }
    #summary { width: 1fr; }
    #bottom Button { margin-left: 1; }
    Confirm { align: center middle; }
    #dialog { width: 80; max-height: 80%; height: auto; padding: 1 2; border: round $accent; background: $surface; }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    #dialog-text { height: auto; }
    #dialog-buttons { height: 1; margin-top: 1; align-horizontal: right; }
    #dialog-buttons Button { margin-left: 2; }
    """
    BINDINGS = [
        Binding("slash", "focus_filter", "Filter"),
        Binding("s", "start", "Start"),
        Binding("x", "stop_areas", "Stop"),
        Binding("t", "next_target_of_focused", "Goes to"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, settings: ar.Settings, rows: List[ar.Row], begin: Callable = ar.start,
                 links: Callable = ar.make_links, clock: Callable = None):
        super().__init__()
        self.settings, self.rows, self.begin, self.links = settings, rows, begin, links
        self.chosen = ar.targets_chosen(settings)
        self.free: Dict[str, Optional[float]] = {}
        self.clock = clock or ad.time.time

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            yield Static(self.TITLE, id="top-title", markup=False)
            yield Static("", id="top-free", markup=False)
        yield Input(placeholder="Filter by name, e.g. germany", id="filter", compact=True)
        with Horizontal(id="head"):
            yield Static("", classes="pad")
            yield Static("Area", classes="name")
            yield Static("Grid", classes="res")
            yield Static("Layers", classes="layers")
            yield Static("Size", classes="km2")
            yield Static("State, speed, time left", classes="state")
            yield Static("Goes to", classes="target")
        continents = list(dict.fromkeys(row.continent for row in self.rows))
        with VerticalScroll(id="areas", can_focus=False):
            for continent in continents:
                rows = [row for row in self.rows if row.continent == continent]
                with Collapsible(title=self._group_title(continent, len(rows), 0), collapsed=False,
                                 id=self._group_id(continent)):
                    for row in rows:
                        yield AreaRow(row, ar.target_of(row, self.settings, self.chosen))
        with Horizontal(id="bottom"):
            yield Static("", id="summary", markup=False)
            yield Button("Start", id="start", variant="primary", compact=True)
            yield Button("Stop", id="stop", compact=True)
        yield Footer()

    @staticmethod
    def _group_id(continent: str) -> str:
        return "group-" + ar.slug(continent)

    @staticmethod
    def _group_title(continent: str, rows: int, ticked: int) -> str:
        return f"{continent} ({rows}, {ticked} ticked)" if ticked else f"{continent} ({rows})"

    def on_mount(self):
        for row in self.area_rows():
            row.set_target(row.target, self.settings.targets[row.target].tiles is not None)
        self.refresh_states()
        self.show_free()
        self.read_free()
        self.set_interval(STATE_SECONDS, self.refresh_states)
        self.set_interval(FREE_SECONDS, self.read_free)

    def area_rows(self) -> List[AreaRow]:
        return list(self.query(AreaRow))

    def row_of(self, name: str) -> AreaRow:
        return self.query_one(f"#row-{name}", AreaRow)

    # --- what is shown ---------------------------------------------------------------------------------------

    @work(thread=True, exclusive=True, group="free")
    def read_free(self):
        """In a thread: asking a share that went away takes a while."""
        free = {label: ar.free_gb(target.disk) for label, target in self.settings.targets.items()}
        self.call_from_thread(self._set_free, free)

    def _set_free(self, free: Dict[str, Optional[float]]):
        self.free = free
        self.show_free()

    def show_free(self):
        parts = [f"{label}: " + ("?" if self.free.get(label) is None else f"{self.free[label]:.0f} GB")
                 for label in self.settings.targets]
        contact = "set" if self.settings.contact or os.environ.get("FINDALINE_CONTACT") else "none"
        self.query_one("#top-free", Static).update("free  " + "   ".join(parts) + f"   contact: {contact}")

    def refresh_states(self):
        states = ar.states(self.settings)
        now = self.clock()
        for row in self.area_rows():
            state = states.get(row.row.name)
            if row.starting and (is_live(state) or now - row.starting > STARTING_SECONDS):
                row.starting = 0.0
            row.show(state, bool(row.starting))
        self.refresh_summary()

    def refresh_summary(self):
        rows = self.area_rows()
        ticked = [row for row in rows if row.ticked]
        running = sum(is_live(row.state) for row in rows)
        size = sum(row.row.km2 for row in ticked)
        chosen = f"{len(ticked)} ticked ({km2_text(size)})" if size else f"{len(ticked)} ticked"
        self.query_one("#summary", Static).update(f"{areas_word(len(rows))}, {chosen}, {running} downloading")
        for group in self.query(Collapsible):
            members = list(group.query(AreaRow))
            group.title = self._group_title(members[0].row.continent, len(members),
                                            sum(row.ticked for row in members))

    def on_checkbox_changed(self):
        self.refresh_summary()

    def on_input_changed(self, event: Input.Changed):
        words = event.value.lower().split()
        for row in self.area_rows():
            row.display = all(word in row.row.title.lower() for word in words)
        for group in self.query(Collapsible):
            group.display = any(row.display for row in group.query(AreaRow))
            if words:
                group.collapsed = False

    # --- the keys --------------------------------------------------------------------------------------------

    def action_focus_filter(self):
        self.query_one("#filter", Input).focus()

    def on_input_submitted(self):
        self.action_next_row()

    def key_escape(self):
        """Out of the filter: the list as it was."""
        field = self.query_one("#filter", Input)
        if self.focused is field:
            field.value = ""
            self.action_next_row()

    def action_next_row(self):
        self.screen.focus_next("Box, CollapsibleTitle")

    def action_previous_row(self):
        self.screen.focus_previous("Box, CollapsibleTitle")

    def action_next_target_of_focused(self):
        focused = self.focused
        if focused is not None and isinstance(focused.parent, AreaRow):
            self.next_target(focused.parent)

    def next_target(self, row: AreaRow):
        if is_live(row.state) or row.starting:
            self.notify("Stop it first: the tiles stay where they went", severity="warning")
            return
        labels = list(self.settings.targets)
        label = labels[(labels.index(row.target) + 1) % len(labels)]
        row.set_target(label, self.settings.targets[label].tiles is not None)
        ar.save_target(row.row.name, label, self.settings)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "start":
            self.action_start()
        elif event.button.id == "stop":
            self.action_stop_areas()

    # --- Start and Stop --------------------------------------------------------------------------------------

    def _floor_lines(self, labels: List[str]) -> List[str]:
        lines = []
        for label in labels:
            free = self.free.get(label)
            text = "? free" if free is None else f"{free:.0f} GB free"
            lines.append(f"{label}: {text}, stops below {self.settings.targets[label].min_free_gb:g} GB")
        return lines

    def action_start(self):
        rows = [row for row in self.area_rows() if row.ticked and not is_live(row.state) and not row.starting]
        if not rows:
            self.notify("Tick the areas to download first", severity="warning")
            return
        links, blocked, going = [], [], []
        for row in rows:
            target = self.settings.targets[row.target]
            needed, problem = ar.links_of(row.row, target)
            if problem:
                blocked.append(f"{row.row.title}: {problem}")
            else:
                links += [link for link in needed if link not in links]
                going.append(row)
        lines = [f"{row.row.title[:33]:<34}{row.row.resolution:g} m {km2_text(row.row.km2):>14}  {row.target[:7]:<8}"
                 f"{'resumes' if row.state else 'new'}" for row in going]
        if blocked:
            lines += ["", "Not started:", *blocked]
        if not going:
            self.notify("\n".join(blocked), severity="error", markup=False)
            return
        lines += ["", *self._floor_lines(list(dict.fromkeys(row.target for row in going)))]
        if links:
            lines.append(f"{len(links)} tile folder{'' if len(links) == 1 else 's'} linked to the share"
                         + (": one UAC window" if os.name == "nt" else ""))
        lines.append("Downloads keep running after you close this window.")

        def answered(yes: Optional[bool]):
            if yes:
                now = self.clock()
                for row in going:
                    row.starting = now
                    row.box.value = False
                    row.show(row.state, True)
                self.refresh_summary()
                self.begin_rows(going, links)
        self.push_screen(Confirm(f"Start {areas_word(len(going))}?", lines, "Start"), answered)

    @work(thread=True, exclusive=True, group="start")
    def begin_rows(self, rows: List[AreaRow], links: List[ar.Link]):
        """In a thread: a UAC window waits for its answer. Only the rows whose links are there start."""
        missing = []
        try:
            missing = self.links(links, self.settings.state_dir) if links else []
        except OSError as e:
            self.call_from_thread(self.notify, f"The links failed: {e}", severity="error", markup=False)
            missing = links
        unlinked = {link.path for link in missing}
        for row in rows:
            target = self.settings.targets[row.target]
            needed = {os.path.join(target.data_dir, "cache", *folder.split("/"))
                      for folder in ar.layer_folders(row.row.source)}
            if target.tiles is not None and needed & unlinked:
                self.call_from_thread(self.notify, f"{row.row.title}: no links, not started", severity="error",
                                      markup=False)
                row.starting = 0.0
                continue
            try:
                self.begin(row.row, target, self.settings)
            except OSError as e:
                self.call_from_thread(self.notify, f"{row.row.title}: {e}", severity="error", markup=False)
                row.starting = 0.0

    def action_stop_areas(self):
        rows = [row for row in self.area_rows() if row.ticked and is_live(row.state)]
        if not rows:
            self.notify("Tick the areas downloading first", severity="warning")
            return

        def answered(yes: Optional[bool]):
            if yes:
                ar.stop([row.row.name for row in rows], self.settings)
                for row in rows:
                    row.box.value = False
                self.refresh_summary()
        lines = [row.row.title for row in rows] + ["", "What is downloaded stays; Start resumes."]
        self.push_screen(Confirm(f"Stop {areas_word(len(rows))}?", lines, "Stop"), answered)


def run(settings_path: str) -> int:
    """The window, until it is closed."""
    try:
        settings = ar.load_settings(settings_path)
        rows = ar.rows_of(settings)
    except ar.SettingsError as e:
        print(e, file=sys.stderr)
        return 2
    Downloads(settings, rows).run()
    return 0
