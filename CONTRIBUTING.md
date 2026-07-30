# Contributing to devin-orchestrator

## Getting started

```bash
git clone https://github.com/emiltsoi/devin-orchestrator.git
cd devin-orchestrator
pip install -r requirements.txt -r requirements-dev.txt
```

## Running tests

```bash
python -m pytest tests -q
```

Tests are configured to work from any directory (`tests/conftest.py` adds the repo root to `sys.path`).

## Lint and type check

```bash
ruff check .
ruff format --check .
python -m mypy
```

## Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

## Building and installing locally

```bash
python -m build --wheel
pip install dist/*.whl --force-reinstall
```

## Deployment

For the public one-click path, see [DEPLOY.md](DEPLOY.md).

## Releasing

1. Update the version in `pyproject.toml` and `devin_orchestrator/__init__.py`.
2. Tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
3. Push: `git push && git push origin vX.Y.Z`
4. The [release workflow](.github/workflows/release.yml) will build, test, publish to PyPI, and create a GitHub release.
