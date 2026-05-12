"""
Phase 5 Evaluation — Risk scoring model vs manual labels.

Runs 12 simulated PR scenarios against the dummy_repo KG.
For each scenario:
  - Queries real blast radius from the KG
  - Runs real git enrichment
  - Runs real coverage gap check
  - Computes risk score
  - Compares model output with manually assigned expected risk level

Usage:
    python scripts/evaluation.py

Output: evaluation table + match rate summary.
"""

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REPO = ROOT / "dummy_repo"
DB_PATH = REPO / ".code-review-graph" / "graph.db"


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    id: str
    description: str
    changed_file: str          # relative path from REPO
    pr_author: str
    pr_size_lines: int
    expected: str              # "low" | "medium" | "high"
    expected_reason: str       # why the manual label was assigned


SCENARIOS: list[Scenario] = [
    # --- Low risk ---
    Scenario(
        id="S01",
        description="Tweak logger format string",
        changed_file="src/utils/logger.py",
        pr_author="alice",        # known contributor
        pr_size_lines=5,
        expected="low",
        expected_reason="leaf utility, tiny change, known contributor",
    ),
    Scenario(
        id="S02",
        description="Add docstring to order model",
        changed_file="src/models/order.py",
        pr_author="alice",
        pr_size_lines=8,
        expected="medium",
        expected_reason="alice never touched order.py → new_contributor=True; coverage gap raises score",
    ),
    Scenario(
        id="S03",
        description="Minor refactor in user model",
        changed_file="src/models/user.py",
        pr_author="alice",
        pr_size_lines=15,
        expected="low",
        expected_reason="model layer, small change, known author, tested",
    ),
    # --- Medium risk ---
    Scenario(
        id="S04",
        description="Update validator logic",
        changed_file="src/utils/validator.py",
        pr_author="alice",
        pr_size_lines=40,
        expected="medium",
        expected_reason="shared utility used by payment+auth, moderate blast radius",
    ),
    Scenario(
        id="S05",
        description="New contributor adds cart feature",
        changed_file="src/cart.py",
        pr_author="newguy",       # new contributor
        pr_size_lines=30,
        expected="medium",
        expected_reason="new contributor to these files, cart has no test coverage",
    ),
    Scenario(
        id="S06",
        description="Refactor payment helper",
        changed_file="src/payment.py",
        pr_author="alice",
        pr_size_lines=55,
        expected="medium",
        expected_reason="payment has tests but blast radius includes cart (uncovered)",
    ),
    Scenario(
        id="S07",
        description="Large auth refactor by known contributor",
        changed_file="src/auth.py",
        pr_author="alice",
        pr_size_lines=200,
        expected="medium",
        expected_reason="auth has high bug history; known author keeps it medium",
    ),
    # --- High risk ---
    Scenario(
        id="S08",
        description="New contributor modifies auth module",
        changed_file="src/auth.py",
        pr_author="newguy",
        pr_size_lines=80,
        expected="high",
        expected_reason="auth: high bug frequency + new contributor + wide blast radius",
    ),
    Scenario(
        id="S09",
        description="Massive auth rewrite by new contributor",
        changed_file="src/auth.py",
        pr_author="newguy",
        pr_size_lines=500,
        expected="high",
        expected_reason="large PR + new contributor + high-risk file",
    ),
    Scenario(
        id="S10",
        description="New contributor rewrites payment module",
        changed_file="src/payment.py",
        pr_author="newguy",
        pr_size_lines=120,
        expected="high",
        expected_reason="payment: bug history + new contributor + uncovered blast radius",
    ),
    # --- Edge cases ---
    Scenario(
        id="S11",
        description="Tiny fix in auth by known contributor",
        changed_file="src/auth.py",
        pr_author="alice",
        pr_size_lines=3,
        expected="medium",
        expected_reason="auth bug history raises it; tiny size keeps it from high",
    ),
    Scenario(
        id="S12",
        description="Large refactor of logger by new contributor",
        changed_file="src/utils/logger.py",
        pr_author="newguy",
        pr_size_lines=350,
        expected="medium",
        expected_reason="leaf module (low blast) but new contributor + large PR",
    ),
]


# ---------------------------------------------------------------------------
# Pipeline per scenario
# ---------------------------------------------------------------------------

def run_scenario(s: Scenario) -> dict:
    from code_review_graph.graph import GraphStore
    from src.kg.coverage_mapper import compute_coverage_gap
    from src.kg.git_enrichment import compute_file_stats, is_new_contributor
    from src.risk.scorer import RiskInput, RiskScorer

    changed_abs = [str(REPO / s.changed_file)]

    # 1. Blast radius from real KG
    store = GraphStore(str(DB_PATH))
    blast = store.get_impact_radius(changed_abs, max_depth=2)
    store.close()
    impacted: list[str] = blast.get("impacted_files", [])
    all_files = list(set(changed_abs) | set(impacted))

    # 2. Git enrichment
    git_stats = compute_file_stats(REPO, changed_abs)
    bug_freq = max((st.bug_frequency    for st in git_stats.values()), default=0)
    churn    = max((st.contributor_churn for st in git_stats.values()), default=0)

    # 3. Coverage gap
    cov = compute_coverage_gap(all_files, REPO)

    # 4. New contributor check
    new_contrib = is_new_contributor(REPO, changed_abs, s.pr_author)

    # 5. Score
    scorer = RiskScorer()
    inp = RiskInput(
        blast_radius_size  = len(impacted),
        coverage_gap_ratio = cov["coverage_gap_ratio"],
        bug_frequency      = bug_freq,
        contributor_churn  = churn,
        is_new_contributor = new_contrib,
        pr_size_lines      = s.pr_size_lines,
    )
    result = scorer.score(inp)

    return {
        "blast_size":   len(impacted),
        "bug_freq":     bug_freq,
        "churn":        churn,
        "new_contrib":  new_contrib,
        "cov_gap":      cov["coverage_gap_ratio"],
        "score":        result.score,
        "model_level":  result.level,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not DB_PATH.exists():
        print("ERROR: KG not built. Run first:")
        print("  python scripts/test_risk_pipeline.py")
        sys.exit(1)

    print("=" * 90)
    print(f"{'ID':<4} {'Description':<38} {'File':<22} {'Exp':>6} {'Model':>6} {'Score':>6} {'Match':>5}")
    print("=" * 90)

    matches = 0
    rows = []

    for s in SCENARIOS:
        r = run_scenario(s)
        match = (r["model_level"] == s.expected)
        if match:
            matches += 1
        rows.append((s, r, match))
        flag = "[OK]" if match else "[!!]"
        print(
            f"{s.id:<4} {s.description[:37]:<38} "
            f"{s.changed_file[:21]:<22} "
            f"{s.expected:>6} {r['model_level']:>6} {r['score']:>6.3f} {flag:>5}"
        )

    total = len(SCENARIOS)
    print("=" * 90)
    print(f"\nMatch rate: {matches}/{total} ({matches/total:.0%})")
    print("\nDetailed signal breakdown for mismatches:")
    for s, r, match in rows:
        if not match:
            print(
                f"  {s.id} {s.description[:40]}\n"
                f"     expected={s.expected}, model={r['model_level']} (score={r['score']:.3f})\n"
                f"     blast={r['blast_size']} bug={r['bug_freq']} churn={r['churn']} "
                f"new_contrib={r['new_contrib']} cov_gap={r['cov_gap']:.0%} "
                f"pr_size={s.pr_size_lines}\n"
                f"     reason: {s.expected_reason}"
            )

    print("\nNote: mismatches may indicate weights need tuning (config/risk_weights.yaml)")


if __name__ == "__main__":
    main()
