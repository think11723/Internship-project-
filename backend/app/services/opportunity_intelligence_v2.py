"""Sprint 12 — Opportunity Intelligence v2 (Ranking & Portfolio).

A pure-deterministic, additive module that produces, per company:

  - opportunity_score      (0-100, distinct from Sprint 7 score
                             and from Sprint 11 recommendation
                             confidence; see scoring matrix)
  - opportunity_rank        (1-based, global rank across the input list)
  - opportunity_tier         ("S" | "A" | "B" | "C" | "D")
  - opportunity_summary      (single sentence)
  - opportunity_strengths   (3-5 evidence-grounded bullets)
  - opportunity_risks        (3-5 evidence-grounded bullets)
  - estimated_roi           ("Low" | "Medium" | "High")
  - estimated_time_to_apply (minutes, int)
  - recommended_application_order (1-based, matches opportunity_rank)

Also produces a portfolio-level summary across the input list
(top tier, top 3 this week, top 10 overall, low priority, do-not-apply).

This module reads from the (frozen) Recommendation Engine v11 and the
(frozen) opportunity_intelligence. It does not modify their logic. It
introduces a NEW signal: "is this opportunity worth the candidate's
time RIGHT NOW" — distinct from "does the candidate match the role".

LLM may only improve wording via the existing AIGateway. The score is
deterministic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("fundflow.opportunity_v2")


# ─── Opportunity tiers ────────────────────────────────────────────────────

TIER_THRESHOLDS = (
    (80, "S"),
    (65, "A"),
    (50, "B"),
    (30, "C"),
    (0,  "D"),
)


def _score_to_tier(score: int) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return "D"


# ─── Recommendation-engine strategy → opportunity modifier ────────────────

_STRATEGY_BONUS = {
    "Apply Immediately":            +5,
    "Apply This Week":               +3,
    "Connect on LinkedIn First":      0,
    "Cold Email Founder":             0,
    "Monitor Hiring":                -3,
    "Wait Until Next Funding Round":  -2,
    "Build Missing Skills First":    -5,
    "Gain More Experience":          -4,
    "Track Future Openings":         0,
    "Not Recommended":              -10,
}


# ─── Funding recency signal ──────────────────────────────────────────────

def _funding_recency_score(fr: str) -> int:
    """0-15. Series A fresh is the peak; late-stage rounds score lower
    because the company is already well-funded."""
    f = (fr or "").lower()
    if "pre-seed" in f or "preseed" in f:
        return 8
    if "seed" in f:
        return 12
    if "series a" in f:
        return 15
    if "series b" in f:
        return 12
    if "series c" in f:
        return 9
    if "series d" in f or "series e" in f or "series f" in f:
        return 6
    return 0


# ─── Hiring activity signal ──────────────────────────────────────────────

def _hiring_activity_score(status: str, open_count: int) -> int:
    s = (status or "").strip().lower()
    if s == "actively_hiring":
        if open_count >= 5:
            return 20
        if open_count >= 1:
            return 15
        return 10
    if s == "hiring":
        return 7
    if s == "not_hiring":
        return -15
    return 0


# ─── Open positions signal ────────────────────────────────────────────────

def _open_positions_score(open_count: int) -> int:
    """0-10. More open roles = more surface area for the candidate."""
    if open_count >= 5:
        return 10
    if open_count >= 3:
        return 8
    if open_count >= 1:
        return 5
    return 0


# ─── Career growth signal (smaller = more growth potential) ────────────

def _career_growth_score(size: str) -> int:
    """0-5. Smaller teams give more scope; large companies give stability."""
    s = (size or "").strip()
    if "1-10" in s:
        return 5
    if "11-50" in s:
        return 4
    if "51-200" in s:
        return 3
    if "201-500" in s:
        return 2
    if any(x in s for x in ("501-1,000", "1,001-5,000")):
        return 1
    if any(x in s for x in ("5,001-10,000", "10,001+")):
        return 0
    return 2  # unknown


# ─── Engineering culture signal ──────────────────────────────────────────

def _culture_score(culture_indicators: List[str]) -> int:
    """0-5. Reward fast-growing/well-funded/remote-first/open-source signals."""
    good = {"fast-growing", "well-funded", "remote-first", "open-source"}
    score = 0
    for c in culture_indicators or []:
        if isinstance(c, str) and c.lower() in good:
            score += 2
        elif isinstance(c, str) and c.lower() in {"profitable", "bootstrapped"}:
            score += 1
    return min(5, score)


# ─── Expected ROI ────────────────────────────────────────────────────────

def _expected_roi(tier: str, strategy: str) -> str:
    if tier in ("S", "A") and strategy in (
        "Apply Immediately", "Apply This Week",
    ):
        return "High"
    if tier in ("S", "A"):
        return "Medium"
    if tier in ("B",):
        return "Medium"
    return "Low"


# ─── Time-to-apply estimate ─────────────────────────────────────────────

def _time_to_apply_minutes(
    company_size: str, open_count: int, has_resume: bool,
) -> int:
    """Estimated minutes the candidate will spend applying."""
    if not has_resume:
        return 0
    base = 25  # base: tailor resume, write cover letter, submit
    if "1-10" in company_size or "11-50" in company_size:
        base += 10  # more personalization for small team
    if open_count >= 3:
        base += 5  # choosing which role
    return min(120, base)


# ─── Main scoring function ──────────────────────────────────────────────

def compute_opportunity_score(
    resume: Optional[Dict[str, Any]],
    enrichment: Dict[str, Any],
    jobs: List[Dict[str, Any]],
    scores: Dict[str, int],
    recommendation: Optional[Dict[str, Any]] = None,
    candidate_skills: Optional[set] = None,
) -> Dict[str, Any]:
    """Return the breakdown of the Opportunity Score.

    The Opportunity Score is a distinct metric from Sprint 7's
    ``opportunity_score`` and Sprint 11's ``intelligence.confidence``.
    It measures "should the candidate act on this opportunity RIGHT
    NOW", not "do the candidate's skills match the role".
    """
    if candidate_skills is None:
        candidate_skills = set()
        if resume:
            for f in ("skills", "technologies", "programming_languages",
                      "frameworks", "cloud", "databases", "tools"):
                for s in (resume.get(f) or []):
                    v = (s or "").strip().lower()
                    if v:
                        candidate_skills.add(v)

    score = 0

    # 1. Resume match (0-25)
    tech_fit = int(scores.get("technical_fit") or 0)
    overall = int(scores.get("overall_fit") or 0)
    score += int(round((max(tech_fit, overall) * 0.25)))

    # 2. Hiring activity (-15 to +20)
    open_count = int(enrichment.get("open_positions_count") or 0)
    score += _hiring_activity_score(
        enrichment.get("hiring_status_detailed") or "", open_count
    )

    # 3. Funding recency (0-15)
    fr = enrichment.get("funding_round") or ""
    score += _funding_recency_score(fr)

    # 4. Open positions volume (0-10)
    score += _open_positions_score(open_count)

    # 5. Remote friendliness (0 to +5)
    wm = (enrichment.get("work_mode") or "").strip().lower()
    if wm == "remote":
        score += 5
    elif wm == "hybrid":
        score += 2
    # onsite / unknown: 0

    # 6. Visa support (-5 to +5)
    visa = enrichment.get("visa_sponsorship_mentioned")
    if visa is True:
        score += 5
    elif visa is False:
        score -= 5

    # 7. Career growth (0-5)
    size = enrichment.get("employee_count_bracket") or ""
    score += _career_growth_score(size)

    # 8. Engineering culture (0-5)
    score += _culture_score(enrichment.get("engineering_culture_indicators") or [])

    # 9. Recommendation-engine strategy modifier
    if recommendation is not None:
        strategy = (recommendation.get("strategy") or "")
        score += _STRATEGY_BONUS.get(strategy, 0)

    # 10. Internship / graduate friendliness (0 to +3)
    if (enrichment.get("internship_friendly") is True
            or enrichment.get("graduate_friendly") is True):
        if resume is None:
            score += 0  # no resume = bonus moot
        else:
            # If candidate has little experience, the bonus is higher
            import re
            yrs_raw = resume.get("years_of_experience") or ""
            m = re.search(r"(\d+)", str(yrs_raw))
            yrs = int(m.group(1)) if m else 99
            if yrs <= 2:
                score += 3
            elif yrs <= 4:
                score += 1

    return {
        "score": max(0, min(100, score)),
        "tier": _score_to_tier(max(0, min(100, score))),
        "signal_breakdown": {
            "resume_match": int(round(max(tech_fit, overall) * 0.25)),
            "hiring_activity": _hiring_activity_score(
                enrichment.get("hiring_status_detailed") or "", open_count
            ),
            "funding_recency": _funding_recency_score(fr),
            "open_positions": _open_positions_score(open_count),
            "remote_friendliness": 5 if wm == "remote" else (2 if wm == "hybrid" else 0),
            "visa_support": (5 if visa is True else (-5 if visa is False else 0)),
            "career_growth": _career_growth_score(size),
            "engineering_culture": _culture_score(
                enrichment.get("engineering_culture_indicators") or []
            ),
            "strategy_modifier": (
                _STRATEGY_BONUS.get(recommendation.get("strategy", ""), 0)
                if recommendation else 0
            ),
            "internship_or_graduate_bonus": (
                3 if (enrichment.get("internship_friendly")
                      or enrichment.get("graduate_friendly")) else 0
            ),
        },
    }


# ─── Strengths / risks / summary builders ────────────────────────────────

def _build_strengths(
    tier: str, strategy: str, enrichment: Dict[str, Any],
    jobs: List[Dict[str, Any]], candidate_skills: set,
) -> List[str]:
    out: List[str] = []
    fr = enrichment.get("funding_round") or "—"
    fa = enrichment.get("funding_amount") or ""
    if fa:
        out.append(f"Recently funded ({fr}, {fa})")
    else:
        out.append(f"Recently funded ({fr})")
    status = enrichment.get("hiring_status_detailed") or ""
    open_count = int(enrichment.get("open_positions_count") or 0)
    if status == "actively_hiring":
        out.append(
            f"Actively hiring right now ({open_count} open roles)"
        )
    if (enrichment.get("work_mode") or "").lower() == "remote":
        out.append("Remote-friendly — no relocation barrier")
    if enrichment.get("visa_sponsorship_mentioned") is True:
        out.append("Visa sponsorship available")
    required = set()
    for j in jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip().lower()
            if v:
                required.add(v)
    if required:
        overlap = required & candidate_skills
        if len(overlap) >= 3:
            out.append(
                f"Strong skill match ({len(overlap)} of "
                f"{len(required)} required skills already on your resume)"
            )
    if strategy in ("Apply Immediately", "Apply This Week"):
        out.append(f"Recommended action right now: {strategy}")
    return out[:5]


def _build_risks(
    tier: str, strategy: str, enrichment: Dict[str, Any],
    jobs: List[Dict[str, Any]], candidate_skills: set,
) -> List[str]:
    out: List[str] = []
    if enrichment.get("visa_sponsorship_mentioned") is False:
        out.append("Visa sponsorship not supported (relocation may be required)")
    required = set()
    for j in jobs or []:
        for s in (j.get("skills") or []):
            v = (s or "").strip().lower()
            if v:
                required.add(v)
    missing = len(required - candidate_skills) if required else 0
    if missing >= 4:
        out.append(
            f"Large skill gap: {missing} required skills not on your resume"
        )
    if (enrichment.get("work_mode") or "").lower() == "onsite":
        out.append("Onsite only — relocation required")
    if enrichment.get("hiring_status_detailed") == "not_hiring":
        out.append("Not currently hiring")
    if strategy in ("Build Missing Skills First", "Gain More Experience"):
        out.append("Resume not yet strong enough for this role")
    if tier == "D":
        out.append("Overall low fit — likely waste of time")
    return out[:5]


def _build_summary(tier: str, strategy: str, score: int) -> str:
    if tier == "S":
        return f"Apply now (score {score}/100): high match + actively hiring + recent funding"
    if tier == "A":
        return f"Strong opportunity (score {score}/100): apply this week"
    if tier == "B":
        return f"Medium opportunity (score {score}/100): worth a tailored application"
    if tier == "C":
        return f"Weak opportunity (score {score}/100): monitor or deprioritise"
    return f"Low priority (score {score}/100): not worth the time right now"


# ─── Ranking ───────────────────────────────────────────────────────────

def rank_opportunities(
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rank a list of pre-computed opportunity dicts by score (desc),
    preserving stable order on ties. Mutates and returns the list.

    Each input item must have ``opportunity_score`` (int) and
    ``name`` (str) and the rest of the new fields.
    """
    items_sorted = sorted(
        items,
        key=lambda x: (-int(x.get("opportunity_score") or 0), x.get("name") or ""),
    )
    for i, item in enumerate(items_sorted, start=1):
        item["opportunity_rank"] = i
        # recommended_application_order matches opportunity_rank
        # unless the strategy explicitly says "wait" (then it gets a
        # higher number, indicating "act later").
        s = item.get("opportunity_recommendation_strategy") or ""
        if "Wait" in s or "Track" in s or "Monitor" in s or "Build" in s:
            item["recommended_application_order"] = 100 + i
        elif "Gain" in s:
            item["recommended_application_order"] = 200 + i
        elif s == "Not Recommended":
            item["recommended_application_order"] = 1000 + i
        else:
            item["recommended_application_order"] = i
    return items_sorted


# ─── Per-company full record ────────────────────────────────────────────

def build_opportunity_record(
    company: Dict[str, Any],
    resume: Optional[Dict[str, Any]],
    enrichment: Optional[Dict[str, Any]] = None,
    jobs: Optional[List[Dict[str, Any]]] = None,
    scores: Optional[Dict[str, int]] = None,
    recommendation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a full per-company Opportunity Intelligence v2 record."""
    enrichment = enrichment or {}
    jobs = jobs or []
    scores = scores or {}

    if resume is None:
        candidate_skills = set()
    else:
        candidate_skills = set()
        for f in ("skills", "technologies", "programming_languages",
                  "frameworks", "cloud", "databases", "tools"):
            for s in (resume.get(f) or []):
                v = (s or "").strip().lower()
                if v:
                    candidate_skills.add(v)

    breakdown = compute_opportunity_score(
        resume=resume,
        enrichment=enrichment,
        jobs=jobs,
        scores=scores,
        recommendation=recommendation,
        candidate_skills=candidate_skills,
    )
    score = breakdown["score"]
    tier = breakdown["tier"]
    strategy = ""
    if recommendation:
        strategy = recommendation.get("strategy") or ""

    return {
        "opportunity_score": score,
        "opportunity_tier": tier,
        "opportunity_summary": _build_summary(tier, strategy, score),
        "opportunity_strengths": _build_strengths(
            tier, strategy, enrichment, jobs, candidate_skills
        ),
        "opportunity_risks": _build_risks(
            tier, strategy, enrichment, jobs, candidate_skills
        ),
        "estimated_roi": _expected_roi(tier, strategy),
        "estimated_time_to_apply": _time_to_apply_minutes(
            enrichment.get("employee_count_bracket") or "",
            int(enrichment.get("open_positions_count") or 0),
            resume is not None,
        ),
        "opportunity_recommendation_strategy": strategy,
        "opportunity_score_signal_breakdown": breakdown["signal_breakdown"],
    }


# ─── Portfolio-level summary ──────────────────────────────────────────

def build_portfolio_summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a ranked list of opportunity records into a portfolio
    summary suitable for a dashboard header.
    """
    excellent = sum(1 for i in items if i.get("opportunity_tier") in ("S", "A"))
    medium = sum(1 for i in items if i.get("opportunity_tier") == "B")
    long_term = sum(1 for i in items if i.get("opportunity_tier") in ("C", "D"))
    do_not_apply = sum(
        1 for i in items if i.get("opportunity_recommendation_strategy") == "Not Recommended"
    )
    top_today = [
        i for i in items
        if i.get("opportunity_tier") in ("S", "A")
        and i.get("opportunity_recommendation_strategy") in (
            "Apply Immediately", "Apply This Week",
        )
    ]
    top_three = [
        i for i in items
        if i.get("opportunity_recommendation_strategy") in (
            "Apply Immediately", "Apply This Week", "Cold Email Founder",
        )
    ][:3]
    top_ten = items[:10]

    def _names(cs):
        return [c.get("name") for c in cs]

    text = (
        f"You currently have "
        f"{excellent} excellent opportunities, "
        f"{medium} medium opportunities, "
        f"{long_term} long-term opportunities"
    )
    if do_not_apply:
        text += f", and {do_not_apply} companies marked Do Not Apply"

    return {
        "text": text,
        "excellent_count": excellent,
        "medium_count": medium,
        "long_term_count": long_term,
        "do_not_apply_count": do_not_apply,
        "top_today_names": _names(top_today),
        "top_three_names": _names(top_three),
        "top_ten_names": _names(top_ten),
        "total_companies": len(items),
    }


# ─── Application queue ────────────────────────────────────────────────

def build_application_queue(
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Return a recommended application queue ordered by
    ``recommended_application_order`` (1 = first to act on).
    """
    return sorted(items, key=lambda x: x.get("recommended_application_order", 9999))


# ─── Convenience: tie it all together ──────────────────────────────────

def enrich_companies_with_opportunity(
    company_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Take a list of company records (each containing ``recommendation``
    and ``scores`` and a ``enrichment`` sub-dict) and produce a ranked,
    opportunity-tagged list. Mutates the records in place.
    """
    # Build a per-company opportunity record
    for c in company_records:
        rec = c.get("recommendation") or {}
        intel = rec.get("intelligence") or {}
        scores = rec.get("scores") or {}
        enrichment = c.get("enrichment") or {}
        jobs = (c.get("job_intelligence") or {}).get("jobs") or []
        resume = c.get("_resolved_resume")  # optional injection
        opportunity = build_opportunity_record(
            company=c,
            resume=resume,
            enrichment=enrichment,
            jobs=jobs,
            scores=scores,
            recommendation=intel or rec,
        )
        c["opportunity_v2"] = opportunity
    # Rank
    records_for_rank = [
        {
            "name": c.get("name"),
            "opportunity_score": c["opportunity_v2"]["opportunity_score"],
            "opportunity_tier": c["opportunity_v2"]["opportunity_tier"],
            "opportunity_recommendation_strategy":
                c["opportunity_v2"]["opportunity_recommendation_strategy"],
        }
        for c in company_records
    ]
    records_for_rank = rank_opportunities(records_for_rank)
    rank_map = {r["name"]: r["opportunity_rank"] for r in records_for_rank}
    for c in company_records:
        if c.get("name") in rank_map:
            c["opportunity_v2"]["opportunity_rank"] = rank_map[c["name"]]
            c["opportunity_v2"]["recommended_application_order"] = rank_map[c["name"]]
    return company_records


def build_full_opportunity_pack(
    company_records: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Single-call helper for the dashboard. Returns ranked records +
    portfolio summary + application queue."""
    enriched = enrich_companies_with_opportunity(list(company_records))
    summary = build_portfolio_summary(
        [c["opportunity_v2"] for c in enriched]
    )
    queue = build_application_queue(
        [c["opportunity_v2"] for c in enriched]
    )
    return {
        "portfolio_summary": summary,
        "ranked_opportunities": [c["opportunity_v2"] for c in enriched],
        "application_queue": queue,
    }
