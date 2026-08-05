"""Intelligence aggregation for the Weekly Career Report.

This module implements Stage 2 (Market Intelligence) and Stage 4
(Career Intelligence) of the Ticket-014 orchestration pipeline. Both
stages are deterministic — no LLM calls.

  Stage 2 - Market Intelligence
    Input:  list of discovered companies
    Output: market_summary, industry_breakdown, hiring aggregates

  Stage 4 - Career Intelligence
    Input:  normalized candidate profile, all companies, top matches
    Output: career_intelligence, technology_breakdown,
            top_strengths, top_skill_gaps
"""

import re
from collections import Counter
from typing import Any, Dict, List


_FUNDING_TOKEN_RE = re.compile(r"\$?(\d+(?:\.\d+)?)\s*([KMB])?", re.IGNORECASE)
_FUNDING_UNIT = {"K": 0.001, "M": 1.0, "B": 1000.0}


def _parse_funding_millions(amount: str) -> float:
    """Parse strings like '$4B', '$58M', '$367M' into a million-dollar value.

    Returns 0.0 for missing / unparseable strings.
    """
    if not amount:
        return 0.0
    match = _FUNDING_TOKEN_RE.search(str(amount))
    if not match:
        return 0.0
    num = float(match.group(1))
    unit = (match.group(2) or "M").upper()
    return num * _FUNDING_UNIT.get(unit, 1.0)


def _infer_hiring_signal(funding_round: str) -> str:
    """Heuristic mapping from funding stage to hiring signal."""
    stage = (funding_round or "").lower()
    if any(s in stage for s in ["series b", "series c", "series d", "series e", "series f"]):
        return "Actively hiring"
    if "series a" in stage:
        return "Hiring"
    return "Selective hiring"


# =====================================================================
# Stage 2: Market Intelligence
# =====================================================================

def market_intelligence(companies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate statistics over the discovered companies dataset."""
    if not companies:
        return {
            "market_summary": {
                "total_companies": 0,
                "industries_covered": 0,
                "funding_stages": {},
                "hiring_signals": {},
                "total_funding_millions": 0,
            },
            "industry_breakdown": [],
        }

    funding_stage_counts: Counter = Counter()
    hiring_signal_counts: Counter = Counter()
    industry_counts: Counter = Counter()
    total_funding = 0.0

    for company in companies:
        stage = company.get("funding_round") or "Undisclosed"
        funding_stage_counts[stage] += 1

        hiring_signal_counts[_infer_hiring_signal(stage)] += 1

        industry = company.get("industry") or "Other"
        industry_counts[industry] += 1

        total_funding += _parse_funding_millions(company.get("funding_amount", ""))

    industry_breakdown = [
        {"industry": industry, "company_count": count}
        for industry, count in sorted(
            industry_counts.items(), key=lambda x: (-x[1], x[0])
        )
    ]

    return {
        "market_summary": {
            "total_companies": len(companies),
            "industries_covered": len(industry_counts),
            "funding_stages": dict(
                sorted(funding_stage_counts.items(), key=lambda x: (-x[1], x[0]))
            ),
            "hiring_signals": dict(
                sorted(hiring_signal_counts.items(), key=lambda x: (-x[1], x[0]))
            ),
            "total_funding_millions": round(total_funding, 1),
        },
        "industry_breakdown": industry_breakdown,
    }


# =====================================================================
# Stage 4: Career Intelligence
# =====================================================================

def career_intelligence(
    candidate: Dict[str, Any],
    companies: List[Dict[str, Any]],
    top_matches: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Derive per-candidate career insights from the company dataset."""
    candidate_skills = {s.lower() for s in (candidate.get("skills") or [])}
    candidate_skill_original = {
        s.lower(): s for s in (candidate.get("skills") or [])
    }

    # Build a lowercase -> original-casing lookup from the company
    # dataset so we can render "PyTorch", "TypeScript", "FastAPI"
    # with their original casing rather than a crude .title() fallback.
    skill_casing_lookup: Dict[str, str] = {}
    for company in companies:
        for skill in company.get("skills") or []:
            skill_casing_lookup.setdefault(skill.lower(), skill)

    overlap_counter: Counter = Counter()
    demand_counter: Counter = Counter()
    missing_counter: Counter = Counter()
    industry_overlap: Counter = Counter()

    for company in companies:
        company_skill_set = {
            s.lower() for s in (company.get("skills") or [])
        }
        overlap = candidate_skills & company_skill_set
        if overlap:
            overlap_counter.update(overlap)
            industry_overlap[company.get("industry") or "Other"] += len(overlap)
        demand_counter.update(company_skill_set)
        missing_counter.update(company_skill_set - candidate_skills)

    # technology_breakdown — how often each tech appears across companies,
    # and whether the candidate already has it. Capped at the top 20.
    technology_breakdown = []
    for tech, count in demand_counter.most_common(20):
        technology_breakdown.append(
            {
                "technology": skill_casing_lookup.get(
                    tech, candidate_skill_original.get(tech, tech.title())
                ),
                "demand_count": count,
                "you_have_it": tech in candidate_skills,
            }
        )

    # top_strengths — candidate skills with the broadest demand overlap.
    top_strengths = [
        candidate_skill_original.get(skill, skill.title())
        for skill, _ in overlap_counter.most_common(5)
    ]

    # top_skill_gaps — missing skills ranked by how many companies want them.
    top_skill_gaps = [
        skill_casing_lookup.get(skill, skill.title())
        for skill, _ in missing_counter.most_common(6)
        if skill not in candidate_skills
    ][:5]

    # career_intelligence — the headline narrative fields.
    top_hiring_industries = [
        industry for industry, _ in industry_overlap.most_common(5) if industry
    ]
    dominant_technologies = [
        skill_casing_lookup.get(tech, candidate_skill_original.get(tech, tech.title()))
        for tech, _ in demand_counter.most_common(8)
    ]
    career_strengths = [
        candidate_skill_original.get(skill, skill.title())
        for skill, _ in overlap_counter.most_common(5)
    ]
    highest_opportunity_areas = [
        industry for industry, _ in industry_overlap.most_common(5) if industry
    ]

    return {
        "career_intelligence": {
            "top_hiring_industries": top_hiring_industries,
            "dominant_technologies": dominant_technologies,
            "career_strengths": career_strengths,
            "most_valuable_skill_gaps": top_skill_gaps,
            "highest_opportunity_areas": highest_opportunity_areas,
        },
        "technology_breakdown": technology_breakdown,
        "top_strengths": top_strengths,
        "top_skill_gaps": top_skill_gaps,
    }