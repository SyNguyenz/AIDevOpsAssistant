"""
CI-KG cross-reference analyzer — Phase 4.

Links failed tests back to the blast radius to explain WHY a CI job failed
in terms of the changed source files that likely caused it.

Logic:
  1. For each failed test file (e.g. tests/test_auth.py) → infer source module
     via naming convention (test_auth → auth) or coverage_mapper.convention_map.
  2. Check if that source module appears in the PR's blast radius.
  3. If yes, record the link: changed file X → impacted Y → tested by test Z (failed).

Limitation: relies on Python naming convention (test_<module>.py or <module>_test.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.server.ci_reader import FailedTest


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class FailureLink:
    """One causal chain: changed_file → blast_file → failed_test."""
    changed_file: str    # file modified in the PR (triggered the change)
    blast_file: str      # impacted file in blast radius
    failed_test: str     # test_id that failed
    test_file: str       # path of the test file
    error_snippet: str = ""


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def cross_reference_failures(
    failed_tests: list[FailedTest],
    changed_files: list[str],
    blast_radius_files: list[str],
) -> list[FailureLink]:
    """
    Link each failed test to a source file in the blast radius.

    Returns a list of FailureLink with the causal chain.
    Only returns links where a clear connection exists.
    """
    all_scope = list(set(changed_files) | set(blast_radius_files))
    links: list[FailureLink] = []

    for ft in failed_tests:
        source_stem = _infer_source_stem(ft.test_file)
        if not source_stem:
            continue

        # Find matching source file in blast radius / changed files
        blast_match = _find_source_in_list(source_stem, blast_radius_files)
        changed_match = _find_source_in_list(source_stem, changed_files)

        if blast_match:
            # The test covers a file in the blast radius
            trigger = changed_match or _find_closest_changed(blast_match, changed_files)
            links.append(FailureLink(
                changed_file=trigger or "",
                blast_file=blast_match,
                failed_test=ft.test_id,
                test_file=ft.test_file,
                error_snippet=ft.error_snippet,
            ))

    return links


def build_ci_section(
    ci_status,  # CIStatus | None
    failed_tests: list[FailedTest],
    links: list[FailureLink],
) -> str:
    """Return a markdown section for the CI analysis to prepend to the LLM prompt."""
    if ci_status is None:
        return ""

    conclusion = ci_status.conclusion or ci_status.status
    lines = [
        "### CI Status",
        f"**Workflow:** {ci_status.name or 'CI'}  |  "
        f"**Result:** `{conclusion.upper()}`  |  "
        f"[View run]({ci_status.html_url})",
        "",
    ]

    if not failed_tests:
        if conclusion == "failure":
            lines.append("_CI failed but no pytest FAILED lines found in logs._")
        return "\n".join(lines)

    lines += [
        f"**Failed tests ({len(failed_tests)}):**",
    ]
    for ft in failed_tests[:8]:
        snippet = f" — `{ft.error_snippet[:80]}`" if ft.error_snippet else ""
        lines.append(f"- `{ft.test_id}`{snippet}")
    if len(failed_tests) > 8:
        lines.append(f"- _(+{len(failed_tests) - 8} more)_")
    lines.append("")

    if links:
        lines += [
            "**Likely causal chain (KG cross-reference):**",
        ]
        for lk in links[:5]:
            changed_name = Path(lk.changed_file).name if lk.changed_file else "?"
            blast_name = Path(lk.blast_file).name
            lines.append(
                f"- `{lk.failed_test}` tests `{blast_name}` "
                f"which is in the blast radius of `{changed_name}`"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_PREFIX_RE = re.compile(r"^test_(.+)|(.+)_test$")


def _infer_source_stem(test_file: str) -> str:
    """
    Given a test file path, return the expected source module stem.
    e.g. "tests/test_auth.py" → "auth"
    """
    stem = Path(test_file).stem  # e.g. "test_auth"
    m = _TEST_PREFIX_RE.match(stem)
    if m:
        return m.group(1) or m.group(2)
    return ""


def _find_source_in_list(source_stem: str, file_list: list[str]) -> str:
    """Return the first path in file_list whose stem matches source_stem."""
    for f in file_list:
        if Path(f).stem == source_stem:
            return f
    return ""


def _find_closest_changed(blast_file: str, changed_files: list[str]) -> str:
    """Heuristic: return the changed file most likely to have caused blast_file."""
    # Simple heuristic: first changed file (could be improved with KG edge traversal)
    return changed_files[0] if changed_files else ""
