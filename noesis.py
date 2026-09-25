#!/usr/bin/env python3
"""Noesis – pre-flight knowledge checker for coding agents."""
import argparse
import collections
import json
import os
import pathlib
import re
import subprocess
import sys

# -- Ledger helpers ----------------------------------------------------------
LEDGER_DIR = ".noesis"
LEDGER_FILE = "ledger.json"
_DEFAULT_LEDGER = {"unknowns": [], "footprint": [], "next_id": 1}


def load_ledger(repo: pathlib.Path) -> dict:
    path = repo / LEDGER_DIR / LEDGER_FILE
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return dict(_DEFAULT_LEDGER)


def save_ledger(repo: pathlib.Path, ledger: dict):
    d = repo / LEDGER_DIR
    d.mkdir(exist_ok=True)
    tmp = d / (LEDGER_FILE + ".tmp")
    with open(tmp, "w") as f:
        json.dump(ledger, f, indent=2)
    os.replace(tmp, d / LEDGER_FILE)


def next_unknown_id(ledger: dict) -> str:
    uid = f"U{ledger['next_id']}"
    ledger["next_id"] += 1
    return uid


# -- Evidence collectors -----------------------------------------------------
_INTENT_PATTERN = re.compile(
    r"legal|regulation|compliance|required|workaround|hotfix|"
    r"do not remove|don't remove|security|must",
    re.IGNORECASE,
)
_RISKHIST_PATTERN = re.compile(r"fix|revert|bug", re.IGNORECASE)
_EXTS = {".py", ".yaml", ".yml", ".json", ".ini", ".toml", ".md"}
_STR_LIT = re.compile(r"""(["']).*?\1""")


def collect_refs(repo: pathlib.Path, target_file: str, symbol: str) -> list:
    if not symbol:
        return []
    results = []
    skip = {
        str((repo / ".git").resolve()),
        str((repo / LEDGER_DIR).resolve()),
        str((repo / target_file).resolve()),
    }
    for root, dirs, files in os.walk(repo):
        dirs[:] = [
            d for d in dirs
            if str(pathlib.Path(root, d).resolve()) not in skip
        ]
        for fname in files:
            p = pathlib.Path(root, fname)
            if p.suffix not in _EXTS:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(p.relative_to(repo))
            if p.suffix == ".py":
                for i, line in enumerate(text.splitlines(), 1):
                    if symbol not in line:
                        continue
                    stripped = line.strip()
                    # direct: import statement
                    if re.match(r"^\s*(from\s+\S+\s+)?import\b", line):
                        results.append({
                            "type": "direct",
                            "claim": f"Import of '{symbol}' in {rel}:{i}",
                            "source": f"{rel}:{i}",
                        })
                    # direct: call or attribute access outside a string literal
                    elif re.search(rf"\b{re.escape(symbol)}\s*[\(\.]", line) and not _STR_LIT.search(stripped):
                        results.append({
                            "type": "direct",
                            "claim": f"Call/use of '{symbol}' in {rel}:{i}",
                            "source": f"{rel}:{i}",
                        })
                    # indirect: inside a string literal
                    elif _STR_LIT.search(stripped) and symbol in stripped:
                        results.append({
                            "type": "indirect",
                            "claim": f"String reference to '{symbol}' in {rel}:{i}",
                            "source": f"{rel}:{i}",
                        })
            else:
                for i, line in enumerate(text.splitlines(), 1):
                    if symbol in line:
                        results.append({
                            "type": "indirect",
                            "claim": f"Reference to '{symbol}' in {rel}:{i}",
                            "source": f"{rel}:{i}",
                        })
    return results


def collect_history(repo: pathlib.Path, target_file: str) -> list:
    result = subprocess.run(
        ["git", "log", "--follow", "--pretty=format:%H|%ad|%an|%s", "--", target_file],
        capture_output=True, text=True, cwd=repo,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []
    entries = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            entries.append({"hash": parts[0], "date": parts[1], "author": parts[2], "message": parts[3]})
    return entries


def collect_intent(history: list) -> list:
    return [c for c in history if _INTENT_PATTERN.search(c.get("message", ""))]


def collect_cochange(repo: pathlib.Path, target_file: str, history: list) -> list:
    counter: collections.Counter = collections.Counter()
    for entry in history:
        h = entry["hash"]
        r = subprocess.run(
            ["git", "show", "--name-only", "--pretty=format:", h],
            capture_output=True, text=True, cwd=repo,
        )
        if r.returncode != 0:
            continue
        files = [f for f in r.stdout.strip().splitlines() if f and f != target_file]
        for f in files:
            counter[f] += 1
    return [{"file": f, "count": c} for f, c in counter.most_common() if c >= 2]


def collect_tests(repo: pathlib.Path, target_file: str, symbol: str) -> list:
    module_name = pathlib.Path(target_file).stem
    results = []
    for root, _dirs, files in os.walk(repo):
        for fname in files:
            if not (fname.startswith("test_") or fname.endswith("_test.py")):
                continue
            p = pathlib.Path(root, fname)
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(p.relative_to(repo))
            for i, line in enumerate(text.splitlines(), 1):
                if module_name in line or (symbol and symbol in line):
                    results.append({"file": rel, "line": i, "snippet": line.strip()})
    return results


def collect_riskhist(history: list) -> dict:
    matched = [c for c in history if _RISKHIST_PATTERN.search(c.get("message", ""))]
    return {"count": len(matched), "commits": [c["hash"] for c in matched]}


# -- Unknown generation ------------------------------------------------------
def _unknown_exists(ledger: dict, category: str, target_file: str) -> bool:
    return any(
        u["status"] == "open" and u["category"] == category and u.get("target_file") == target_file
        for u in ledger["unknowns"]
    )


def _add_unknown(ledger, category, severity, next_steps, target_file):
    if _unknown_exists(ledger, category, target_file):
        return
    ledger["unknowns"].append({
        "id": next_unknown_id(ledger),
        "category": category,
        "severity": severity,
        "status": "open",
        "evidence": [],
        "attempts": 0,
        "next_steps": next_steps,
        "target_file": target_file,
    })


def generate_unknowns(ledger, target_file, refs, intent_commits, cochange_files, tests_found, riskhist, history):
    # 1. indirect refs -> hidden_caller
    for ref in refs:
        if ref["type"] == "indirect":
            src = ref["source"]
            cat = "hidden_caller"
            if not any(
                u["status"] == "open" and u["category"] == cat and u.get("target_file") == target_file
                and src in u["next_steps"]
                for u in ledger["unknowns"]
            ):
                if not _unknown_exists(ledger, cat, target_file):
                    _add_unknown(
                        ledger, cat, "critical",
                        f"Check {src} to see how it's called and whether removing/changing the symbol breaks it.",
                        target_file,
                    )

    # 2. intent-flagged commits -> intent / critical
    for commit in intent_commits:
        h = commit["hash"]
        cat = "intent"
        if not any(
            u["status"] == "open" and u["category"] == cat and u.get("target_file") == target_file
            and h in u["next_steps"]
            for u in ledger["unknowns"]
        ):
            if not _unknown_exists(ledger, cat, target_file):
                _add_unknown(
                    ledger, cat, "critical",
                    f"Read commit {h} in full and the surrounding code to understand why it's written this way.",
                    target_file,
                )

    # 3. cochange files -> coupling / major
    for item in cochange_files:
        f = item["file"]
        cat = "coupling"
        if not any(
            u["status"] == "open" and u["category"] == cat and u.get("target_file") == target_file
            and f in u["next_steps"]
            for u in ledger["unknowns"]
        ):
            ledger["unknowns"].append({
                "id": next_unknown_id(ledger),
                "category": cat,
                "severity": "major",
                "status": "open",
                "evidence": [],
                "attempts": 0,
                "next_steps": f"Review {f} for duplicated or dependent logic before finalizing the change.",
                "target_file": target_file,
            })

    # 4. no tests -> no_safety_net / major
    if not tests_found:
        _add_unknown(
            ledger, "no_safety_net", "major",
            "No test covers this. Consider writing one before changing it, or proceed with extra caution.",
            target_file,
        )

    # 5. riskhist count >= 2 -> fragile_area / minor
    if riskhist["count"] >= 2:
        _add_unknown(
            ledger, "fragile_area", "minor",
            "This file has a history of bugs/reverts. Double check the change doesn't repeat a past issue.",
            target_file,
        )

    # 6. no history -> no_history / major
    if not history:
        _add_unknown(
            ledger, "no_history", "major",
            "No git history available; treat this file as high-uncertainty.",
            target_file,
        )

    return ledger


# -- Verdict + Report --------------------------------------------------------
_SEP = "=" * 64
_SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}


def compute_verdict(unknowns: list) -> tuple:
    criticals = [u for u in unknowns if u["severity"] == "critical" and u["status"] == "open"]
    if not criticals:
        return "PROCEED", 0
    if any(u["attempts"] >= 3 for u in criticals):
        return "STOP_AND_ASK", 2
    return "INVESTIGATE_MORE", 1


def print_report(change: str, target: str, unknowns: list, verdict: str):
    print(_SEP)
    print("NOESIS REPORT")
    print(f"Change requested: {change}")
    print(f"Target: {target}")
    print(_SEP)
    print()
    print(f"VERDICT: {verdict}")
    print()
    print("UNKNOWNS (critical first, then major, then minor):")
    sorted_u = sorted(unknowns, key=lambda u: _SEVERITY_ORDER.get(u["severity"], 9))
    for u in sorted_u:
        ev = u["evidence"]
        ev_str = "(none)" if not ev else "; ".join(f"{e['type']}: {e['source']}" for e in ev)
        print(f"[{u['id']}] {u['severity'].upper()} - {u['category']} - {u['status'].upper()}")
        if u.get("target_file"):
            print(f"  File: {u['target_file']}")
        print(f"  Next step: {u['next_steps']}")
        print(f"  Evidence so far: {ev_str}")
        print()
    if verdict == "PROCEED":
        open_guards = [u for u in sorted_u if u["status"] == "open" and u["severity"] in ("major", "minor")]
        if open_guards:
            print("GUARDRAILS (proceed but watch these):")
            for u in open_guards:
                print(f"  [{u['id']}] {u['severity'].upper()} - {u['category']} - {u['next_steps']}")
            print()
    if verdict == "STOP_AND_ASK":
        stuck = [u for u in unknowns if u["severity"] == "critical" and u["status"] == "open" and u["attempts"] >= 3]
        print("QUESTIONS FOR A HUMAN:")
        for i, u in enumerate(stuck, 1):
            q = u["next_steps"].rstrip(".")
            print(f"  {i}. {q}?")
        print()
    print(_SEP)


# -- Footprint ---------------------------------------------------------------
def _update_footprint(ledger, target_file, refs, cochange_files):
    fp = set(ledger.get("footprint", []))
    fp.add(target_file)
    for r in refs:
        if r["type"] == "indirect":
            fp.add(r["source"].split(":")[0])
    for item in cochange_files:
        resolved = [u for u in ledger["unknowns"]
                    if u["category"] == "coupling" and u["status"] == "resolved"
                    and item["file"] in u["next_steps"]]
        if resolved:
            fp.add(item["file"])
    ledger["footprint"] = sorted(fp)


# -- Command handlers --------------------------------------------------------
def cmd_check(args):
    repo = pathlib.Path(args.repo).resolve()
    target = args.target
    target_file, _, symbol = target.partition(":")
    change = args.change

    history = collect_history(repo, target_file)
    refs = collect_refs(repo, target_file, symbol)
    intent_commits = collect_intent(history)
    cochange_files = collect_cochange(repo, target_file, history)
    tests_found = collect_tests(repo, target_file, symbol)
    riskhist = collect_riskhist(history)

    ledger = load_ledger(repo)
    generate_unknowns(ledger, target_file, refs, intent_commits, cochange_files, tests_found, riskhist, history)
    _update_footprint(ledger, target_file, refs, cochange_files)
    save_ledger(repo, ledger)

    verdict, code = compute_verdict(ledger["unknowns"])
    print_report(change, target, ledger["unknowns"], verdict)
    sys.exit(code)


def infer_source_type(source: str) -> str:
    if source.endswith(".md"):
        return "doc"
    if "test" in source:
        return "test"
    if re.match(r"^[0-9a-fA-F]{7,40}$", source):
        return "history"
    if re.search(r".+:\d+$", source):
        return "code"
    return "code"


def cmd_resolve(args):
    uid = args.unknown_id
    repo = pathlib.Path(getattr(args, "repo", None) or ".").resolve()
    ledger = load_ledger(repo)
    unknown = next((u for u in ledger["unknowns"] if u["id"] == uid), None)
    if unknown is None:
        print(f"Unknown {uid} not found in ledger.")
        sys.exit(1)

    etype = infer_source_type(args.source)
    unknown["evidence"].append({"text": args.evidence, "source": args.source, "type": etype})

    severity = unknown["severity"]
    ev = unknown["evidence"]
    resolved = False
    if severity == "critical":
        types_present = {e["type"] for e in ev}
        if len(types_present) >= 2:
            resolved = True
    else:
        resolved = True

    if resolved:
        unknown["status"] = "resolved"
        print(f"{uid} marked RESOLVED.")
    else:
        unknown["attempts"] += 1
        types_present = {e["type"] for e in ev}
        print(
            f"{uid} still OPEN (attempts={unknown['attempts']}). "
            f"Critical unknowns need 2+ evidence entries with different types. "
            f"Types so far: {', '.join(types_present)}."
        )

    save_ledger(repo, ledger)


def cmd_add_unknown(args):
    repo = pathlib.Path(getattr(args, "repo", None) or ".").resolve()
    ledger = load_ledger(repo)
    ledger["unknowns"].append({
        "id": next_unknown_id(ledger),
        "category": args.category,
        "severity": args.severity,
        "status": "open",
        "evidence": [],
        "attempts": 0,
        "next_steps": args.text,
        "target_file": getattr(args, "target_file", None),
    })
    save_ledger(repo, ledger)
    print(f"Unknown added: U{ledger['next_id'] - 1}")


def cmd_drift(args):
    repo = pathlib.Path(args.repo).resolve()
    ledger = load_ledger(repo)
    footprint = set(ledger.get("footprint", []))

    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, cwd=repo,
    )
    if result.returncode != 0:
        print("git diff failed:", result.stderr.strip())
        sys.exit(2)

    changed = {f for f in result.stdout.strip().splitlines() if f}
    extra = changed - footprint
    if extra:
        print("DRIFT_DETECTED")
        for f in sorted(extra):
            print(f"  {f}")
        sys.exit(2)
    else:
        print("NO DRIFT")
        sys.exit(0)


# -- CLI entry point ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(prog="noesis", description="Pre-flight knowledge checker for coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    # check
    p_check = sub.add_parser("check", help="Assess agent knowledge before a change.")
    p_check.add_argument("--repo", required=True, metavar="PATH")
    p_check.add_argument("--change", required=True, metavar="TEXT")
    p_check.add_argument("--target", required=True, metavar="FILE[:SYMBOL]")

    # resolve
    p_res = sub.add_parser("resolve", help="Resolve an unknown by providing evidence.")
    p_res.add_argument("unknown_id", metavar="UNKNOWN_ID")
    p_res.add_argument("--evidence", required=True, metavar="TEXT")
    p_res.add_argument("--source", required=True, metavar="FILE:LINE_OR_HASH")
    p_res.add_argument("--repo", default=None, metavar="PATH")

    # add-unknown
    p_add = sub.add_parser("add-unknown", help="Manually add an unknown.")
    p_add.add_argument("--category", required=True, metavar="TEXT")
    p_add.add_argument("--severity", required=True, choices=["critical", "major", "minor"])
    p_add.add_argument("--text", required=True, metavar="TEXT")
    p_add.add_argument("--repo", default=None, metavar="PATH")

    # drift
    p_drift = sub.add_parser("drift", help="Detect out-of-footprint changes.")
    p_drift.add_argument("--repo", required=True, metavar="PATH")

    args = parser.parse_args()
    dispatch = {
        "check": cmd_check,
        "resolve": cmd_resolve,
        "add-unknown": cmd_add_unknown,
        "drift": cmd_drift,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
