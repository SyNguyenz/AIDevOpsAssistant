"""
Phase 5: Full evaluation summary with comprehensive metrics.

Combines dummy_repo (calibration set, 12 scenarios) +
click real-repo (generalization set, 10 scenarios) into one report.

Metrics reported:
  - Accuracy (simple match rate)
  - Confusion matrix
  - Per-class Precision / Recall / F1
  - Weighted F1 (accounts for class imbalance)
  - Macro F1
  - Ordinal accuracy (off-by-1 counts as half-correct)
  - Cohen's Kappa (agreement beyond chance)

Also demonstrates auto-calibration: compute caps from repo stats,
compare vs manually-tuned caps.

Usage:
    python scripts/evaluation_summary.py
    python scripts/evaluation_summary.py --auto   # use auto-calibrated caps for click
"""

import sys
from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DUMMY_REPO  = ROOT / "dummy_repo"
EVAL_REPO   = ROOT / "eval_repo"
DUMMY_DB    = DUMMY_REPO / ".code-review-graph" / "graph.db"
EVAL_DB     = EVAL_REPO  / ".code-review-graph" / "graph.db"

LEVELS = ["low", "medium", "high"]
LEVEL_IDX = {l: i for i, l in enumerate(LEVELS)}


# ---------------------------------------------------------------------------
# Inline scenario definitions (copied from evaluation.py / evaluation_real.py)
# to avoid importlib side effects
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dc, field as _field

@_dc
class _S:
    id: str; description: str; changed_file: str
    pr_author: str; pr_size_lines: int; expected: str; expected_reason: str = ""

@_dc
class _R:
    pr_id: str; description: str; changed_files: list
    pr_author: str; pr_size_lines: int; expected: str; rationale: str = ""

DUMMY_SCENARIOS = [
    _S("S01","Tweak logger format string","src/utils/logger.py","alice",5,"low"),
    _S("S02","Add docstring to order model","src/models/order.py","alice",8,"medium"),
    _S("S03","Minor refactor in user model","src/models/user.py","alice",15,"low"),
    _S("S04","Update validator logic","src/utils/validator.py","alice",40,"medium"),
    _S("S05","New contributor adds cart feature","src/cart.py","newguy",30,"medium"),
    _S("S06","Refactor payment helper","src/payment.py","alice",55,"medium"),
    _S("S07","Large auth refactor by known contributor","src/auth.py","alice",200,"medium"),
    _S("S08","New contributor modifies auth module","src/auth.py","newguy",80,"high"),
    _S("S09","Massive auth rewrite by new contributor","src/auth.py","newguy",500,"high"),
    _S("S10","New contributor rewrites payment module","src/payment.py","newguy",120,"high"),
    _S("S11","Tiny fix in auth by known contributor","src/auth.py","alice",3,"medium"),
    _S("S12","Large refactor of logger by new contributor","src/utils/logger.py","newguy",350,"medium"),
]

REAL_SCENARIOS = [
    _R("#3256","Custom error in prompt",["src/click/termui.py"],"Kevin Deldycke",28,"medium"),
    _R("#3208","Fix shadowed option hint",["src/click/exceptions.py"],"Rowlando13",6,"medium"),
    _R("#3363","Auto-detect UNPROCESSED type",["src/click/core.py"],"Rowlando13",23,"medium"),
    _R("#3364","Split default_map strings",["src/click/core.py"],"Rowlando13",5,"medium"),
    _R("#3371","Typing improvements (multi-file)",["src/click/core.py","src/click/types.py","src/click/termui.py"],"Kevin Deldycke",254,"high"),
    _R("#3240","Reduce UNSET blast-radius",["src/click/core.py"],"Rowlando13",36,"medium"),
    _R("#3244","CliRunner file descriptor",["src/click/testing.py"],"Kevin Deldycke",65,"medium"),
    _R("#3299","Fix empty string check",["src/click/core.py"],"Kevin Deldycke",2,"medium"),
    _R("#3235","Debugger in tests",["src/click/testing.py"],"Kevin Deldycke",45,"medium"),
    _R("#3250","Mark private API",["src/click/utils.py"],"Rowlando13",5,"medium"),
]

def _load_dummy_scenarios():
    return DUMMY_SCENARIOS, DUMMY_REPO, DUMMY_DB

def _load_real_scenarios():
    return REAL_SCENARIOS, EVAL_REPO, EVAL_DB


# ---------------------------------------------------------------------------
# Pipeline runner (unified)
# ---------------------------------------------------------------------------

def run_pipeline(changed_abs, pr_author, pr_size_lines, repo_root, db_path, config_path=None):
    from code_review_graph.graph import GraphStore
    from src.kg.coverage_mapper import compute_coverage_gap
    from src.kg.git_enrichment import compute_file_stats, is_new_contributor
    from src.risk.scorer import RiskInput, RiskScorer

    store = GraphStore(str(db_path))
    blast = store.get_impact_radius(changed_abs, max_depth=2)
    store.close()
    impacted = blast.get("impacted_files", [])
    all_files = list(set(changed_abs) | set(impacted))

    git_stats = compute_file_stats(repo_root, changed_abs)
    bug_freq  = max((s.bug_frequency    for s in git_stats.values()), default=0)
    churn     = max((s.contributor_churn for s in git_stats.values()), default=0)
    cov       = compute_coverage_gap(all_files, repo_root)
    new_c     = is_new_contributor(repo_root, changed_abs, pr_author)

    scorer = RiskScorer(config_path) if config_path else RiskScorer()
    inp = RiskInput(
        blast_radius_size  = len(impacted),
        coverage_gap_ratio = cov["coverage_gap_ratio"],
        bug_frequency      = bug_freq,
        contributor_churn  = churn,
        is_new_contributor = new_c,
        pr_size_lines      = pr_size_lines,
    )
    result = scorer.score(inp)
    return result.score, result.level


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def confusion_matrix(labels, preds):
    mat = [[0]*3 for _ in range(3)]
    for l, p in zip(labels, preds):
        mat[LEVEL_IDX[l]][LEVEL_IDX[p]] += 1
    return mat


def prf1_metrics(labels, preds):
    rows = {}
    for cls in LEVELS:
        tp = sum(1 for l, p in zip(labels, preds) if l == cls and p == cls)
        fp = sum(1 for l, p in zip(labels, preds) if l != cls and p == cls)
        fn = sum(1 for l, p in zip(labels, preds) if l == cls and p != cls)
        p  = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        rows[cls] = {"P": p, "R": r, "F1": f1, "support": tp + fn}
    return rows


def weighted_f1(prf, labels):
    total = len(labels)
    return sum(prf[c]["F1"] * prf[c]["support"] for c in LEVELS) / total if total else 0.0


def macro_f1(prf):
    return sum(prf[c]["F1"] for c in LEVELS) / len(LEVELS)


def ordinal_accuracy(labels, preds):
    """Each off-by-1 error = 0.5 credit, off-by-2 = 0.0 credit."""
    score = 0.0
    for l, p in zip(labels, preds):
        diff = abs(LEVEL_IDX[l] - LEVEL_IDX[p])
        score += 1.0 if diff == 0 else (0.5 if diff == 1 else 0.0)
    return score / len(labels) if labels else 0.0


def cohen_kappa(labels, preds):
    n = len(labels)
    if n == 0:
        return 0.0
    # Observed agreement
    po = sum(1 for l, p in zip(labels, preds) if l == p) / n
    # Expected agreement
    pe = 0.0
    for cls in LEVELS:
        p_label = labels.count(cls) / n
        p_pred  = preds.count(cls)  / n
        pe += p_label * p_pred
    return (po - pe) / (1 - pe) if pe < 1 else 0.0


def print_confusion_matrix(mat, title=""):
    if title:
        print(f"\n{title}")
    header = f"{'':>12}" + "".join(f" {c:>8}" for c in LEVELS)
    print(header)
    print(f"{'':>12}" + "-" * (9 * len(LEVELS)))
    for i, actual in enumerate(LEVELS):
        row = f"act:{actual:>6} |" + "".join(f" {mat[i][j]:>8}" for j in range(len(LEVELS)))
        print(row)
    print(f"{'':>12}" + " " + "   pred ->".rjust(9 * len(LEVELS) - 1))


def print_metrics(labels, preds, title="", show_cm=True):
    n = len(labels)
    acc  = sum(1 for l, p in zip(labels, preds) if l == p) / n
    prf  = prf1_metrics(labels, preds)
    wf1  = weighted_f1(prf, labels)
    mf1  = macro_f1(prf)
    ord_acc = ordinal_accuracy(labels, preds)
    kappa   = cohen_kappa(labels, preds)

    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print(f"{'='*60}")

    print(f"  n={n}  Accuracy={acc:.0%}  Ordinal-acc={ord_acc:.0%}  Kappa={kappa:.2f}")
    print(f"  Weighted-F1={wf1:.2f}  Macro-F1={mf1:.2f}")

    print(f"\n  {'Class':<8} {'P':>6} {'R':>6} {'F1':>6} {'N':>5}")
    print(f"  {'-'*35}")
    for cls in LEVELS:
        d = prf[cls]
        print(f"  {cls:<8} {d['P']:>6.2f} {d['R']:>6.2f} {d['F1']:>6.2f} {d['support']:>5}")

    if show_cm:
        mat = confusion_matrix(labels, preds)
        print_confusion_matrix(mat, "  Confusion matrix (rows=actual, cols=predicted):")

    return {"acc": acc, "wf1": wf1, "mf1": mf1, "kappa": kappa, "ord": ord_acc}


# ---------------------------------------------------------------------------
# Auto-calibration demo
# ---------------------------------------------------------------------------

def demo_auto_calibration():
    print("\n" + "=" * 60)
    print("  Auto-calibration (click repo)")
    print("=" * 60)

    from src.risk.auto_calibrate import compute_auto_caps

    auto = compute_auto_caps(EVAL_REPO, EVAL_DB)
    caps = auto["normalization"]
    thresh = auto["thresholds"]

    print(f"  Derived caps (P90 of repo signal distribution):")
    for k, v in caps.items():
        print(f"    {k}: {v}")
    print(f"  Thresholds: low={thresh['low']}  high={thresh['high']}")
    print(f"\n  (Manual click caps were: blast=60 bug=15 churn=15 threshold_high=0.55)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    use_auto = "--auto" in sys.argv

    # -------- Dummy repo (calibration set) --------
    dummy_scenarios, dummy_root, dummy_db = _load_dummy_scenarios()
    dummy_labels, dummy_preds = [], []

    print("\nRunning dummy_repo scenarios...")
    for s in dummy_scenarios:
        changed = [str(dummy_root / s.changed_file)]  # _S has .changed_file (str)
        _, level = run_pipeline(changed, s.pr_author, s.pr_size_lines, dummy_root, dummy_db)
        dummy_labels.append(s.expected)
        dummy_preds.append(level)

    m_dummy = print_metrics(dummy_labels, dummy_preds,
                            "dummy_repo — calibration set (12 scenarios, default caps)")

    # -------- Click real-repo --------
    real_scenarios, real_root, real_db = _load_real_scenarios()

    click_config = None
    config_label = "dummy_repo caps (transfer test)"

    if use_auto:
        # Write auto-calibrated config to a temp path
        from src.risk.auto_calibrate import write_auto_config
        auto_path = ROOT / "config" / "risk_weights_click_auto.yaml"
        merged = write_auto_config(real_root, real_db, auto_path)
        click_config = auto_path
        config_label = "auto-calibrated caps"
        print(f"\nAuto-calibrated config written to {auto_path.name}")
    else:
        click_config = ROOT / "config" / "risk_weights_click.yaml"
        config_label = "manually-tuned click caps"

    real_labels, real_preds = [], []
    print(f"\nRunning click scenarios ({config_label})...")
    for s in real_scenarios:
        changed = [str(real_root / f) for f in s.changed_files]  # _R has .changed_files (list)
        _, level = run_pipeline(changed, s.pr_author, s.pr_size_lines, real_root, real_db,
                                click_config)
        real_labels.append(s.expected)
        real_preds.append(level)

    m_real = print_metrics(real_labels, real_preds,
                           f"click (pallets/click) — generalization set (10 PRs, {config_label})")

    # -------- Combined --------
    all_labels = dummy_labels + real_labels
    all_preds  = dummy_preds  + real_preds
    m_all = print_metrics(all_labels, all_preds, "COMBINED (22 scenarios)", show_cm=True)

    # -------- Summary table --------
    print(f"\n{'='*60}")
    print("  Final Summary")
    print(f"{'='*60}")
    print(f"  {'Dataset':<30} {'Acc':>6} {'W-F1':>6} {'Kappa':>7} {'Ord':>6}")
    print(f"  {'-'*55}")
    for label, m in [
        ("dummy_repo (calibration, n=12)", m_dummy),
        (f"click ({config_label}, n=10)", m_real),
        ("Combined (n=22)", m_all),
    ]:
        print(f"  {label:<30} {m['acc']:>6.0%} {m['wf1']:>6.2f} {m['kappa']:>7.2f} {m['ord']:>6.0%}")

    if not use_auto:
        demo_auto_calibration()
        print("\n  Run with --auto to use auto-calibrated caps instead of manual ones.")


if __name__ == "__main__":
    main()
