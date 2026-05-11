"""
Risk-aware PR review tool — Week 9 + Phase 4 (CI-aware).

Orchestrates the full pipeline:
  1. Build/update KG for changed files
  2. Query blast radius
  3. Enrich with git history
  4. Compute coverage gap
  5. Score risk
  6. (Phase 4) Read CI status + parse failed tests + KG cross-reference
  7. Build context-aware LLM prompt
  8. Post review comment via PR-Agent

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
from src.server.ci_analyzer import FailureLink, build_ci_section, cross_reference_failures
from src.server.ci_reader import CIReader, CIStatus, FailedTest

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
    head_sha: str = "",
    github_token: str = "",
) -> dict:
    """
    Run the full risk + CI pipeline for a PR.

    Returns dict with: risk_result, blast_radius, coverage, git_stats,
                       ci_status, failed_tests, ci_links
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

    # 6. CI-aware analysis (Phase 4)
    ci_status: CIStatus | None = None
    failed_tests: list[FailedTest] = []
    ci_links: list[FailureLink] = []

    token = github_token or os.environ.get("GITHUB_TOKEN", "")
    if token and head_sha:
        repo_name = _extract_repo_name(pr_url)
        if repo_name:
            try:
                reader = CIReader(token, repo_name)
                ci_status = reader.get_pr_ci_status(head_sha)
                if ci_status and ci_status.conclusion == "failure":
                    failed_tests = reader.get_failed_tests(ci_status.run_id)
                    ci_links = cross_reference_failures(
                        failed_tests, changed_files, impacted_files
                    )
                    logger.info(
                        f"CI: {len(failed_tests)} failed tests, "
                        f"{len(ci_links)} linked to blast radius"
                    )
            except Exception as exc:
                logger.warning(f"CI analysis failed (non-fatal): {exc}")

    return {
        "risk_result":    risk_result,
        "blast_radius":   blast,
        "coverage":       cov,
        "git_stats":      git_stats,
        "changed_files":  changed_files,
        "impacted_files": impacted_files,
        "ci_status":      ci_status,
        "failed_tests":   failed_tests,
        "ci_links":       ci_links,
    }


def _extract_repo_name(pr_url: str) -> str:
    """Extract 'owner/repo' from a GitHub PR URL."""
    import re
    m = re.search(r"github\.com/([^/]+/[^/]+)/pull/", pr_url)
    return m.group(1) if m else ""


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
            "These files in the blast radius have no test coverage:",
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

    # Phase 4: CI section
    ci_section = build_ci_section(
        pipeline_output.get("ci_status"),
        pipeline_output.get("failed_tests", []),
        pipeline_output.get("ci_links", []),
    )
    if ci_section:
        lines.append(ci_section)

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

        # Resolve head SHA for CI lookup
        head_sha = self._resolve_head_sha()

        # Run risk pipeline (includes CI analysis if token + head SHA available)
        pipeline = await run_risk_pipeline(
            self.pr_url,
            head_sha=head_sha,
            github_token=os.environ.get("GITHUB_TOKEN", ""),
        )

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

    def _resolve_head_sha(self) -> str:
        """Try to get the PR's head SHA via git_provider."""
        try:
            git_provider = get_git_provider(self.pr_url)
            # PR-Agent exposes last_commit_id on most providers
            return git_provider.last_commit_id or ""
        except Exception:
            return ""

    async def _post_risk_comment(self, pipeline: dict):
        from pr_agent.git_providers import get_git_provider_with_context
        git_provider = get_git_provider_with_context(self.pr_url)
        body = build_risk_prompt(pipeline)
        git_provider.publish_comment(body)
        logger.info("Posted risk summary comment")
