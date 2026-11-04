# Prototypes of the architecture diagrams (2026-11-04)

Three forms of the same slice of the system (a search step by step, where the country layer forks
off, a web job's states), to choose the form of `docs/architecture/`. Decided already: Mermaid in
Markdown is the source of truth; the question is which views stand beside it.

| File | Form | What it is good at |
| --- | --- | --- |
| `a-mermaid.md` | Mermaid blocks in Markdown | GitHub renders it; a diff; a test can check the names against the code |
| `b-explorer.html` | one HTML page: levels, drill-down, a details panel, plain / technical wording | zoom from the whole to one kernel; showing someone on a screen |
| `c-swimlane.md` | sequence diagrams and a table of processes against stores | who writes what, when: web, worker, quick lane, children, the country run |

`b-explorer.html` is written as an artifact page (no `<html>`/`<head>` of its own); a browser opens it
all the same. The HTML versions of A and C were built from the Markdown with a small script of the
session (headings, lists, tables and the Mermaid blocks as `<pre class="mermaid">`).
