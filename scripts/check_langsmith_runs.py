"""Utility script to monitor and inspect recent LangSmith trace runs.

Reads configuration directly from environment variables or .env without hardcoded keys.
Default endpoint routes to the EU workspace (https://eu.api.smith.langchain.com).

Usage:
    uv run python scripts/check_langsmith_runs.py [--limit 10] [--project af-aidevs] [--session-id <id>]
"""

import argparse
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

warnings.filterwarnings("ignore", category=DeprecationWarning)


def load_environment(explicit_path: str | None = None) -> None:
    """Loads environment variables from explicit path, cwd/parents, or lesson directories."""
    if explicit_path and Path(explicit_path).exists():
        load_dotenv(explicit_path, override=True, encoding="utf-8-sig")
        return

    # 1. Search upwards from cwd
    cwd_dotenv = find_dotenv(usecwd=True)
    if cwd_dotenv and Path(cwd_dotenv).exists():
        load_dotenv(cwd_dotenv, override=False, encoding="utf-8-sig")

    if os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"):
        return

    # 2. Search within lesson folders if not found in root
    repo_root = Path(__file__).resolve().parent.parent
    for candidate in repo_root.glob("lessons/**/.env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False, encoding="utf-8-sig")
            if os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"):
                break


load_environment()

try:
    from langsmith import Client
except ImportError:
    print(
        "ERROR: 'langsmith' package is not installed. Install via: uv pip install langsmith",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect recent LangSmith runs for af-aidevs"
    )
    parser.add_argument(
        "--project",
        type=str,
        default=os.getenv("LANGSMITH_PROJECT")
        or os.getenv("LANGCHAIN_PROJECT")
        or "af-aidevs",
        help="LangSmith project name (default: env or af-aidevs)",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=os.getenv("LANGSMITH_ENDPOINT")
        or os.getenv("LANGCHAIN_ENDPOINT")
        or "https://eu.api.smith.langchain.com",
        help="LangSmith API endpoint (default: https://eu.api.smith.langchain.com)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent runs to display (default: 10)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="Filter runs by session_id in metadata",
    )

    args = parser.parse_args()

    api_key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        print(
            "ERROR: Missing LANGSMITH_API_KEY or LANGCHAIN_API_KEY in environment or .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Connecting to LangSmith endpoint: {args.endpoint}")
    print(f"Project: {args.project} | Limit: {args.limit}\n")

    client = Client(api_url=args.endpoint, api_key=api_key)

    try:
        filter_expr = None
        if args.session_id:
            filter_expr = f'has(metadata, "session_id") and eq(metadata["session_id"], "{args.session_id}")'

        runs = list(
            client.list_runs(
                project_name=args.project,
                limit=args.limit,
                filter=filter_expr,
            )
        )

        if not runs:
            print("No runs found matching query.")
            return

        print(
            f"{'START TIME':<22} | {'NAME':<28} | {'STATUS':<10} | {'DURATION':<8} | {'SESSION_ID'}"
        )
        print("-" * 95)

        for run in runs:
            start_str = (
                run.start_time.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(run.start_time, datetime)
                else str(run.start_time)[:19]
            )
            duration_s = (
                f"{(run.end_time - run.start_time).total_seconds():.2f}s"
                if run.end_time and run.start_time
                else "N/A"
            )
            metadata = run.extra.get("metadata", {}) if run.extra else {}
            session_id = metadata.get("session_id", "N/A")
            name = (run.name[:25] + "...") if len(run.name) > 28 else run.name
            status = run.status or "unknown"

            print(
                f"{start_str:<22} | {name:<28} | {status:<10} | {duration_s:<8} | {session_id}"
            )

    except Exception as exc:
        print(f"Error querying LangSmith: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
