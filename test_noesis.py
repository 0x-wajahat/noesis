"""Tests for noesis.py – uses pytest + temporary git repos."""
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

# Make noesis importable from the workspace root
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import noesis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def git(*args, cwd):
    result = subprocess.run(["git"] + list(args), capture_output=True, text=True, cwd=cwd)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def make_repo(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """Init a git repo, write files, make one initial commit. Returns repo path."""
    git("init", cwd=tmp_path)
    git("config", "user.email", "test@test.com", cwd=tmp_path)
    git("config", "user.name", "Test", cwd=tmp_path)
    for name, content in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    git("add", ".", cwd=tmp_path)
    git("commit", "-m", "initial commit", cwd=tmp_path)
    return tmp_path


def add_commit(repo: pathlib.Path, files: dict[str, str], message: str):
    for name, content in files.items():
        p = repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    git("add", ".", cwd=repo)
    git("commit", "-m", message, cwd=repo)


# ---------------------------------------------------------------------------
# collect_refs
# ---------------------------------------------------------------------------

def test_refs_indirect_yaml(tmp_path):
    """A YAML file referencing the symbol produces an indirect ref."""
    repo = make_repo(tmp_path, {
        "target.py": "def my_func():\n    pass\n",
        "config.yaml": "handler: my_func\n",
    })
    refs = noesis.collect_refs(repo, "target.py", "my_func")
    indirect = [r for r in refs if r["type"] == "indirect"]
    assert len(indirect) >= 1
    assert any("config.yaml" in r["source"] for r in indirect)


def test_refs_direct_import(tmp_path):
    """A Python import statement produces a direct ref."""
    repo = make_repo(tmp_path, {
        "target.py": "def my_func():\n    pass\n",
        "caller.py": "from target import my_func\n",
    })
    refs = noesis.collect_refs(repo, "target.py", "my_func")
    direct = [r for r in refs if r["type"] == "direct"]
    assert len(direct) >= 1
    assert any("caller.py" in r["source"] for r in direct)


def test_refs_indirect_string_literal(tmp_path):
    """A symbol inside a Python string literal is indirect."""
    repo = make_repo(tmp_path, {
        "target.py": "def my_func():\n    pass\n",
        "other.py": 'ROUTES = {"path": "my_func"}\n',
    })
    refs = noesis.collect_refs(repo, "target.py", "my_func")
    indirect = [r for r in refs if r["type"] == "indirect"]
    assert len(indirect) >= 1


def test_refs_no_symbol(tmp_path):
    """Empty symbol returns no refs."""
    repo = make_repo(tmp_path, {"target.py": "x = 1\n"})
    assert noesis.collect_refs(repo, "target.py", "") == []


# ---------------------------------------------------------------------------
# collect_history + collect_intent
# ---------------------------------------------------------------------------

def test_history_parses_commits(tmp_path):
    repo = make_repo(tmp_path, {"foo.py": "x = 1\n"})
    add_commit(repo, {"foo.py": "x = 2\n"}, "second change")
    history = noesis.collect_history(repo, "foo.py")
    assert len(history) >= 2
    assert all(k in history[0] for k in ("hash", "date", "author", "message"))


def test_history_empty_for_missing_file(tmp_path):
    repo = make_repo(tmp_path, {"foo.py": "x = 1\n"})
    history = noesis.collect_history(repo, "does_not_exist.py")
    assert history == []


def test_intent_catches_security(tmp_path):
    repo = make_repo(tmp_path, {"auth.py": "pass\n"})
    add_commit(repo, {"auth.py": "# hardened\npass\n"}, "security: harden auth check")
    history = noesis.collect_history(repo, "auth.py")
    flagged = noesis.collect_intent(history)
    assert len(flagged) >= 1
    assert any("security" in c["message"].lower() for c in flagged)


def test_intent_catches_do_not_remove(tmp_path):
    repo = make_repo(tmp_path, {"compat.py": "pass\n"})
    add_commit(repo, {"compat.py": "# kept\npass\n"}, "do not remove this workaround")
    history = noesis.collect_history(repo, "compat.py")
    flagged = noesis.collect_intent(history)
    assert any("do not remove" in c["message"].lower() for c in flagged)


def test_intent_ignores_unrelated(tmp_path):
    repo = make_repo(tmp_path, {"util.py": "pass\n"})
    add_commit(repo, {"util.py": "# v2\npass\n"}, "refactor utility helpers")
    history = noesis.collect_history(repo, "util.py")
    flagged = noesis.collect_intent(history)
    assert flagged == []


# ---------------------------------------------------------------------------
# collect_cochange
# ---------------------------------------------------------------------------

def test_cochange_counts_correctly(tmp_path):
    """A file touched in 2 commits alongside target.py must appear with count=2."""
    repo = make_repo(tmp_path, {
        "target.py": "x = 1\n",
        "sibling.py": "y = 1\n",
    })
    add_commit(repo, {"target.py": "x = 2\n", "sibling.py": "y = 2\n"}, "change both A")
    add_commit(repo, {"target.py": "x = 3\n", "sibling.py": "y = 3\n"}, "change both B")
    history = noesis.collect_history(repo, "target.py")
    cochange = noesis.collect_cochange(repo, "target.py", history)
    assert any(item["file"] == "sibling.py" and item["count"] >= 2 for item in cochange)


def test_cochange_ignores_single_occurrence(tmp_path):
    """A file touched only once with target.py must NOT appear in cochange results."""
    # Start with only target.py so the initial commit does not count as a co-occurrence
    repo = make_repo(tmp_path, {"target.py": "x = 1\n"})
    # Add once.py in a separate commit alongside target.py (one shared commit)
    add_commit(repo, {"target.py": "x = 2\n", "once.py": "z = 1\n"}, "together once")
    # Give target.py another commit that does NOT touch once.py
    add_commit(repo, {"target.py": "x = 3\n"}, "target only")
    history = noesis.collect_history(repo, "target.py")
    cochange = noesis.collect_cochange(repo, "target.py", history)
    assert not any(item["file"] == "once.py" for item in cochange)


# ---------------------------------------------------------------------------
# collect_riskhist
# ---------------------------------------------------------------------------

def test_riskhist_counts_fix_commits(tmp_path):
    repo = make_repo(tmp_path, {"mod.py": "x = 1\n"})
    add_commit(repo, {"mod.py": "x = 2\n"}, "fix null pointer")
    add_commit(repo, {"mod.py": "x = 3\n"}, "bug: off-by-one")
    history = noesis.collect_history(repo, "mod.py")
    rh = noesis.collect_riskhist(history)
    assert rh["count"] >= 2


# ---------------------------------------------------------------------------
# Verdict paths
# ---------------------------------------------------------------------------

def _ledger_with_unknowns(unknowns):
    ledger = {"unknowns": unknowns, "footprint": [], "next_id": len(unknowns) + 1}
    return ledger


def test_verdict_investigate_more():
    """One open critical with 0 attempts -> INVESTIGATE_MORE, exit 1."""
    unknowns = [{"id": "U1", "severity": "critical", "status": "open", "attempts": 0,
                 "category": "intent", "next_steps": "check it"}]
    verdict, code = noesis.compute_verdict(unknowns)
    assert verdict == "INVESTIGATE_MORE"
    assert code == 1


def test_verdict_stop_and_ask():
    """Open critical with attempts >= 3 -> STOP_AND_ASK, exit 2."""
    unknowns = [{"id": "U1", "severity": "critical", "status": "open", "attempts": 3,
                 "category": "intent", "next_steps": "check it"}]
    verdict, code = noesis.compute_verdict(unknowns)
    assert verdict == "STOP_AND_ASK"
    assert code == 2


def test_verdict_proceed_all_resolved():
    """All criticals resolved -> PROCEED, exit 0."""
    unknowns = [
        {"id": "U1", "severity": "critical", "status": "resolved", "attempts": 1,
         "category": "intent", "next_steps": "done"},
        {"id": "U2", "severity": "major", "status": "open", "attempts": 0,
         "category": "no_safety_net", "next_steps": "add tests"},
    ]
    verdict, code = noesis.compute_verdict(unknowns)
    assert verdict == "PROCEED"
    assert code == 0


def test_verdict_proceed_no_unknowns():
    verdict, code = noesis.compute_verdict([])
    assert verdict == "PROCEED"
    assert code == 0


# ---------------------------------------------------------------------------
# infer_source_type
# ---------------------------------------------------------------------------

def test_infer_source_type():
    assert noesis.infer_source_type("src/module.py:42") == "code"
    assert noesis.infer_source_type("a1b2c3d") == "history"
    assert noesis.infer_source_type("test_auth.py:10") == "test"
    assert noesis.infer_source_type("README.md") == "doc"
    assert noesis.infer_source_type("abc123defabc123defabc123defabc123defabcd") == "history"


# ---------------------------------------------------------------------------
# drift detection
# ---------------------------------------------------------------------------

def test_drift_detected(tmp_path):
    """A file modified outside the footprint triggers DRIFT_DETECTED."""
    repo = make_repo(tmp_path, {
        "tracked.py": "x = 1\n",
        "other.py": "y = 1\n",
    })
    # Set footprint to only tracked.py
    ledger = {"unknowns": [], "footprint": ["tracked.py"], "next_id": 1}
    noesis.save_ledger(repo, ledger)

    # Modify other.py in the working tree (unstaged change)
    (repo / "other.py").write_text("y = 999\n")

    result = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).parent / "noesis.py"),
         "drift", "--repo", str(repo)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert "DRIFT_DETECTED" in result.stdout
    assert "other.py" in result.stdout


# ---------------------------------------------------------------------------
# Deduplication: resolved unknowns must not be recreated
# ---------------------------------------------------------------------------

def test_no_duplicate_after_resolved_critical(tmp_path):
    """Re-running check after a critical is RESOLVED must not create a duplicate."""
    repo = make_repo(tmp_path, {
        "auth.py": "pass\n",
    })
    # Commit with an intent keyword so generate_unknowns creates an intent/critical
    add_commit(repo, {"auth.py": "# hardened\npass\n"}, "security: harden auth check")

    history = noesis.collect_history(repo, "auth.py")
    intent_commits = noesis.collect_intent(history)
    assert len(intent_commits) >= 1, "precondition: at least one intent commit expected"

    # First run — ledger is empty, so the intent unknown is created
    ledger = {"unknowns": [], "footprint": [], "next_id": 1}
    noesis.generate_unknowns(ledger, "auth.py", [], intent_commits, [], [], {"count": 0, "commits": []}, history)
    intent_unknowns = [u for u in ledger["unknowns"] if u["category"] == "intent" and u["target_file"] == "auth.py"]
    assert len(intent_unknowns) == 1
    uid = intent_unknowns[0]["id"]

    # Resolve it (simulate two evidence entries with different types)
    intent_unknowns[0]["evidence"] = [
        {"text": "read code", "source": "auth.py:1", "type": "code"},
        {"text": "read commit", "source": "a1b2c3d", "type": "history"},
    ]
    intent_unknowns[0]["status"] = "resolved"

    # Second run — same collectors, same ledger (now with the resolved unknown)
    noesis.generate_unknowns(ledger, "auth.py", [], intent_commits, [], [], {"count": 0, "commits": []}, history)

    all_intent = [u for u in ledger["unknowns"] if u["category"] == "intent" and u["target_file"] == "auth.py"]
    # Must still be exactly one — no duplicate created
    assert len(all_intent) == 1, f"expected 1 intent unknown, got {len(all_intent)}"
    # The original resolved one must still be RESOLVED
    assert all_intent[0]["id"] == uid
    assert all_intent[0]["status"] == "resolved"


def test_no_drift(tmp_path):
    """No changes outside footprint -> NO DRIFT, exit 0."""
    repo = make_repo(tmp_path, {"tracked.py": "x = 1\n"})
    ledger = {"unknowns": [], "footprint": ["tracked.py"], "next_id": 1}
    noesis.save_ledger(repo, ledger)

    # Modify tracked.py (it's in the footprint)
    (repo / "tracked.py").write_text("x = 2\n")

    result = subprocess.run(
        [sys.executable, str(pathlib.Path(__file__).parent / "noesis.py"),
         "drift", "--repo", str(repo)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "NO DRIFT" in result.stdout
