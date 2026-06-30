# Contributing to svg2fcm

Thanks for your interest in contributing! This document covers everything
needed to get a working dev environment, make a change, and submit it.

## Quick start

```bash
git clone https://github.com/Guernik/svg2fcm
cd svg2fcm
just install         # creates .venv and installs everything
just hooks-install   # activate pre-commit git hooks (one-time, per clone)
just check           # ruff + mypy --strict + pytest
```

`just hooks-install` wires up [pre-commit](https://pre-commit.com/) so
that ruff, ruff-format, mypy, and the standard hygiene checks run
automatically on `git commit`. The same hooks run in CI via
`pre-commit run --all-files`, so passing locally is a strong signal
that CI will be green. Run `just hooks-run` to execute every hook
against every tracked file on demand.

If you don't have [`just`](https://just.systems/) installed, the
[`justfile`](justfile) is short enough to read and run the commands
manually.

## Development workflow

1. Create a branch from `main`.
2. Make your change. Keep diffs focused — one logical change per PR.
3. Run `just check` until green. CI runs the same gate on macOS, Linux,
   and Windows × Python 3.10/3.11/3.12, so passing locally is a good
   indicator.
4. Update `CHANGELOG.md` under `[Unreleased]` if the change is
   user-visible.
5. Open a PR. The template lists the checklist.

### What the gate enforces

* `ruff check src tests` — lint, including pydocstyle conventions.
* `ruff format --check src tests` — formatting.
* `mypy src tests` — type checking in strict mode.
* `pytest --cov` — full test suite with coverage.

Run `just fmt` to apply ruff's auto-fixes before pushing.

## Coding conventions

* **Type hints everywhere.** `from __future__ import annotations` at the
  top of every module. `mypy --strict` is the source of truth.
* **Docstrings.** Public functions and classes get Google-style
  docstrings (PEP 257). Module-level docstrings on every file.
* **No magic numbers.** Header constants, FCM bitflags, and unit
  conversions all live in `svg2fcm.fcm.constants`. If you need a new
  number, add it there with a comment explaining where it came from.
* **Errors raise `Svg2FcmError` subclasses** (see
  `src/svg2fcm/exceptions.py`). The CLI catches the base class. Don't
  let third-party exceptions bubble up unwrapped from library code.
* **Logging, not `print`.** Library code uses `logging.getLogger(__name__)`.
  Only the CLI's final user-facing line uses `print`.

## Tests

Tests live under `tests/`:

* `tests/unit/` — fast unit tests of single modules.
* `tests/integration/` — end-to-end SVG → FCM → parse round-trip checks.
* `tests/fixtures/` — sample `.fcm` files. **Every fixture is byte-exact
  round-tripped by `tests/integration/test_round_trip.py`**: any change
  that loses information will fail that test.

When you add a new format feature or fix a parser bug, drop a fixture
into `tests/fixtures/` so the round-trip property covers it.

## Format spec changes

If you discover new fields or fix our understanding of existing ones:

1. Update `docs/FCM_FORMAT.md` first — that's the source of truth.
2. Reflect the change in `src/svg2fcm/fcm/constants.py` and the model.
3. Add a sample fixture (or two) under `tests/fixtures/` that exercises
   the change.
4. The round-trip test will fail if the encoder/parser disagree.

## Reporting bugs

Open an issue using the bug report template. The single most useful
thing you can include is a **minimal SVG that reproduces the problem**
and the `svg2fcm -vv` output. Attach the generated `.fcm` if Canvas
Workspace or the machine misbehaves with it.

## Licensing of contributions

By submitting a pull request, patch, or other contribution to this
project, you agree that your contribution is licensed under the
[Mozilla Public License 2.0](LICENSE) — the same license as the project
itself (**inbound = outbound**). You also confirm that you have the
right to submit the work under that license: it is either your own
original work, or it is otherwise compatible with MPL-2.0 and properly
attributed.

If you include code, sample SVGs, or other assets that are not your own
work, please call that out in the PR description and include the
upstream license so we can verify compatibility before merging.

## Releasing

(For maintainers.)

1. Bump the version in **both** `pyproject.toml` and
   `src/svg2fcm/__init__.py` (they must match — the release workflow
   verifies this).
2. Move `CHANGELOG.md`'s `[Unreleased]` section under a new dated
   release header, e.g. `## [0.1.1] — 2026-05-19`. The release workflow
   extracts the body of this section as the GitHub Release notes, so
   the heading text must match the tag's version exactly.
3. Commit the bump and push to `main`.
4. Tag the commit and push the tag:

   ```bash
   git tag v0.1.1
   git push origin v0.1.1
   ```

5. The `release` workflow (`.github/workflows/release.yml`) fires on
   the `v*` tag, builds the wheel, sdist, and Inkscape extension zip,
   then publishes a GitHub Release at
   `https://github.com/Guernik/svg2fcm/releases/tag/v0.1.1` with
   those three artifacts attached.

PyPI publishing is not wired up yet.
