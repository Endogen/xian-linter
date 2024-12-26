import uvicorn
import asyncio
import ast
import base64
import gzip

from io import StringIO
from fastapi import FastAPI, Request
from pyflakes.api import check
from pyflakes.reporter import Reporter
from contracting.compilation.linter import Linter


app = FastAPI()

async def run_pyflakes(code: str) -> list[dict]:
    """
    Runs Pyflakes on 'code' and returns a list of dicts:
      [{ "stage": "pyflakes", "message": <string> }, ...]
    """
    loop = asyncio.get_event_loop()
    stdout = StringIO()
    stderr = StringIO()
    reporter = Reporter(stdout, stderr)

    await loop.run_in_executor(None, check, code, "<string>", reporter)

    combined_output = stdout.getvalue() + stderr.getvalue()
    errors = []
    for line in combined_output.splitlines():
        line = line.strip()
        if line:
            errors.append({"stage": "pyflakes", "message": line})
    return errors

async def run_contracting_linter(code: str) -> list[dict]:
    """
    Runs the Contracting Linter on 'code' and returns a list of dicts:
      [{ "stage": "contracting", "message": <string> }, ...]
    """
    loop = asyncio.get_event_loop()
    errors = []

    try:
        # Parse the code into an AST
        tree = await loop.run_in_executor(None, ast.parse, code)
        # Run the Contracting linter
        linter = Linter()
        violations = await loop.run_in_executor(None, linter.check, tree)
        if violations:
            for v in violations:
                msg = v.strip()
                if msg:
                    errors.append({"stage": "contracting", "message": msg})
    except Exception as ex:
        # If parse fails or anything else
        errors.append({"stage": "contracting", "message": f"Contracting Linter Error: {ex}"})

    return errors


# How to run
# base64 < contract.py > contract.py.b64
# curl -X POST "http://localhost:8000/lint_base64" --data-binary "@contract.py.b64"
@app.post("/lint_base64")
async def lint_base64(request: Request):
    """
    Expects the *raw* request body to be a Base64-encoded Python code.
    We'll:
      1) decode base64
      2) run Pyflakes
      3) run Contracting Linter
      4) combine errors

    Returns JSON:
    {
      "success": <bool>,
      "errors": [
        { "stage": "pyflakes" | "contracting", "message": "..." },
        ...
      ]
    }
    """
    raw_data = await request.body()
    b64_text = raw_data.decode("utf-8", errors="replace")

    # 1) Base64 decode
    try:
        code_bytes = base64.b64decode(b64_text)
        code = code_bytes.decode("utf-8", errors="replace")
    except Exception as ex:
        return {
            "success": False,
            "errors": [
                {"stage": "decode", "message": f"Unable to decode base64: {ex}"}
            ]
        }

    # 2) Run Pyflakes
    pyflakes_issues = await run_pyflakes(code)

    # 3) Run Contracting Linter
    contracting_issues = await run_contracting_linter(code)

    # 4) Combine
    all_issues = pyflakes_issues + contracting_issues
    success = (len(all_issues) == 0)

    return {
        "success": success,
        "errors": all_issues
    }


# How to run
# gzip -c contract.py > contract.py.gz
# curl -X POST "http://localhost:8000/lint_gzip" -H "Content-Type: application/gzip" --data-binary "@contract.py.gz"
@app.post("/lint_gzip")
async def lint_gzip(request: Request):
    """
    Expects the *raw* request body to be gzipped Python code.
    We'll:
      1) decompress
      2) run Pyflakes
      3) run Contracting Linter
      4) combine errors

    Returns same JSON shape as /lint_base64
    """
    raw_data = await request.body()

    # 1) Decompress
    try:
        code_bytes = gzip.decompress(raw_data)
        code = code_bytes.decode("utf-8", errors="replace")
    except Exception as ex:
        return {
            "success": False,
            "errors": [
                {"stage": "decode", "message": f"Unable to decompress Gzip: {ex}"}
            ]
        }

    # 2) Run Pyflakes
    pyflakes_issues = await run_pyflakes(code)

    # 3) Run Contracting Linter
    contracting_issues = await run_contracting_linter(code)

    # 4) Combine
    all_issues = pyflakes_issues + contracting_issues
    success = (len(all_issues) == 0)

    return {
        "success": success,
        "errors": all_issues
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
