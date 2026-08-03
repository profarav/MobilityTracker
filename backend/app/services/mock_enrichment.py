"""
Mock enrichment provider.

Swap this module out for a real provider (Proxycurl, Apollo, PDL, etc.)
by implementing the same `enrich_person` interface.
"""

import random
from datetime import datetime
from typing import Optional

_COMPANIES = [
    "Google", "Microsoft", "Salesforce", "HubSpot", "Figma", "Stripe",
    "Shopify", "Twilio", "Datadog", "Snowflake", "Accenture", "Deloitte",
    "McKinsey & Company", "KPMG", "Wunderman Thompson", "BBDO", "Ogilvy",
    "Publicis", "R/GA", "Anomaly", "72andSunny", "Droga5",
]

_TITLES = [
    "VP of Marketing", "Head of Growth", "Director of Brand",
    "Chief Marketing Officer", "Senior Director of Marketing",
    "Creative Director", "Head of Design", "Brand Strategist",
    "Director of Communications", "Content Lead", "Growth Lead",
    "VP of Communications", "Head of Creative", "Marketing Manager",
]


def enrich_person(
    person_id: str,
    current_company: Optional[str],
    current_title: Optional[str],
    linkedin_url: Optional[str] = None,
    **kwargs,
) -> dict:
    """
    Simulates a third-party enrichment API response.
    ~30% probability of returning a changed company or title.
    """
    has_changed = random.random() < 0.30

    if has_changed:
        new_company = random.choice([c for c in _COMPANIES if c != current_company])
        new_title = random.choice([t for t in _TITLES if t != current_title])
    else:
        new_company = current_company
        new_title = current_title

    return {
        "source": "mock_enrichment_v1",
        "fetched_at": datetime.utcnow().isoformat(),
        "person_id": person_id,
        "company": new_company,
        "title": new_title,
        "confidence_score": round(random.uniform(0.70, 0.99), 2),
        "linkedin_url": linkedin_url,
        "raw": {
            "mock": True,
            "note": "Replace with Proxycurl, Apollo, or PDL response here.",
        },
    }
