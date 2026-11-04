"""Every script of the repository writes its output in UTF-8, whatever the code page of a redirected stdout
(Windows: cp1250 has no "²", "→" or "ħ"; the quick lane's "sea 0.31 km²" broke every 3D view and profile of a
run with water filling, 4901833): an entry point that prints calls progress.utf8_output(), or, a script on
the standard library alone, reconfigures its streams to UTF-8 itself."""

import ast
import io
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
SKIP = {"node_modules", "local", "__pycache__"}  # and every folder whose name starts with "." (.venv, .claude)


def _scripts():
    for folder, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for name in files:
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def _main_block(tree: ast.Module):
    """The module's `if __name__ == "__main__":` or None."""
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and \
                isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__":
            return node
    return None


def _calls(nodes):
    for node in nodes:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                yield sub


def _name(call: ast.Call) -> str:
    return call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")


def _writes(nodes) -> bool:
    """print(), sys.stdout/stderr.write() or an argparse parser (its --help)."""
    return any(_name(c) in ("print", "ArgumentParser") or
               (isinstance(c.func, ast.Attribute) and c.func.attr == "write" and
                isinstance(c.func.value, ast.Attribute) and c.func.value.attr in ("stdout", "stderr"))
               for c in _calls(nodes))


def _sets_utf8(nodes) -> bool:
    """progress.utf8_output(), or <stream>.reconfigure(encoding="utf-8", ...)."""
    for call in _calls(nodes):
        if _name(call) == "utf8_output":
            return True
        if _name(call) == "reconfigure" and any(k.arg == "encoding" and isinstance(k.value, ast.Constant) and
                                                str(k.value.value).lower().replace("-", "") == "utf8"
                                                for k in call.keywords):
            return True
    return False


def test_entry_points_write_utf8():
    """Each script that prints sets UTF-8 where it starts: in its `if __name__ == "__main__":` block, or
    among its module-level statements when it has none (docs/country-precompute/report/)."""
    missing, checked = [], 0
    for path in _scripts():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        main = _main_block(tree)
        top = [n for n in tree.body if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        where = main.body if main is not None else top
        if not (_writes(tree.body) if main is not None else _writes(top)):
            continue
        checked += 1
        if not _sets_utf8(where):
            missing.append(os.path.relpath(path, REPO))
    assert checked >= 30, checked  # findaline.py, saving.py, tests/regression.py, the tools, ...
    assert not missing, f"entry points without UTF-8 output (progress.utf8_output()): {missing}"


def test_utf8_output(monkeypatch):
    """utf8_output writes UTF-8 to a stream in another encoding and leaves a stream without reconfigure
    alone (None under pythonw, jobs._EventWriter)."""
    import progress
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1250")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", None)
    progress.utf8_output()
    print("sea 0.31 km²", file=stream)
    stream.flush()
    assert raw.getvalue().decode("utf-8").rstrip("\r\n") == "sea 0.31 km²"


def test_a_tool_with_its_output_in_a_code_page():
    """tools/sk_tiles.py --help holds "km²": with a redirected stdout in cp1250 it stopped with a
    UnicodeEncodeError before its entry point set UTF-8."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1250"}
    env.pop("PYTHONUTF8", None)
    result = subprocess.run([sys.executable, os.path.join(REPO, "tools", "sk_tiles.py"), "--help"],
                            capture_output=True, timeout=120, env=env)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert "km²" in result.stdout.decode("utf-8")
