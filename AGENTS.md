# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project

**noesis** — Python project. As of the initial commit, no source files, package manager config, or tooling have been set up yet.

## Intended Tooling (inferred from `.gitignore`)

The `.gitignore` was generated with explicit entries for the following tools; prefer these when setting up the project:

- **Linter/formatter**: `ruff` (`.ruff_cache/` is ignored)
- **Type checker**: `mypy` (`.mypy_cache/` is ignored)
- **Test runner**: `pytest` (`.pytest_cache/` is ignored)
- **Package manager**: `uv` is the primary candidate (`uv.lock` comment present); `poetry`, `pdm`, and `pixi` are also accounted for — pick one and commit to it
- **Possible UI framework**: `marimo` or `streamlit` entries exist (`__marimo__/`, `.streamlit/secrets.toml`)

## Commands (to be added once tooling is configured)

Until a `pyproject.toml` or equivalent is committed, there are no standard commands. Once set up, document them here, e.g.:

```bash
uv run pytest                        # run all tests
uv run pytest tests/test_foo.py -k test_name   # run a single test
uv run ruff check .                  # lint
uv run ruff format .                 # format
uv run mypy .                        # type check
```
