"""
Context-aware risk scoring engine — Week 8.

Formula (CHID paper + OWASP):
    risk = w1*norm(blast_radius_size)
         + w2*norm(coverage_gap_ratio)
         + w3*norm(bug_frequency)
         + w4*norm(contributor_churn)
         + w5*is_new_contributor
         + w6*norm(pr_size_lines)

Weights are configurable via config/risk_weights.yaml.
Output includes a human-readable breakdown for explainability.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RiskInput:
    """All signals needed to compute a risk score."""
    blast_radius_size:   int   = 0     # # files in blast radius
    coverage_gap_ratio:  float = 0.0   # uncovered / total blast radius
    bug_frequency:       int   = 0     # bug-fix commits in 90d on changed files
    contributor_churn:   int   = 0     # distinct authors in 90d
    is_new_contributor:  bool  = False # PR author never touched these files
    pr_size_lines:       int   = 0     # lines added + deleted in diff


@dataclass
class SignalBreakdown:
    name: str
    raw_value: Any
    normalized: float
    weight: float
    contribution: float

    def __str__(self) -> str:
        return (
            f"  {self.name:<22} raw={self.raw_value!s:<8} "
            f"norm={self.normalized:.2f}  w={self.weight:.2f}  "
            f"contrib={self.contribution:.3f}"
        )


@dataclass
class RiskResult:
    score: float
    level: str                              # "low" | "medium" | "high"
    breakdown: list[SignalBreakdown] = field(default_factory=list)

    def explanation(self) -> str:
        lines = [f"Risk: {self.level.upper()} ({self.score:.2f})", "Breakdown:"]
        lines += [str(s) for s in self.breakdown]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 3),
            "level": self.level,
            "breakdown": [
                {
                    "signal": s.name,
                    "raw": s.raw_value,
                    "normalized": round(s.normalized, 3),
                    "weight": s.weight,
                    "contribution": round(s.contribution, 3),
                }
                for s in self.breakdown
            ],
        }


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = Path(__file__).parent.parent.parent / "config" / "risk_weights.yaml"


class RiskScorer:
    def __init__(self, config_path: str | Path | None = None):
        cfg = self._load_config(config_path or _DEFAULT_CONFIG)
        w = cfg["risk_weights"]
        n = cfg["normalization"]
        t = cfg["thresholds"]

        self.weights = {
            "blast_radius":       w["blast_radius"],
            "coverage_gap":       w["coverage_gap"],
            "bug_frequency":      w["bug_frequency"],
            "contributor_churn":  w["contributor_churn"],
            "new_contributor":    w["new_contributor"],
            "pr_size":            w["pr_size"],
        }
        self.caps = {
            "blast_radius":      n["max_blast_radius"],
            "bug_frequency":     n["max_bug_frequency"],
            "contributor_churn": n["max_contributor_churn"],
            "pr_size":           n["max_pr_size_lines"],
        }
        self.threshold_low  = t["low"]
        self.threshold_high = t["high"]

    # ------------------------------------------------------------------

    def score(self, inp: RiskInput) -> RiskResult:
        def norm(value: float, cap: float) -> float:
            return min(value / cap, 1.0) if cap > 0 else 0.0

        signals = [
            SignalBreakdown(
                name="blast_radius_size",
                raw_value=inp.blast_radius_size,
                normalized=norm(inp.blast_radius_size, self.caps["blast_radius"]),
                weight=self.weights["blast_radius"],
                contribution=0.0,
            ),
            SignalBreakdown(
                name="coverage_gap_ratio",
                raw_value=f"{inp.coverage_gap_ratio:.0%}",
                normalized=min(inp.coverage_gap_ratio, 1.0),
                weight=self.weights["coverage_gap"],
                contribution=0.0,
            ),
            SignalBreakdown(
                name="bug_frequency",
                raw_value=inp.bug_frequency,
                normalized=norm(inp.bug_frequency, self.caps["bug_frequency"]),
                weight=self.weights["bug_frequency"],
                contribution=0.0,
            ),
            SignalBreakdown(
                name="contributor_churn",
                raw_value=inp.contributor_churn,
                normalized=norm(inp.contributor_churn, self.caps["contributor_churn"]),
                weight=self.weights["contributor_churn"],
                contribution=0.0,
            ),
            SignalBreakdown(
                name="new_contributor",
                raw_value=inp.is_new_contributor,
                normalized=1.0 if inp.is_new_contributor else 0.0,
                weight=self.weights["new_contributor"],
                contribution=0.0,
            ),
            SignalBreakdown(
                name="pr_size_lines",
                raw_value=inp.pr_size_lines,
                normalized=norm(inp.pr_size_lines, self.caps["pr_size"]),
                weight=self.weights["pr_size"],
                contribution=0.0,
            ),
        ]

        total = 0.0
        for s in signals:
            s.contribution = s.normalized * s.weight
            total += s.contribution

        total = round(min(total, 1.0), 3)
        level = (
            "low"    if total < self.threshold_low  else
            "high"   if total > self.threshold_high else
            "medium"
        )

        return RiskResult(score=total, level=level, breakdown=signals)

    # ------------------------------------------------------------------

    @staticmethod
    def _load_config(path: str | Path) -> dict:
        with open(path, "r") as f:
            return yaml.safe_load(f)
