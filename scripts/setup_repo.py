"""
One-time repo setup for AI DevOps Assistant.

Run this once after cloning + building the KG. It:
  1. Builds (or rebuilds) the Knowledge Graph for this repo.
  2. Auto-calibrates normalization caps from repo signal distributions.
  3. Writes .code-review-graph/risk_weights.yaml — the pipeline
     automatically loads this on every subsequent run.

After this, `python run_review.py <PR_URL>` is plug-and-play.
Re-run any time the repo changes significantly (new modules, team growth).

Usage:
    python scripts/setup_repo.py [--repo PATH] [--rebuild]

    --repo PATH    path to the repo to configure (default: current dir)
    --rebuild      force full KG rebuild (default: incremental)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="One-time repo setup")
    parser.add_argument("--repo",    default=".", help="Path to target repo")
    parser.add_argument("--rebuild", action="store_true", help="Full KG rebuild")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    if not (repo_root / ".git").exists():
        print(f"ERROR: {repo_root} is not a git repository.")
        sys.exit(1)

    db_path    = repo_root / ".code-review-graph" / "graph.db"
    out_config = repo_root / ".code-review-graph" / "risk_weights.yaml"

    # ---- Step 1: Build / update KG ----
    print(f"[1/2] Building Knowledge Graph for {repo_root.name}...")
    from code_review_graph.tools.build import build_or_update_graph
    result = build_or_update_graph(
        full_rebuild=args.rebuild,
        repo_root=str(repo_root),
    )
    print(f"      nodes={result.get('total_nodes')}  "
          f"edges={result.get('total_edges')}")

    if not db_path.exists():
        print(f"ERROR: KG DB not found at {db_path}")
        sys.exit(1)

    # ---- Step 2: Auto-calibrate caps ----
    print("[2/2] Auto-calibrating normalization caps...")
    from src.risk.auto_calibrate import write_auto_config
    merged = write_auto_config(repo_root, db_path, out_config)

    caps   = merged["normalization"]
    thresh = merged["thresholds"]

    print(f"      max_blast_radius:      {caps['max_blast_radius']}")
    print(f"      max_bug_frequency:     {caps['max_bug_frequency']}")
    print(f"      max_contributor_churn: {caps['max_contributor_churn']}")
    print(f"      max_pr_size_lines:     {caps['max_pr_size_lines']}")
    print(f"      threshold low={thresh['low']}  high={thresh['high']}")
    print(f"\n      Config written to: {out_config.relative_to(repo_root)}")

    print("\n[OK] Setup complete.")
    print(f"     python run_review.py <PR_URL>  # uses auto-calibrated config")


if __name__ == "__main__":
    main()
