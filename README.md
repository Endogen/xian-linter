# Xian Contract Linter

A FastAPI service that provides Python code linting specifically designed for Xian smart contracts. It combines PyFlakes for general Python linting with a custom Contracting linter to ensure contract code follows specific rules and patterns.

## Features

- Base64 and Gzip encoded code input support
- Parallel execution of linters
- Deduplication of error messages
- Configurable whitelist patterns for ignored errors
- Standardized error reporting format
- Input validation and size limits

## Installation

```bash
# Clone the repository
git clone [repository_url]
cd xian-linter

# Install dependencies using Poetry
poetry install
```

## Usage

Start the server:
```bash
poetry run python linter.py
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
    "success": boolean,
    "errors": [
        {
            "message": "Error description",
            "severity": "error",
            "position": {
                "line": number,    # 0-based line number
                "column": number   # 0-based column number
            }
        }
    ]
}
```

The `position` field is optional and may not be present for global errors.
