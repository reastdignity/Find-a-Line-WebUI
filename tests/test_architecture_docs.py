"""The architecture diagrams of docs/architecture/ against the code.

Every file holds Mermaid blocks of the kinds GitHub renders and a table "Where in the code" whose
rows name files of the repository and names in them; a renamed function, a moved file or a typo
in a diagram fails here. The prototypes of docs/architecture/prototypes/ are not checked: they
are kept as they were when the form was chosen.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "architecture"
FILES = sorted(p for p in DOCS.glob("*.md") if p.name != "README.md")  # the index has no diagram
KINDS = ("flowchart", "sequenceDiagram", "stateDiagram-v2")
FORBIDDEN = ("%%{init", "architecture-beta", "block-beta", "C4Context", "\nclick ", "\n    click ")
CLASSDEF = {
    "step": "classDef step fill:#e1e8fa,stroke:#2350c8,color:#17201c",
    "q": "classDef q fill:#fbefd9,stroke:#995500,color:#17201c",
    "file": "classDef file fill:#e0f1e6,stroke:#1d7a47,color:#17201c",
    "actor": "classDef actor fill:#e9eee9,stroke:#45524b,color:#17201c",
}


def blocks(text: str):
    return re.findall(r"```mermaid\n(.*?)```", text, re.S)


def table(text: str, heading: str):
    """The rows of the table under a heading: lists of cells."""
    m = re.search(r"^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, f"no section '{heading}'"
    rows = [line for line in m.group(1).splitlines() if line.startswith("|")]
    assert len(rows) >= 3, f"'{heading}' has no rows"
    return [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows[2:]]


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_mermaid_blocks_as_github_renders_them(path):
    text = path.read_text(encoding="utf-8")
    found = blocks(text)
    assert found, f"{path.name} has no Mermaid block"
    for block in found:
        kind = block.split()[0]
        assert kind in KINDS, f"{path.name}: a {kind} diagram; GitHub renders {KINDS}"
        for bad in FORBIDDEN:
            assert bad not in block, f"{path.name}: {bad.strip()!r} in a diagram"
        if kind == "flowchart":
            lines = [line.strip() for line in block.splitlines()]
            for name, line in CLASSDEF.items():
                assert line in lines, f"{path.name}: a flowchart without the classDef '{name}' line"
            for line in lines:
                if line.startswith("style "):
                    raise AssertionError(f"{path.name}: a 'style' line; colour by class")
    assert text.count("```mermaid") == text.count("```") // 2 or "```\n" not in text.replace("```mermaid", ""), \
        f"{path.name}: a fenced block that is not Mermaid (keep the files to Mermaid and tables)"


def names_of(cell: str):
    """The names in backticks of a table cell that can be looked for as one word."""
    out = []
    for token in re.findall(r"`([^`]+)`", cell):
        token = token.strip()
        if any(c in token for c in " /<>(=-+*'\""):
            continue
        out.append(token)
    return out


def present(name: str, text: str) -> bool:
    """Whether a name of a table cell is in the text: as it is, or a dotted name (`Jobs.add`,
    `search.Paths`) by its last part."""
    def word(s, before=r"(?<![\w.])"):
        return re.search(before + re.escape(s) + r"(?![\w])", text) is not None
    if word(name):
        return True
    # An attribute or a method: its last part after a dot (`self.listeners`, `def add`)
    return "." in name and re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)+", name) is not None and word(name.split(".")[-1], r"(?<!\w)")


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_where_in_the_code_names_exist(path):
    text = path.read_text(encoding="utf-8")
    missing = []
    for row in table(text, "Where in the code"):
        assert len(row) == 3, f"{path.name}: a row of {len(row)} cells: {row}"
        files = re.findall(r"\]\(([^)]+)\)", row[1])
        assert files, f"{path.name}: a row without a file link: {row[0]}"
        texts = []
        for f in files:
            target = (DOCS / f).resolve()
            assert target.exists(), f"{path.name}: {f} does not exist (row {row[0]!r})"
            if target.is_dir():
                texts.extend(p.read_text(encoding="utf-8", errors="replace")
                             for p in target.rglob("*") if p.suffix in (".py", ".ts", ".tsx", ".sh", ".conf", ".yaml", ".json", ".md", ".mjs", ".css"))
            else:
                texts.append(target.read_text(encoding="utf-8", errors="replace"))
        joined = "\n".join(texts)
        for name in names_of(row[2]):
            if not present(name, joined):
                missing.append(f"{row[0]!r}: {name} not in {', '.join(files)}")
    assert not missing, f"{path.name}:\n  " + "\n  ".join(missing)


def test_index_lists_every_file():
    index = (DOCS / "README.md").read_text(encoding="utf-8")
    for p in FILES:
        if p.name != "README.md":
            assert f"({p.name})" in index, f"README.md does not link {p.name}"
