"""
Test risk scoring pipeline end-to-end on dummy_repo.

Simulates a PR that changes src/auth.py (high-risk file).

Usage:
    python scripts/test_risk_pipeline.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REPO = ROOT / "dummy_repo"


def step1_build_kg():
    print("=== Step 1: Build KG ===")
    from code_review_graph.tools.build import build_or_update_graph
    r = build_or_update_graph(full_rebuild=True, repo_root=str(REPO))
    print(f"  nodes={r.get('total_nodes')}  edges={r.get('total_edges')}")


def step2_run_coverage():
    print("\n=== Step 2: Run pytest --cov to generate .coverage ===")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--cov=src", "--cov-report=", "-q"],
        cwd=str(REPO),
        capture_output=True, text=True,
    )
    if (REPO / ".coverage").exists():
        print("  .coverage file generated")
    else:
        print("  .coverage not found — will use convention fallback")
        print("  pytest output:", result.stdout[-300:] if result.stdout else result.stderr[-300:])


def step3_blast_radius():
    print("\n=== Step 3: Blast radius for src/auth.py ===")
    from code_review_graph.graph import GraphStore
    db = REPO / ".code-review-graph" / "graph.db"
    store = GraphStore(str(db))
    changed = [str(REPO / "src" / "auth.py")]
    blast = store.get_impact_radius(changed, max_depth=2)
    store.close()
    print(f"  Impacted files ({len(blast['impacted_files'])}):")
    for f in sorted(blast["impacted_files"]):
        print(f"    - {Path(f).relative_to(REPO)}")
    return blast


def step4_coverage_gap(blast):
    print("\n=== Step 4: Coverage gap ===")
    from src.kg.coverage_mapper import compute_coverage_gap
    all_files = blast.get("impacted_files", []) + [str(REPO / "src" / "auth.py")]
    cov = compute_coverage_gap(all_files, REPO, REPO / ".coverage")
    print(f"  Method : {cov['method']}")
    print(f"  Covered: {[Path(f).name for f in cov['covered']]}")
    print(f"  Uncovered ({len(cov['uncovered'])}): {[Path(f).name for f in cov['uncovered']]}")
    print(f"  Gap ratio: {cov['coverage_gap_ratio']:.0%}")
    return cov


def step5_git_enrichment():
    print("\n=== Step 5: Git history enrichment ===")
    from src.kg.git_enrichment import compute_file_stats, is_new_contributor
    changed = [str(REPO / "src" / "auth.py")]
    stats = compute_file_stats(REPO, changed)
    for path, s in stats.items():
        print(f"  {Path(path).name}: bug={s.bug_frequency} churn={s.contributor_churn} vel={s.change_velocity}")
    new_contrib = is_new_contributor(REPO, changed, "newguy")
    print(f"  'newguy' is new contributor: {new_contrib}")
    return stats


def step6_risk_score(blast, cov, git_stats):
    print("\n=== Step 6: Risk Score ===")
    from src.risk.scorer import RiskInput, RiskScorer

    scorer = RiskScorer()
    bug_freq = max((s.bug_frequency    for s in git_stats.values()), default=0)
    churn    = max((s.contributor_churn for s in git_stats.values()), default=0)

    inp = RiskInput(
        blast_radius_size  = len(blast.get("impacted_files", [])),
        coverage_gap_ratio = cov["coverage_gap_ratio"],
        bug_frequency      = bug_freq,
        contributor_churn  = churn,
        is_new_contributor = True,   # simulate new contributor
        pr_size_lines      = 45,     # simulate small PR
    )
    result = scorer.score(inp)
    print(result.explanation())
    return result


if __name__ == "__main__":
    if not REPO.exists():
        print("ERROR: dummy_repo not found. Run: python scripts/create_dummy_repo.py")
        sys.exit(1)

    step1_build_kg()
    step2_run_coverage()
    blast = step3_blast_radius()
    cov   = step4_coverage_gap(blast)
    stats = step5_git_enrichment()
    risk  = step6_risk_score(blast, cov, stats)

    print(f"\n[RESULT] Risk={risk.level.upper()} ({risk.score:.2f})")
    action = {"low": "auto-approve", "medium": "post review comment", "high": "request changes"}
    print(f"[ACTION] {action[risk.level]}")
