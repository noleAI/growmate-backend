# Ruff Usage Guide

Ruff is an extremely fast Python linter and code formatter.

## Installation
It's included in `requirements.txt`, so it will be installed when you run:
```bash
pip install -r requirements.txt
```

## Basic Commands

**1. Linting your code**
Check for errors in the current directory:
```bash
ruff check .
```

**2. Auto-fixing lint errors**
Ruff can automatically fix many issues (like unused imports, sorting imports, formatting issues):
```bash
ruff check --fix .
```

**3. Formatting your code**
To reformat your code (similar to Black):
```bash
ruff format .
```

## Configuration
Ruff is configured via the `pyproject.toml` file in the root directory. Feel free to adjust the `[tool.ruff]` block to fit your specific needs.
