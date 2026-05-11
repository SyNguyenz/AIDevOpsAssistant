"""
CI-aware reader — Phase 4.

Reads GitHub Actions workflow run status and logs for a PR's head commit.
Parses pytest log output to extract failed test identifiers.

Limitation: only supports pytest output format (PASSED/FAILED/ERROR lines).
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Optional

import requests


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CIStatus:
    run_id: int
    status: str       # "completed" | "in_progress" | "queued"
    conclusion: str   # "success" | "failure" | "cancelled" | "" (pending)
    html_url: str
    name: str = ""    # workflow name


@dataclass
class FailedTest:
    test_id: str      # e.g. "tests/test_auth.py::test_login"
    test_file: str    # e.g. "tests/test_auth.py"
    test_name: str    # e.g. "test_login"
    error_snippet: str = ""  # first relevant error line


# ---------------------------------------------------------------------------
# GitHub Actions client
# ---------------------------------------------------------------------------

class CIReader:
    """Thin wrapper around GitHub Actions REST API."""

    def __init__(self, token: str, repo_full_name: str):
        self.repo = repo_full_name
        self._base = f"https://api.github.com/repos/{repo_full_name}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_pr_ci_status(self, head_sha: str) -> Optional[CIStatus]:
        """
        Return the latest failed (or most recent) workflow run for a commit SHA.
        Returns None if no runs found or on API error.
        """
        try:
            resp = requests.get(
                f"{self._base}/actions/runs",
                headers=self._headers,
                params={"head_sha": head_sha, "per_page": 10},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception:
            return None

        runs = resp.json().get("workflow_runs", [])
        if not runs:
            return None

        # Prefer a failed run; otherwise return the most recent
        failed = [r for r in runs if r.get("conclusion") == "failure"]
        run = failed[0] if failed else runs[0]

        return CIStatus(
            run_id=run["id"],
            status=run.get("status", ""),
            conclusion=run.get("conclusion") or "",
            html_url=run.get("html_url", ""),
            name=run.get("name", ""),
        )

    # ------------------------------------------------------------------
    # Log parsing
    # ------------------------------------------------------------------

    def get_failed_tests(self, run_id: int) -> list[FailedTest]:
        """
        Download the log zip for a workflow run and parse pytest output.
        Returns list of FailedTest extracted from FAILED lines.
        """
        log_zip = self._download_log_zip(run_id)
        if not log_zip:
            return []
        return _parse_pytest_from_zip(log_zip)

    def _download_log_zip(self, run_id: int) -> Optional[bytes]:
        """Download log zip bytes; follows GitHub's 302 redirect."""
        url = f"{self._base}/actions/runs/{run_id}/logs"
        try:
            # GitHub returns 302 to a signed S3 URL
            resp = requests.get(
                url, headers=self._headers,
                allow_redirects=False, timeout=15,
            )
            if resp.status_code == 302:
                download_url = resp.headers.get("Location", "")
                # Signed URL — no auth header needed
                dl = requests.get(download_url, timeout=60)
                dl.raise_for_status()
                return dl.content
            elif resp.status_code == 200:
                return resp.content
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Pytest log parser
# ---------------------------------------------------------------------------

# Matches: FAILED tests/test_auth.py::test_login - AssertionError: ...
_FAILED_LINE_RE = re.compile(
    r"FAILED\s+([\w/\\.\-]+\.py)::(\w+)(?:\s+-\s+(.+))?",
    re.IGNORECASE,
)

# Matches short summary section header
_SUMMARY_HEADER_RE = re.compile(r"=+ short test summary info =+", re.IGNORECASE)


def parse_pytest_log(log_text: str) -> list[FailedTest]:
    """
    Parse a single pytest log string and return all FAILED tests.

    Looks in the "short test summary info" section first (most reliable),
    then falls back to scanning all FAILED lines in the full log.
    """
    results: dict[str, FailedTest] = {}

    # Try to isolate the short summary section
    summary_match = _SUMMARY_HEADER_RE.search(log_text)
    search_text = log_text[summary_match.start():] if summary_match else log_text

    for m in _FAILED_LINE_RE.finditer(search_text):
        test_file = m.group(1).replace("\\", "/")
        test_name = m.group(2)
        error_snippet = (m.group(3) or "").strip()
        test_id = f"{test_file}::{test_name}"

        if test_id not in results:
            results[test_id] = FailedTest(
                test_id=test_id,
                test_file=test_file,
                test_name=test_name,
                error_snippet=error_snippet,
            )

    return list(results.values())


def _parse_pytest_from_zip(zip_bytes: bytes) -> list[FailedTest]:
    """Extract all log files from zip and parse for pytest FAILED lines."""
    results: list[FailedTest] = []
    seen_ids: set[str] = set()

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if not name.endswith(".txt"):
                    continue
                try:
                    text = zf.read(name).decode("utf-8", errors="replace")
                except Exception:
                    continue
                for ft in parse_pytest_log(text):
                    if ft.test_id not in seen_ids:
                        seen_ids.add(ft.test_id)
                        results.append(ft)
    except Exception:
        pass

    return results
