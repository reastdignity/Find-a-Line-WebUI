"""The instructions Claude Code loads by itself stay small and name files that exist.

CLAUDE.md goes into every request of every session and of every general-purpose subagent; a rule of
`.claude/rules/` only into a session that reads or edits one of the files its `paths` name. By 2026-11-12
CLAUDE.md had grown to 255 KB, about 116 000 tokens in every request: its code map went to docs/code-map/
(loaded by nothing), what must stay in sync and the pitfalls to the rules of their areas. This test keeps
the sizes, and fails when a renamed file leaves a rule that would never load again."""

import os
import re
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(REPO, ".claude", "rules")
CODE_MAP = os.path.join(REPO, "docs", "code-map")

CLAUDE_MD_LINES = 200  # the target Claude Code's documentation gives for a CLAUDE.md
CLAUDE_MD_BYTES = 12_000  # about 5 000 tokens
RULE_BYTES = 16_000  # a rule loaded on demand is cut at 40 000 characters; this keeps one near 7 000 tokens
LINE_CHARS = 400  # short lines merge: the one-line rows of thousands of characters conflicted in every merge


def _text(path):
    with open(path, encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


def _rules():
    return sorted(name[:-3] for name in os.listdir(RULES) if name.endswith(".md"))


def _paths(name):
    """The globs of a rule's `paths` list: the YAML front matter Claude Code reads."""
    lines = _text(os.path.join(RULES, name + ".md")).split("\n")
    assert lines[0] == "---", f"{name}: no front matter, so the rule would load into every session"
    end = lines.index("---", 1)
    assert lines[1] == "paths:", f"{name}: the front matter starts with `paths:`"
    globs = [re.fullmatch(r'  - "([^"]+)"', line) for line in lines[2:end]]
    assert globs and all(globs), f"{name}: every line of `paths` is a quoted glob"
    return [g.group(1) for g in globs]


def _regex(glob):
    """A glob of a rule as a regular expression over a path relative to the repository."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(glob[i]), i + 1
    return re.compile(out)


def _tracked():
    try:
        result = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, encoding="utf-8", check=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return result.stdout.split("\n")


def _table():
    """The rows of CLAUDE.md's table "Where things are": [area, files, rules, code map files]."""
    section = _text(os.path.join(REPO, "CLAUDE.md")).split("## Where things are\n", 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.split("\n") if line.startswith("|")]
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    assert all(len(row) == 4 for row in rows)
    return rows[2:]


def test_claude_md_stays_small():
    text = _text(os.path.join(REPO, "CLAUDE.md"))
    lines = text.split("\n")
    assert len(lines) <= CLAUDE_MD_LINES, "CLAUDE.md is loaded into every request: move the detail to a rule or docs/"
    assert len(text.encode("utf-8")) <= CLAUDE_MD_BYTES, "CLAUDE.md is loaded into every request: keep it short"
    assert max(len(line) for line in lines) <= LINE_CHARS


def test_rules_are_scoped_and_small():
    assert _rules(), "no rules found"
    for name in _rules():
        text = _text(os.path.join(RULES, name + ".md"))
        assert _paths(name)
        assert len(text.encode("utf-8")) <= RULE_BYTES, f"{name}: too long for a rule, split it or move detail to docs/"
        assert max(len(line) for line in text.split("\n")) <= LINE_CHARS, f"{name}: wrap its lines"


def test_rule_paths_name_tracked_files():
    tracked = _tracked()
    for name in _rules():
        for glob in _paths(name):
            pattern = _regex(glob)
            assert any(pattern.fullmatch(path) for path in tracked), (
                f"{name}: `{glob}` matches no tracked file, so nothing would load the rule through it")


def test_claude_md_names_every_rule_and_code_map():
    rows = _table()
    cells = [cell.strip() for row in rows for cell in row[2].split(",")]
    named = {cell for cell in cells if re.fullmatch(r"[a-z0-9-]+", cell)}  # not "the rule of its area"
    assert named == set(_rules()), "CLAUDE.md's table and .claude/rules/ name the same rules"
    maps = {name for row in rows for name in re.findall(r"[a-z0-9-]+\.md", row[3])}
    assert maps == {name for name in os.listdir(CODE_MAP) if name.endswith(".md")}
