#!/usr/bin/env python3
"""Apply Alembic migrations (run from repo root: python scripts/init_db.py)."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    backend = Path(__file__).resolve().parent.parent / "backend"
    if not backend.is_dir():
        print("backend/ directory not found.", file=sys.stderr)
        sys.exit(1)
    subprocess.run(
        ["alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=str(backend),
        check=True,
    )
    print("Migrations applied.")


if __name__ == "__main__":
    main()
