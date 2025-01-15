# Xian Contract Linter

[![PyPI version](https://badge.fury.io/py/xian-linter.svg)](https://badge.fury.io/py/xian-linter)
[![Python versions](https://img.shields.io/pypi/pyversions/xian-linter.svg)](https://pypi.org/project/xian-linter/)

A FastAPI service that provides Python code linting specifically designed for Xian smart contracts. It combines PyFlakes for general Python linting with a custom Contracting linter to ensure contract code follows specific rules and patterns.

## Features

- Base64 and Gzip encoded code input support
- Parallel execution of linters
- Deduplication of error messages
- Configurable whitelist patterns for ignored errors
- Standardized error reporting format
- Input validation and size limits

## Installation

You can install the linter in two ways:

### 1. Using pip
```bash
pip install xian-linter
```

### 2. From source
```bash
# Clone the repository
git clone [repository_url]
cd xian-linter

# Install dependencies using Poetry
poetry install
```

## Usage

There are several ways to run the linter server:

### If installed via pip:

1. Using the command-line script:
```bash
xian-linter
```

2. Using Python's module syntax:
```bash
python -m xian_linter
```

3. Using uvicorn directly:
```bash
uvicorn xian_linter.linter:app --host 0.0.0.0 --port 8000
```

### If installed from source using Poetry:
```bash
poetry run python xian_linter/linter.py
```

The server will start on `http://localhost:8000` by default.

### API Endpoints

#### POST /lint_base64
Expects base64-encoded Python code in the request body.

```bash
# Example using curl
base64 < contract.py > contract.py.b64
curl -X POST "http://localhost:8000/lint_base64" --data-binary "@contract.py.b64"
```

#### POST /lint_gzip
Expects gzipped Python code in the request body.

```bash
# Example using curl
gzip -c contract.py > contract.py.gz
curl -X POST "http://localhost:8000/lint_gzip" -H "Content-Type: application/gzip" --data-binary "@contract.py.gz"
```

### Query Parameters

- `whitelist_patterns`: Comma-separated list of patterns to ignore in lint errors. Default patterns are provided for common Contracting keywords.

### Response Format

```json
{
    "success": false,
    "errors": [
        {
            "message": "Error description",
            "severity": "error",
            "position": {
                "line": 3,
                "column": 1
            }
        }
    ]
}
```

The `position` field is optional and may not be present for global errors.
