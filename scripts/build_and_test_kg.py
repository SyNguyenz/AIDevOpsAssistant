"""
Build KG on dummy_repo, enrich with git history, test blast radius query.

Usage:
    python scripts/build_and_test_kg.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REPO_PATH = ROOT / "dummy_repo"
DB_PATH = REPO_PATH / ".code-review-graph" / "graph.db"

os.environ["CRG_REPO_ROOT"] = str(REPO_PATH)


def step1_build_kg():
    print("=== Step 1: Build Knowledge Graph ===")
    from code_review_graph.tools.build import build_or_update_graph
    result = build_or_update_graph(full_rebuild=True, repo_root=str(REPO_PATH))
    print(f"  Status    : {result['status']}")
    print(f"  Files     : {result.get('files_parsed', result.get('files_updated', '?'))}")
    print(f"  Nodes     : {result.get('total_nodes', '?')}")
    print(f"  Edges     : {result.get('total_edges', '?')}")


def step2_blast_radius():
    print("\n=== Step 2: Blast Radius Query ===")
    from code_review_graph.graph import GraphStore
    store = GraphStore(str(DB_PATH))

    changed = [str(REPO_PATH / "src" / "auth.py")]
    print(f"  Changed files: {['src/auth.py']}")
    impact = store.get_impact_radius(changed, max_depth=2)

    print(f"  Impacted files ({len(impact['impacted_files'])}):")
    for f in sorted(impact["impacted_files"]):
        print(f"    - {f}")
    print(f"  Total impacted nodes: {impact['total_impacted']}")
    store.close()


def step3_git_enrichment():
    print("\n=== Step 3: Git History Enrichment ===")
    from src.kg.git_enrichment import enrich_graph
    stats = enrich_graph(DB_PATH, REPO_PATH)

    for path, s in sorted(stats.items()):
        print(f"  {path}")
        print(f"    bug_freq={s.bug_frequency}  churn={s.contributor_churn}  velocity={s.change_velocity}  last={s.last_modifier}")


def step4_verify_db():
    print("\n=== Step 4: Verify enriched data in SQLite ===")
    import sqlite3, json
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT file_path, extra FROM nodes WHERE kind='File' ORDER BY file_path"
    ).fetchall()
    conn.close()

    for file_path, extra_json in rows:
        extra = json.loads(extra_json or "{}")
        git = extra.get("git")
        if git:
            print(f"  {file_path}: bug={git['bug_frequency']} churn={git['contributor_churn']} vel={git['change_velocity']}")
        else:
            print(f"  {file_path}: [no git data]")


if __name__ == "__main__":
    if not REPO_PATH.exists():
        print("ERROR: dummy_repo not found. Run: python scripts/create_dummy_repo.py")
        sys.exit(1)
    step1_build_kg()
    step2_blast_radius()
    step3_git_enrichment()
    step4_verify_db()
    print("\n[OK] Week 5 milestone: KG built + git history enriched")
