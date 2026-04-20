"""
Git history enrichment for Knowledge Graph nodes.

Computes per-file signals used in risk scoring:
  - bug_frequency:      # commits with fix/bug/hotfix keywords in last N days
  - contributor_churn:  # distinct authors in last N days
  - change_velocity:    # total commits in last N days
  - last_modifier:      author of most recent commit on this file
  - is_pr_author_new:   True if PR author has never touched this file before

All signals are stored in the `extra` JSON column of the `nodes` table
(File-kind nodes only).
"""

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from git import Repo
from git.exc import InvalidGitRepositoryError

BUG_KEYWORDS = {"fix", "bug", "hotfix", "patch", "repair", "resolve", "revert"}
LOOKBACK_DAYS = 90


@dataclass
class FileGitStats:
    file_path: str
    bug_frequency: int = 0
    contributor_churn: int = 0
    change_velocity: int = 0
    last_modifier: str = ""
    all_authors: list[str] = field(default_factory=list)


def _is_bug_commit(message: str) -> bool:
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in BUG_KEYWORDS)


def compute_file_stats(
    repo_path: str | Path,
    file_paths: list[str],
    lookback_days: int = LOOKBACK_DAYS,
) -> dict[str, FileGitStats]:
    """
    Query git log for each file and compute history signals.

    Args:
        repo_path: Path to the git repository root.
        file_paths: List of relative file paths to analyse.
        lookback_days: How many days back to look.

    Returns:
        Dict mapping file_path → FileGitStats.
    """
    try:
        repo = Repo(str(repo_path), search_parent_directories=True)
    except InvalidGitRepositoryError:
        return {}

    cutoff = datetime.now() - timedelta(days=lookback_days)
    results: dict[str, FileGitStats] = {}

    repo_root = Path(repo.working_tree_dir)

    for rel_path in file_paths:
        stats = FileGitStats(file_path=rel_path)
        all_authors: list[str] = []
        last_modifier = ""
        last_commit_date = None

        # iter_commits needs repo-relative path with forward slashes
        abs_path = Path(rel_path)
        if abs_path.is_absolute():
            git_path = abs_path.relative_to(repo_root).as_posix()
        else:
            git_path = Path(rel_path).as_posix()

        try:
            commits = list(repo.iter_commits(paths=git_path))
        except Exception:
            results[rel_path] = stats
            continue

        for commit in commits:
            commit_date = datetime.fromtimestamp(commit.committed_date)
            author = commit.author.name or commit.author.email or "unknown"

            # Track last modifier (most recent commit overall)
            if last_commit_date is None or commit_date > last_commit_date:
                last_modifier = author
                last_commit_date = commit_date

            # Only count signals within lookback window
            if commit_date < cutoff:
                continue

            all_authors.append(author)
            stats.change_velocity += 1
            if _is_bug_commit(commit.message):
                stats.bug_frequency += 1

        stats.contributor_churn = len(set(all_authors))
        stats.last_modifier = last_modifier
        stats.all_authors = list(set(all_authors))
        results[rel_path] = stats

    return results


def is_new_contributor(
    repo_path: str | Path,
    file_paths: list[str],
    pr_author: str,
) -> bool:
    """
    Return True if pr_author has never committed to ANY of the given files.
    """
    try:
        repo = Repo(str(repo_path), search_parent_directories=True)
    except InvalidGitRepositoryError:
        return True

    for rel_path in file_paths:
        try:
            commits = list(repo.iter_commits(paths=rel_path))
        except Exception:
            continue
        for commit in commits:
            author = commit.author.name or commit.author.email or ""
            if author.lower() == pr_author.lower():
                return False
    return True


def enrich_graph(
    db_path: str | Path,
    repo_path: str | Path,
    lookback_days: int = LOOKBACK_DAYS,
) -> dict[str, FileGitStats]:
    """
    Read File nodes from the KG SQLite DB, compute git history signals,
    and write them back into the `extra` JSON column.

    Returns the computed stats dict for inspection/testing.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"KG database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))

    # Get all File-kind nodes
    rows = conn.execute(
        "SELECT qualified_name, file_path, extra FROM nodes WHERE kind = 'File'"
    ).fetchall()

    if not rows:
        conn.close()
        return {}

    file_paths = [r[1] for r in rows]
    stats_map = compute_file_stats(repo_path, file_paths, lookback_days)

    # Write enriched data back to extra column
    for qualified_name, file_path, extra_json in rows:
        stats = stats_map.get(file_path)
        if stats is None:
            continue

        try:
            extra = json.loads(extra_json or "{}")
        except json.JSONDecodeError:
            extra = {}

        extra["git"] = {
            "bug_frequency":     stats.bug_frequency,
            "contributor_churn": stats.contributor_churn,
            "change_velocity":   stats.change_velocity,
            "last_modifier":     stats.last_modifier,
            "all_authors":       stats.all_authors,
            "lookback_days":     lookback_days,
        }

        conn.execute(
            "UPDATE nodes SET extra = ? WHERE qualified_name = ?",
            (json.dumps(extra), qualified_name),
        )

    conn.commit()
    conn.close()
    return stats_map
