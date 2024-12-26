import uvicorn
import asyncio
import ast
import base64
import gzip
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, List, Set
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from io import StringIO
from pyflakes.api import check
from pyflakes.reporter import Reporter
from contracting.compilation.linter import Linter


class Settings:
    """Simple settings class"""

    def __init__(self):
        self.MAX_CODE_SIZE: int = 1_000_000  # 1MB
        self.CACHE_SIZE: int = 100
        self.DEFAULT_WHITELIST_PATTERNS: frozenset = frozenset({
            'export', 'construct', 'Hash', 'Variable', 'ctx', 'now',
            'random', 'ForeignHash', 'ForeignVariable', 'block_num',
            'block_hash', 'importlib', 'hashlib', 'datetime', 'crypto',
            'decimal', 'Any'
        })


settings = Settings()


class LintingException(Exception):
    """Custom exception for linting errors"""
    pass


@dataclass(slots=True)
class Position:
    """Represents a position in the source code"""
    line: int  # 0-based line number
    column: int  # 0-based column number


@dataclass(slots=True)
class LintError:
    """Standardized lint error format"""
    message: str
    severity: str = "error"
    position: Optional[Position] = None

    def to_dict(self) -> dict:
        result = {
            "message": self.message,
            "severity": self.severity
        }
        if self.position is not None:
            result["position"] = {
                "line": self.position.line,
                "column": self.position.column
            }
        return result


class Position_Model(BaseModel):
    line: int
    column: int


class LintError_Model(BaseModel):
    message: str
    severity: str
    position: Optional[Position_Model] = None


class LintResponse(BaseModel):
    success: bool
    errors: List[LintError_Model]


app = FastAPI()

# Compile regex patterns once
PYFLAKES_PATTERN = re.compile(r'<string>:(\d+):(\d+):\s*(.+)')
CONTRACTING_PATTERN = re.compile(r'Line (\d+):\s*(.+)')


def standardize_error_message(message: str) -> str:
    """Standardize error message by removing extra location information."""
    # Remove (<unknown>, line X) pattern from the end
    location_pattern = r'\s*\(<unknown>,\s*line\s*\d+\)$'
    message = re.sub(location_pattern, '', message)
    return message


def is_duplicate_error(error1: LintError, error2: LintError) -> bool:
    """Check if two errors are duplicates by comparing standardized messages and positions."""
    msg1 = standardize_error_message(error1.message)
    msg2 = standardize_error_message(error2.message)

    # If messages are different, they're not duplicates
    if msg1 != msg2:
        return False

    # If one has position and other doesn't, they're not duplicates
    if bool(error1.position) != bool(error2.position):
        return False

    # If both have positions, compare them
    if error1.position and error2.position:
        return (error1.position.line == error2.position.line and
                error1.position.column == error2.position.column)

    # If neither has position, compare just messages
    return True


def deduplicate_errors(errors: List[LintError]) -> List[LintError]:
    """Remove duplicate errors while preserving order."""
    unique_errors = []
    for error in errors:
        # Standardize the message
        error.message = standardize_error_message(error.message)
        # Only add if not a duplicate
        if not any(is_duplicate_error(error, existing) for existing in unique_errors):
            unique_errors.append(error)
    return unique_errors


def parse_pyflakes_line(line: str, whitelist_patterns: Set[str]) -> Optional[LintError]:
    """Parse a Pyflakes error line into standardized format"""
    # Strip any "Pyflakes error: " prefix if present
    if line.startswith("Pyflakes error: "):
        line = line[len("Pyflakes error: "):]

    match = PYFLAKES_PATTERN.match(line)
    if not match:
        return None

    line_num, col, message = match.groups()

    if any(pattern in message for pattern in whitelist_patterns):
        return None

    return LintError(
        message=message,
        position=Position(
            line=int(line_num) - 1,
            column=int(col) - 1
        )
    )


def parse_contracting_line(violation: str) -> LintError:
    """Parse a Contracting linter error into standardized format"""
    # Strip any "Contracting linter error: " prefix if present
    if violation.startswith("Contracting linter error: "):
        violation = violation[len("Contracting linter error: "):]

    match = CONTRACTING_PATTERN.match(violation)
    if match:
        line_num = int(match.group(1))
        message = match.group(2)
        # Line 0 means global error
        if line_num == 0:
            return LintError(message=message)
        return LintError(
            message=message,
            position=Position(
                line=line_num - 1,
                column=0
            )
        )
    return LintError(message=violation)


async def run_pyflakes(code: str, whitelist_patterns: Set[str]) -> List[LintError]:
    """Runs Pyflakes and returns standardized errors"""
    try:
        loop = asyncio.get_event_loop()
        stdout = StringIO()
        stderr = StringIO()
        reporter = Reporter(stdout, stderr)

        await loop.run_in_executor(None, check, code, "<string>", reporter)

        combined_output = stdout.getvalue() + stderr.getvalue()
        errors = []

        for line in combined_output.splitlines():
            line = line.strip()
            if not line:
                continue

            error = parse_pyflakes_line(line, whitelist_patterns)
            if error:
                errors.append(error)

        return errors
    except Exception as e:
        raise LintingException(str(e)) from e


async def run_contracting_linter(code: str) -> List[LintError]:
    """Runs Contracting linter and returns standardized errors"""
    try:
        loop = asyncio.get_event_loop()
        tree = await loop.run_in_executor(None, ast.parse, code)
        linter = Linter()
        violations = await loop.run_in_executor(None, linter.check, tree)

        if not violations:
            return []

        return [
            parse_contracting_line(v.strip())
            for v in violations
            if v.strip()
        ]
    except Exception as e:
        # Extract line number from AST SyntaxError if available
        if isinstance(e, SyntaxError) and e.lineno is not None:
            return [LintError(
                message=str(e),
                position=Position(line=e.lineno - 1, column=e.offset - 1 if e.offset else 0)
            )]
        raise LintingException(str(e)) from e


@lru_cache(maxsize=settings.CACHE_SIZE)
def get_whitelist_patterns(patterns_str: Optional[str] = None) -> frozenset:
    """Convert whitelist patterns string to frozenset for caching"""
    if not patterns_str:
        return settings.DEFAULT_WHITELIST_PATTERNS
    return frozenset(patterns_str.split(","))


async def lint_code(code: str, whitelist_patterns: Set[str]) -> List[LintError]:
    """Run all linters in parallel"""
    try:
        pyflakes_task = run_pyflakes(code, whitelist_patterns)
        contracting_task = run_contracting_linter(code)

        results = await asyncio.gather(pyflakes_task, contracting_task)
        all_errors = results[0] + results[1]

        # Deduplicate errors
        return deduplicate_errors(all_errors)
    except LintingException as e:
        error_msg = str(e)
        # Strip any known prefixes from the error message
        for prefix in ["Pyflakes error: ", "Contracting linter error: "]:
            if error_msg.startswith(prefix):
                error_msg = error_msg[len(prefix):]
                break
        return [LintError(message=error_msg)]


def convert_lint_error_to_model(error: LintError) -> LintError_Model:
    """Convert a LintError to a LintError_Model"""
    if error.position:
        position = Position_Model(
            line=error.position.line,
            column=error.position.column
        )
    else:
        position = None

    return LintError_Model(
        message=error.message,
        severity=error.severity,
        position=position
    )


@app.post("/lint_base64")
async def lint_base64(request: Request) -> LintResponse:
    """Lint base64-encoded Python code"""
    raw_data = await request.body()

    # Validate request
    if not raw_data:
        raise HTTPException(status_code=400, detail="Empty request body")

    if len(raw_data) > settings.MAX_CODE_SIZE:
        raise HTTPException(status_code=400, detail="Code size too large")

    # Get and validate whitelist patterns
    whitelist_patterns = get_whitelist_patterns(
        request.query_params.get("whitelist_patterns")
    )

    try:
        # Decode base64
        b64_text = raw_data.decode("utf-8", errors="replace")
        code_bytes = base64.b64decode(b64_text)
        code = code_bytes.decode("utf-8", errors="replace")

        if not code.strip():
            raise HTTPException(status_code=400, detail="Empty code")

        # Run linters
        errors = await lint_code(code, whitelist_patterns)

        return LintResponse(
            success=len(errors) == 0,
            errors=[convert_lint_error_to_model(e) for e in errors]
        )
    except Exception as e:
        return LintResponse(
            success=False,
            errors=[convert_lint_error_to_model(
                LintError(message=f"Processing error: {str(e)}")
            )]
        )


@app.post("/lint_gzip")
async def lint_gzip(request: Request) -> LintResponse:
    """Lint gzipped Python code"""
    raw_data = await request.body()

    # Validate request
    if not raw_data:
        raise HTTPException(status_code=400, detail="Empty request body")

    if len(raw_data) > settings.MAX_CODE_SIZE:
        raise HTTPException(status_code=400, detail="Code size too large")

    # Get and validate whitelist patterns
    whitelist_patterns = get_whitelist_patterns(
        request.query_params.get("whitelist_patterns")
    )

    try:
        # Decompress gzip
        code_bytes = gzip.decompress(raw_data)
        code = code_bytes.decode("utf-8", errors="replace")

        if not code.strip():
            raise HTTPException(status_code=400, detail="Empty code")

        # Run linters
        errors = await lint_code(code, whitelist_patterns)

        return LintResponse(
            success=len(errors) == 0,
            errors=[convert_lint_error_to_model(e) for e in errors]
        )
    except Exception as e:
        return LintResponse(
            success=False,
            errors=[convert_lint_error_to_model(
                LintError(message=f"Processing error: {str(e)}")
            )]
        )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
