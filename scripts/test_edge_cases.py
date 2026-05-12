"""
Phase 5: Edge case tests.

Tests behavior when:
  - No Python files changed (README-only PR)
  - Empty changed_files list
  - File not in KG (new file added by PR)
  - All files already covered (coverage_gap_ratio=0)
  - Binary/non-Python file only

Usage:
    python scripts/test_edge_cases.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REPO = ROOT / "dummy_repo"
DB_PATH = REPO / ".code-review-graph" / "graph.db"


def test_no_python_files():
    print("=== Edge 1: No Python files (README-only PR) ===")
    from src.risk.scorer import RiskInput, RiskScorer
    scorer = RiskScorer()
    # Pipeline returns early with empty RiskInput
    result = scorer.score(RiskInput())
    assert result.score == 0.0
    assert result.level == "low"
    print(f"  score={result.score} level={result.level} [OK]")


def test_empty_blast_radius():
    print("\n=== Edge 2: File with zero blast radius (isolated module) ===")
    from code_review_graph.graph import GraphStore
    from src.risk.scorer import RiskInput, RiskScorer

    store = GraphStore(str(DB_PATH))
    blast = store.get_impact_radius([str(REPO / "src" / "utils" / "logger.py")], max_depth=2)
    store.close()
    impacted = blast.get("impacted_files", [])
    print(f"  logger.py blast radius: {[Path(f).name for f in impacted]}")

    scorer = RiskScorer()
    result = scorer.score(RiskInput(
        blast_radius_size=len(impacted),
        coverage_gap_ratio=0.0,
        bug_frequency=0,
        contributor_churn=1,
        is_new_contributor=False,
        pr_size_lines=5,
    ))
    print(f"  score={result.score} level={result.level} [OK]")
    assert result.level == "low"


def test_new_file_not_in_kg():
    print("\n=== Edge 3: New file not yet in KG ===")
    from code_review_graph.graph import GraphStore
    from src.risk.scorer import RiskInput, RiskScorer

    new_file = str(REPO / "src" / "new_feature.py")
    store = GraphStore(str(DB_PATH))
    blast = store.get_impact_radius([new_file], max_depth=2)
    store.close()
    impacted = blast.get("impacted_files", [])
    print(f"  new_feature.py blast radius: {len(impacted)} files (expected 0)")
    assert len(impacted) == 0

    result = RiskScorer().score(RiskInput(
        blast_radius_size=0,
        coverage_gap_ratio=1.0,  # new file = no tests
        is_new_contributor=True,
        pr_size_lines=150,
    ))
    print(f"  score={result.score} level={result.level}")
    assert result.level in ("low", "medium")  # no blast radius keeps it down
    print("  [OK]")


def test_full_coverage():
    print("\n=== Edge 4: All blast radius files fully covered ===")
    from src.risk.scorer import RiskInput, RiskScorer
    result = RiskScorer().score(RiskInput(
        blast_radius_size=5,
        coverage_gap_ratio=0.0,  # 100% covered
        bug_frequency=1,
        contributor_churn=2,
        is_new_contributor=False,
        pr_size_lines=30,
    ))
    print(f"  score={result.score} level={result.level}")
    assert result.level == "low", f"Expected low, got {result.level}"
    print("  [OK]")


def test_non_python_files():
    print("\n=== Edge 5: Only non-Python files changed (JS, YAML) ===")
    from src.kg.coverage_mapper import compute_coverage_gap
    # coverage_gap with empty source list → 0.0
    result = compute_coverage_gap(["config/app.yaml", "frontend/main.js"], REPO)
    assert result["coverage_gap_ratio"] == 0.0
    assert result["method"] == "none"
    print(f"  method={result['method']} gap={result['coverage_gap_ratio']} [OK]")


def test_risk_scorer_caps():
    print("\n=== Edge 6: Values above normalization caps -> capped at 1.0 ===")
    from src.risk.scorer import RiskInput, RiskScorer
    result = RiskScorer().score(RiskInput(
        blast_radius_size=999,    # way above max_blast_radius=8
        coverage_gap_ratio=2.0,   # impossible but should be clamped
        bug_frequency=999,
        contributor_churn=999,
        is_new_contributor=True,
        pr_size_lines=999999,
    ))
    assert result.score <= 1.0
    assert result.level == "high"
    print(f"  score={result.score} (capped at 1.0) level={result.level} [OK]")


if __name__ == "__main__":
    test_no_python_files()
    test_empty_blast_radius()
    test_new_file_not_in_kg()
    test_full_coverage()
    test_non_python_files()
    test_risk_scorer_caps()
    print("\n[RESULT] All edge case tests PASSED")
