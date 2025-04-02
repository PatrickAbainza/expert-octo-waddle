# Packaging and GitHub Readiness Plan

This document outlines the steps to prepare the `inventory-prototype` project for packaging and uploading to GitHub.

## 1. GitHub Actions CI/CD Workflow

Create a file at `.github/workflows/ci.yml` with the following content:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.8", "3.9", "3.10", "3.11"] # Test against multiple Python versions

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Poetry
        uses: snok/install-poetry@v1
        with:
          virtualenvs-create: true
          virtualenvs-in-project: true

      - name: Load cached venv
        id: cached-poetry-dependencies
        uses: actions/cache@v4
        with:
          path: .venv
          key: venv-${{ runner.os }}-${{ steps.setup-python.outputs.python-version }}-${{ hashFiles('**/poetry.lock') }}

      - name: Install dependencies
        if: steps.cached-poetry-dependencies.outputs.cache-hit != 'true'
        run: poetry install --no-interaction --no-root

      - name: Install project
        run: poetry install --no-interaction

      - name: Run linters (Black, isort)
        run: |
          poetry run black --check .
          poetry run isort --check-only .

      - name: Run type checker (Mypy)
        run: poetry run mypy src

      - name: Run tests with coverage
        run: poetry run pytest --cov=src/inventory_prototype --cov-report=xml

      - name: Upload coverage reports to Codecov
        uses: codecov/codecov-action@v4
        with:
          token: ${{ secrets.CODECOV_TOKEN }} # Optional: Add CODECOV_TOKEN secret to repo settings
          files: ./coverage.xml
          fail_ci_if_error: true
```

**Explanation:**

- **Triggers:** Runs on pushes and pull requests to the `main` branch.
- **Matrix:** Tests across Python versions 3.8, 3.9, 3.10, and 3.11.
- **Setup:** Checks out code, sets up Python, installs Poetry.
- **Caching:** Caches Python dependencies based on `poetry.lock` for faster builds.
- **Install:** Installs dependencies and the project itself using Poetry.
- **Linting:** Runs Black and isort to check code formatting.
- **Type Checking:** Runs Mypy to check static types.
- **Testing:** Runs pytest with coverage reporting.
- **Coverage Upload:** (Optional) Uploads coverage report to Codecov. Requires setting up Codecov and adding a `CODECOV_TOKEN` secret to the GitHub repository settings.

## 2. Enhance `pyproject.toml` Metadata

Update the `[tool.poetry]` section in `pyproject.toml` to include more descriptive metadata:

```diff
 [tool.poetry]
 name = "inventory-prototype"
 version = "0.1.0"
-description = "Simple Inventory API for Chatbot"
+description = "A simple, extensible inventory API system using FastAPI and SQLAlchemy, designed for chatbot integration and rapid prototyping."
 authors = ["Patrick Abainza <your-email@example.com>"] # Add email if desired
 readme = "README.md"
+license = "MIT" # Add license type (assuming MIT based on LICENSE file)
+homepage = "https://github.com/your-username/inventory_chatbot" # Replace with actual URL
+repository = "https://github.com/your-username/inventory_chatbot" # Replace with actual URL
+documentation = "https://github.com/your-username/inventory_chatbot/blob/main/docs/chatbot-api-guide.md" # Link to main docs
+keywords = ["fastapi", "inventory", "api", "chatbot", "prototype", "sqlalchemy"]
+classifiers = [
+    "Development Status :: 3 - Alpha", # Or Beta/Production/Stable as appropriate
+    "Intended Audience :: Developers",
+    "License :: OSI Approved :: MIT License",
+    "Operating System :: OS Independent",
+    "Programming Language :: Python :: 3",
+    "Programming Language :: Python :: 3.8",
+    "Programming Language :: Python :: 3.9",
+    "Programming Language :: Python :: 3.10",
+    "Programming Language :: Python :: 3.11",
+    "Framework :: FastAPI",
+    "Topic :: Software Development :: Libraries :: Application Frameworks",
+    "Topic :: System :: Systems Administration :: Authentication/Directory", # Example, adjust if needed
+]

 [tool.poetry.dependencies]
 python = "^3.8"

```

**Explanation of Additions:**

- **description:** More detailed description.
- **authors:** Added placeholder for email.
- **license:** Specifies the license type (ensure `LICENSE` file matches).
- **homepage, repository, documentation:** Links to the project's online resources (replace placeholders).
- **keywords:** Helps users find the package on PyPI.
- **classifiers:** Standard classifiers for PyPI, indicating project status, audience, license, compatibility, and topics. Adjust `Development Status` as needed.

---

Please review this plan. Let me know if you approve or if you'd like any changes.
