"""Pydantic response models for Scout MCP tools.

Every Intel model includes:
- confidence: float 0-1 (weighted average of per-source scores)
- confidence_breakdown: dict mapping source name -> score 0-1
- data_quality_grade: letter grade (A+/A/B/C/D/F) for quick filtering
  Agents can use these to weight intelligence quality in their reasoning.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


def _default_breakdown() -> dict:
    return {}


def compute_grade(confidence: float) -> str:
    """Compute a letter grade from a 0-1 confidence score.

    A+ (0.90+): Exceptional — multiple high-quality sources confirmed
    A  (0.80-0.90): High — strong multi-source corroboration
    B  (0.65-0.80): Good — solid data from key sources
    C  (0.45-0.65): Fair — limited sources, gaps likely
    D  (0.25-0.45): Low — sparse data, treat with caution
    F  (<0.25): Insufficient — minimal data available
    """
    if confidence >= 0.90:
        return "A+"
    if confidence >= 0.80:
        return "A"
    if confidence >= 0.65:
        return "B"
    if confidence >= 0.45:
        return "C"
    if confidence >= 0.25:
        return "D"
    return "F"


GRADE_DESCRIPTIONS = {
    "A+": "Exceptional — multiple high-quality sources confirmed",
    "A": "High — strong multi-source corroboration",
    "B": "Good — solid data from key sources",
    "C": "Fair — limited sources, gaps likely",
    "D": "Low — sparse data, treat with caution",
    "F": "Insufficient — minimal data available",
}


class SourceConfidence(BaseModel):
    """Per-source confidence score with reason."""
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class FundingInfo(BaseModel):
    total_funding: Optional[str] = None
    last_round: Optional[str] = None
    last_round_amount: Optional[str] = None
    valuation: Optional[str] = None


class NewsItem(BaseModel):
    headline: str
    source: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None


class SocialProfile(BaseModel):
    platform: str
    url: str


class KeyPerson(BaseModel):
    name: str
    role: Optional[str] = None


class CompanyIntel(BaseModel):
    name: str
    domain: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    founded: Optional[str] = None
    headquarters: Optional[str] = None
    employee_range: Optional[str] = None
    funding: Optional[FundingInfo] = None
    tech_stack: list[str] = Field(default_factory=list)
    social_profiles: list[SocialProfile] = Field(default_factory=list)
    recent_news: list[NewsItem] = Field(default_factory=list)
    top_competitors: list[str] = Field(default_factory=list)
    key_people: list[KeyPerson] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: dict[str, SourceConfidence] = Field(default_factory=_default_breakdown)
    data_quality_grade: str = Field(default="F", description="Letter grade: A+/A/B/C/D/F")
    data_freshness: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)


class CompetitorEntry(BaseModel):
    name: str
    domain: Optional[str] = None
    positioning: Optional[str] = None
    pricing: Optional[str] = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    key_differentiator: Optional[str] = None


class CompetitorIntel(BaseModel):
    target: str
    competitors: list[CompetitorEntry] = Field(default_factory=list)
    market_positioning_summary: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: dict[str, SourceConfidence] = Field(default_factory=_default_breakdown)
    data_quality_grade: str = Field(default="F", description="Letter grade: A+/A/B/C/D/F")
    data_freshness: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)


class TrendDevelopment(BaseModel):
    headline: str
    date: Optional[str] = None
    impact_level: Optional[str] = None
    source: Optional[str] = None
    url: Optional[str] = None


class TrendIntel(BaseModel):
    topic: str
    timeframe: str
    sentiment: dict = Field(default_factory=lambda: {"score": 0.0, "label": "neutral"})
    trending_direction: Optional[str] = None
    key_developments: list[TrendDevelopment] = Field(default_factory=list)
    related_topics: list[str] = Field(default_factory=list)
    social_buzz: dict = Field(default_factory=lambda: {"volume": "unknown", "key_voices": []})
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: dict[str, SourceConfidence] = Field(default_factory=_default_breakdown)
    data_quality_grade: str = Field(default="F", description="Letter grade: A+/A/B/C/D/F")
    data_freshness: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)


class MarketIntel(BaseModel):
    market_name: str
    query: str
    depth: str
    market_size: Optional[str] = None
    market_size_projections: Optional[str] = None
    cagr: Optional[str] = None
    key_players: list[str] = Field(default_factory=list)
    trends: list[str] = Field(default_factory=list)
    growth_drivers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: dict[str, SourceConfidence] = Field(default_factory=_default_breakdown)
    data_quality_grade: str = Field(default="F", description="Letter grade: A+/A/B/C/D/F")
    data_freshness: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)


class ProductRating(BaseModel):
    platform: str
    score: Optional[str] = None
    url: Optional[str] = None


class ProductIntel(BaseModel):
    name: str
    category: Optional[str] = None
    description: Optional[str] = None
    pricing: dict = Field(default_factory=lambda: {"free_tier": None, "paid_from": None})
    ratings: list[ProductRating] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    ideal_for: Optional[str] = None
    alternatives: list[str] = Field(default_factory=list)
    recent_updates: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: dict[str, SourceConfidence] = Field(default_factory=_default_breakdown)
    data_quality_grade: str = Field(default="F", description="Letter grade: A+/A/B/C/D/F")
    data_freshness: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)


class PersonIntel(BaseModel):
    name: str
    current_role: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    background_summary: Optional[str] = None
    social_profiles: list[SocialProfile] = Field(default_factory=list)
    recent_activity: list[str] = Field(default_factory=list)
    notable_achievements: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: dict[str, SourceConfidence] = Field(default_factory=_default_breakdown)
    data_quality_grade: str = Field(default="F", description="Letter grade: A+/A/B/C/D/F")
    data_freshness: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sources_used: list[str] = Field(default_factory=list)
    sources_failed: list[str] = Field(default_factory=list)
