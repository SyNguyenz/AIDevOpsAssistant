"""
Auto-calibration of normalization caps from repo statistics.

Strategy: caps = max(observed_signal) * 1.25
  - Gives 25% headroom above the highest signal seen in the repo.
  - The riskiest file normalizes to ~0.80 (not 1.0), preserving score
    differentiation between "very risky" and "somewhat risky".
  - Works for any repo size without a labeled calibration set.
  - Handles skewed distributions (most files have zero signals) better
    than percentile-based approaches.

Why NOT P90 of all files:
  Most files have bug_frequency=0. P90 across all files captures zeros
  and produces a cap of 1-2, which means any file with 3+ bug commits
  immediately hits the cap → everyone scores "high". max*1.25 avoids this.

Output: risk_weights YAML compatible with RiskScorer(config_path=...).
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_auto_caps(
    repo_root: str | Path,
    db_path: str | Path,
    lookback_days: int = 90,
) -> dict:
    """
    Scan all Python source files, compute blast radius + git signals,
    return normalization section with caps = max(signal) * 1.25.

    Returns dict with keys: normalization, thresholds.
    """
    from code_review_graph.graph import GraphStore
    from src.kg.git_enrichment import compute_file_stats

    repo_root = Path(repo_root)
    source_files = [
        str(p) for p in repo_root.rglob("*.py")
        if not _skip(p) and ".code-review-graph" not in str(p)
    ]

    if not source_files:
        return _fallback()

    # Blast radius for every source file
    blast_sizes: list[int] = []
    store = GraphStore(str(db_path))
    for f in source_files:
        try:
            b = store.get_impact_radius([f], max_depth=2)
            blast_sizes.append(len(b.get("impacted_files", [])))
        except Exception:
            blast_sizes.append(0)
    store.close()

    # Git signals
    git_stats = compute_file_stats(repo_root, source_files, lookback_days)
    bug_freqs = [s.bug_frequency    for s in git_stats.values()]
    churns    = [s.contributor_churn for s in git_stats.values()]

    def cap(values: list[int]) -> int:
        """max(values) * 1.25, minimum 1."""
        m = max(values) if values else 0
        return max(int(math.ceil(m * 1.25)), 1)

    caps = {
        "max_blast_radius":      cap(blast_sizes),
        "max_bug_frequency":     cap(bug_freqs),
        "max_contributor_churn": cap(churns),
        "max_pr_size_lines":     500,
    }

    return {
        "normalization": caps,
        "thresholds": {"low": 0.30, "high": 0.55},
    }


def write_auto_config(
    repo_root: str | Path,
    db_path: str | Path,
    output_path: str | Path,
    base_config: str | Path | None = None,
    lookback_days: int = 90,
) -> dict:
    """
    Write a complete risk_weights YAML with auto-calibrated caps.
    Weights are copied unchanged from base_config.
    Returns the merged config dict.
    """
    base_config = base_config or (
        Path(__file__).parent.parent.parent / "config" / "risk_weights.yaml"
    )
    with open(base_config) as f:
        base = yaml.safe_load(f)

    auto = compute_auto_caps(repo_root, db_path, lookback_days)

    merged = {
        "risk_weights": base["risk_weights"],
        "normalization": auto["normalization"],
        "thresholds":    auto["thresholds"],
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.dump(merged, f, default_flow_style=False, sort_keys=False)

    return merged


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _skip(p: Path) -> bool:
    n = p.name
    return n.startswith("test_") or n.endswith("_test.py") or n == "__init__.py"


def _fallback() -> dict:
    return {
        "normalization": {
            "max_blast_radius": 8,
            "max_bug_frequency": 5,
            "max_contributor_churn": 5,
            "max_pr_size_lines": 500,
        },
        "thresholds": {"low": 0.30, "high": 0.55},
    }
