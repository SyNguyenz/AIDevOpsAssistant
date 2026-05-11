"""
Test CI-aware pipeline (Phase 4) using dummy data.

Tests:
  - parse_pytest_log: correctly extracts FAILED test IDs
  - cross_reference_failures: links test failures to blast radius files
  - build_ci_section: formats markdown correctly

Does NOT call GitHub API (no token required).

Usage:
    python scripts/test_ci_pipeline.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REPO = ROOT / "dummy_repo"


# ---------------------------------------------------------------------------
# Step 1: pytest log parser
# ---------------------------------------------------------------------------

def test_parse_pytest_log():
    print("=== Step 1: parse_pytest_log ===")
    from src.server.ci_reader import parse_pytest_log

    sample_log = """
============================= test session results ==============================
PASSED tests/test_utils.py::test_hash_password
FAILED tests/test_auth.py::test_login_invalid - AssertionError: expected 200 got 401
FAILED tests/test_payment.py::test_charge_user - AttributeError: 'NoneType' has no attribute 'charge'

============================== short test summary info ==============================
FAILED tests/test_auth.py::test_login_invalid - AssertionError: expected 200 got 401
FAILED tests/test_payment.py::test_charge_user - AttributeError: 'NoneType' has no attribute 'charge'
2 failed, 1 passed in 0.45s
"""

    results = parse_pytest_log(sample_log)
    print(f"  Found {len(results)} failed tests:")
    for ft in results:
        print(f"    [{ft.test_file}] {ft.test_name} — {ft.error_snippet[:60]}")

    assert len(results) == 2, f"Expected 2, got {len(results)}"
    ids = {ft.test_id for ft in results}
    assert "tests/test_auth.py::test_login_invalid" in ids
    assert "tests/test_payment.py::test_charge_user" in ids
    print("  [OK] parse_pytest_log")
    return results


# ---------------------------------------------------------------------------
# Step 2: cross-reference with blast radius
# ---------------------------------------------------------------------------

def test_cross_reference(failed_tests):
    print("\n=== Step 2: cross_reference_failures ===")
    from src.server.ci_analyzer import cross_reference_failures

    # Simulate: auth.py was changed, payment.py is in blast radius
    changed_files = [str(REPO / "src" / "auth.py")]
    blast_files = [
        str(REPO / "src" / "auth.py"),
        str(REPO / "src" / "payment.py"),
        str(REPO / "src" / "checkout.py"),
    ]

    links = cross_reference_failures(failed_tests, changed_files, blast_files)
    print(f"  Found {len(links)} causal links:")
    for lk in links:
        print(
            f"    {lk.failed_test}\n"
            f"      -> blast: {Path(lk.blast_file).name}\n"
            f"      -> changed: {Path(lk.changed_file).name if lk.changed_file else '?'}"
        )

    assert len(links) >= 1, "Expected at least 1 link"
    blast_names = {Path(lk.blast_file).name for lk in links}
    assert "auth.py" in blast_names or "payment.py" in blast_names
    print("  [OK] cross_reference_failures")
    return links


# ---------------------------------------------------------------------------
# Step 3: build CI section markdown
# ---------------------------------------------------------------------------

def test_build_ci_section(failed_tests, links):
    print("\n=== Step 3: build_ci_section ===")
    from src.server.ci_reader import CIStatus
    from src.server.ci_analyzer import build_ci_section

    ci_status = CIStatus(
        run_id=12345,
        status="completed",
        conclusion="failure",
        html_url="https://github.com/SyNguyenz/dummy_repo/actions/runs/12345",
        name="CI / pytest",
    )

    section = build_ci_section(ci_status, failed_tests, links)
    print(section)

    assert "FAILURE" in section
    assert "test_login_invalid" in section or "test_charge_user" in section
    if links:
        assert "blast radius" in section
    print("  [OK] build_ci_section")
    return section


# ---------------------------------------------------------------------------
# Step 4: full prompt integration (no KG build needed)
# ---------------------------------------------------------------------------

def test_build_risk_prompt(ci_section, failed_tests, links):
    print("\n=== Step 4: build_risk_prompt with CI context ===")
    from src.risk.scorer import RiskInput, RiskScorer
    from src.server.ci_reader import CIStatus
    from src.server.risk_review_tool import build_risk_prompt

    scorer = RiskScorer()
    risk_result = scorer.score(RiskInput(
        blast_radius_size=3,
        coverage_gap_ratio=0.67,
        bug_frequency=2,
        contributor_churn=1,
        is_new_contributor=True,
        pr_size_lines=45,
    ))

    ci_status = CIStatus(
        run_id=12345,
        status="completed",
        conclusion="failure",
        html_url="https://github.com/SyNguyenz/dummy_repo/actions/runs/12345",
        name="CI / pytest",
    )

    pipeline = {
        "risk_result": risk_result,
        "blast_radius": {"impacted_files": [
            str(ROOT / "dummy_repo" / "src" / "payment.py"),
            str(ROOT / "dummy_repo" / "src" / "checkout.py"),
        ]},
        "coverage": {"uncovered": [str(ROOT / "dummy_repo" / "src" / "checkout.py")], "coverage_gap_ratio": 0.33},
        "ci_status": ci_status,
        "failed_tests": failed_tests,
        "ci_links": links,
    }

    prompt = build_risk_prompt(pipeline)
    print(prompt)
    assert "Risk Analysis" in prompt
    assert "CI Status" in prompt
    print("\n  [OK] build_risk_prompt includes CI section")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    failed_tests = test_parse_pytest_log()
    links = test_cross_reference(failed_tests)
    ci_section = test_build_ci_section(failed_tests, links)
    test_build_risk_prompt(ci_section, failed_tests, links)

    print("\n[RESULT] Phase 4 CI-aware pipeline: ALL TESTS PASSED")
