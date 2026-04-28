"""
Risk-aware PR review tool — Week 9.

Orchestrates the full pipeline:
  1. Build/update KG for changed files
  2. Query blast radius
  3. Enrich with git history
  4. Compute coverage gap
  5. Score risk
  6. Build context-aware LLM prompt
  7. Post review comment via PR-Agent

Registered as command "risk_review" in PR-Agent's command2class dispatcher.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
from pr_agent.log import get_logger

from src.kg.coverage_mapper import compute_coverage_gap
from src.kg.git_enrichment import compute_file_stats, is_new_contributor
from src.risk.scorer import RiskInput, RiskScorer

logger = get_logger()

_scorer = RiskScorer()

# ---------------------------------------------------------------------------
# KG helpers (thin wrappers so the tool doesn't import build at module level)
# ---------------------------------------------------------------------------

def _get_repo_root(pr_url: str) -> Path | None:
    """Try to find local repo root matching the PR's repo."""
    cwd = Path.cwd()
    if (cwd / ".git").exists():
        return cwd
    return None


def _build_kg(repo_root: Path, changed_files: list[str]) -> Any:
    """Incremental KG build for changed files, return GraphStore."""
    from code_review_graph.graph import GraphStore
    from code_review_graph.tools.build import build_or_update_graph

    build_or_update_graph(full_rebuild=False, repo_root=str(repo_root))
    db_path = repo_root / ".code-review-graph" / "graph.db"
    return GraphStore(str(db_path))


def _get_blast_radius(store: Any, changed_files: list[str]) -> dict:
    return store.get_impact_radius(changed_files, max_depth=2)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_risk_pipeline(
    pr_url: str,
    repo_root: Path | None = None,
    pr_author: str = "",
    pr_size_lines: int = 0,
) -> dict:
    """
    Run the full risk pipeline for a PR.

    Returns dict with: risk_result, blast_radius, coverage, git_stats, prompt_context
    """
    # Resolve repo root
    if repo_root is None:
        repo_root = _get_repo_root(pr_url)
    if repo_root is None:
        logger.warning("Cannot find local repo root — skipping KG analysis")
        return {}

    # Get changed files from PR
    git_provider = get_git_provider(pr_url)
    diff_files = git_provider.get_files()
    changed_files = [
        str(repo_root / f.filename) for f in diff_files
        if f.filename.endswith(".py")
    ]

    if not changed_files:
        return {"risk_result": _scorer.score(RiskInput()), "note": "no Python files changed"}

    # 1. Build KG + blast radius
    store = _build_kg(repo_root, changed_files)
    blast = _get_blast_radius(store, changed_files)
    store.close()
    impacted_files: list[str] = blast.get("impacted_files", [])
    all_files = list(set(changed_files) | set(impacted_files))

    # 2. Git history enrichment
    git_stats = compute_file_stats(repo_root, changed_files)
    bug_freq  = max((s.bug_frequency    for s in git_stats.values()), default=0)
    churn     = max((s.contributor_churn for s in git_stats.values()), default=0)

    # 3. Coverage gap
    cov = compute_coverage_gap(all_files, repo_root)

    # 4. New contributor check
    new_contrib = is_new_contributor(repo_root, changed_files, pr_author) if pr_author else False

    # 5. Risk score
    inp = RiskInput(
        blast_radius_size  = len(impacted_files),
        coverage_gap_ratio = cov["coverage_gap_ratio"],
        bug_frequency      = bug_freq,
        contributor_churn  = churn,
        is_new_contributor = new_contrib,
        pr_size_lines      = pr_size_lines,
    )
    risk_result = _scorer.score(inp)

    return {
        "risk_result":     risk_result,
        "blast_radius":    blast,
        "coverage":        cov,
        "git_stats":       git_stats,
        "changed_files":   changed_files,
        "impacted_files":  impacted_files,
    }


def build_risk_prompt(pipeline_output: dict) -> str:
    """Build a structured context string to prepend to the LLM review prompt."""
    if not pipeline_output or "risk_result" not in pipeline_output:
        return ""

    risk  = pipeline_output["risk_result"]
    cov   = pipeline_output.get("coverage", {})
    blast = pipeline_output.get("blast_radius", {})

    uncovered = cov.get("uncovered", [])
    uncovered_names = [Path(f).name for f in uncovered]

    lines = [
        "## Risk Analysis",
        f"**Risk Level:** {risk.level.upper()} (score: {risk.score:.2f})",
        "",
        "### Signal Breakdown",
        "```",
        risk.explanation(),
        "```",
        "",
    ]

    if uncovered_names:
        lines += [
            "### Coverage Gap",
            f"These files in the blast radius have no test coverage:",
            "".join(f"\n- `{f}`" for f in uncovered_names),
            "",
        ]

    impacted = blast.get("impacted_files", [])
    if impacted:
        lines += [
            "### Blast Radius",
            f"{len(impacted)} files affected by this change:",
            "".join(f"\n- `{Path(f).name}`" for f in impacted[:10]),
            "",
        ]

    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PR-Agent Tool class (plugs into command2class)
# ---------------------------------------------------------------------------

class PRRiskReview:
    """
    PR-Agent tool: /risk_review

    Runs risk pipeline then delegates to standard PRReviewer with
    risk context injected into the prompt.
    """

    def __init__(self, pr_url: str, ai_handler=None, args=None):
        self.pr_url = pr_url
        self.ai_handler = ai_handler
        self.args = args or []

    async def run(self):
        from pr_agent.tools.pr_reviewer import PRReviewer

        logger.info(f"Running risk-aware review for {self.pr_url}")

        # Run risk pipeline
        pipeline = await run_risk_pipeline(self.pr_url)

        if pipeline:
            risk = pipeline["risk_result"]
            logger.info(f"Risk score: {risk.score:.2f} ({risk.level})")

            # Inject risk context as extra instructions for LLM
            risk_context = build_risk_prompt(pipeline)
            current = get_settings().pr_reviewer.get("extra_instructions", "")
            get_settings().pr_reviewer.extra_instructions = (
                risk_context + "\n\n" + current if current else risk_context
            )

        # Delegate to standard reviewer
        reviewer = PRReviewer(self.pr_url, ai_handler=self.ai_handler, args=self.args)
        await reviewer.run()

        # Post risk summary as separate comment if medium/high
        if pipeline and pipeline["risk_result"].level in ("medium", "high"):
            await self._post_risk_comment(pipeline)

    async def _post_risk_comment(self, pipeline: dict):
        from pr_agent.git_providers import get_git_provider_with_context
        git_provider = get_git_provider_with_context(self.pr_url)
        risk = pipeline["risk_result"]
        body = build_risk_prompt(pipeline)
        git_provider.publish_comment(body)
        logger.info("Posted risk summary comment")
