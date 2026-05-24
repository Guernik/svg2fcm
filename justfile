# svg2fcm — common development tasks.
#
# Run `just` (or `just --list`) to see all recipes.
# Path to the virtual environment used for everything.

venv := ".venv"
python := venv / "bin" / "python"
pip := venv / "bin" / "pip"

# Default: show the recipe list.
[private]
default:
    @just --list

# Create the venv and install the project in editable mode with dev extras.
install:
    test -d {{ venv }} || python3 -m venv {{ venv }}
    {{ pip }} install --quiet --upgrade pip
    {{ pip }} install --quiet -e ".[dev]"

# Run lint, type-check, and tests — the full pre-commit gate.
check: lint typecheck test

# Install the pre-commit git hooks into .git/hooks/.
hooks-install:
    {{ venv }}/bin/pre-commit install
    @echo "Installed. Hooks will now run on every git commit."

# Run all pre-commit hooks against every tracked file (CI parity).
hooks-run:
    {{ venv }}/bin/pre-commit run --all-files

# Bump pinned hook versions in .pre-commit-config.yaml.
hooks-update:
    {{ venv }}/bin/pre-commit autoupdate

# Lint and format-check with ruff (no autofix; run `just fmt` to apply).
lint:
    {{ venv }}/bin/ruff check src tests
    {{ venv }}/bin/ruff format --check src tests

# Apply ruff autofixes and formatting.
fmt:
    {{ venv }}/bin/ruff check --fix src tests
    {{ venv }}/bin/ruff format src tests

# Type-check with mypy in strict mode.
typecheck:
    {{ venv }}/bin/mypy src tests

# Run the test suite with coverage.
test:
    {{ venv }}/bin/pytest --cov

# Build the wheel and sdist into dist/.
build:
    {{ python }} -m build

# Build the Inkscape extension zip into dist/.
package-inkscape:
    {{ python }} scripts/build_inkscape_ext.py

# Install `svg2fcm` system-wide via pipx (isolated venv on PATH).
# Requires pipx — install once with `brew install pipx` (macOS) or
# `python3 -m pip install --user pipx` (Linux/Windows), then run

# `pipx ensurepath` so its bin dir is on $PATH.
install-cli:
    @command -v pipx >/dev/null || { echo "pipx not found. Install with: brew install pipx  (or: python3 -m pip install --user pipx && python3 -m pipx ensurepath)"; exit 1; }
    pipx install --python python3.13 --force '.[vpype]'
    @echo "Installed. Try: svg2fcm --version"

# Uninstall the system-wide `svg2fcm` command.
uninstall-cli:
    pipx uninstall svg2fcm

# Install shell completions for the current user. Auto-detects fish; for

# bash/zsh prints the snippet to add to the rc file. Idempotent.
completions-install:
    #!/usr/bin/env bash
    set -euo pipefail
    repo="$(pwd)"
    fish_dir="${HOME}/.config/fish/completions"
    if [ -d "${HOME}/.config/fish" ]; then
        mkdir -p "${fish_dir}"
        cp "${repo}/completions/svg2fcm.fish" "${fish_dir}/svg2fcm.fish"
        echo "✓ fish: installed at ${fish_dir}/svg2fcm.fish (open a new shell)"
    else
        echo "  fish: ~/.config/fish not found, skipping. To install manually:"
        echo "       cp completions/svg2fcm.fish ~/.config/fish/completions/"
    fi
    echo ""
    echo "  bash: add to ~/.bashrc:"
    echo "       . \"${repo}/completions/svg2fcm.bash\""
    echo ""
    echo "  zsh:  add ${repo}/completions to your \$fpath, e.g. in ~/.zshrc:"
    echo "       fpath=(\"${repo}/completions\" \$fpath)"
    echo "       autoload -Uz compinit && compinit"

# Remove caches, build artifacts, and the venv.
clean:
    rm -rf build dist *.egg-info
    rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
    rm -f .coverage coverage.xml
    find . -type d -name __pycache__ -prune -exec rm -rf {} +

# Full reset: clean *and* drop the venv.
distclean: clean
    rm -rf {{ venv }}
