"""
Apollo enrichment provider.

Implements the same `enrich_person` interface as mock_enrichment.py.
Calls Apollo's People Match (people enrichment) endpoint via the Apollo MCP.
"""

import os
import httpx
from datetime import datetime
from typing import Optional

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")


def enrich_person(
    person_id: str,
    current_company: Optional[str],
    current_title: Optional[str],
    linkedin_url: Optional[str] = None,
    email: Optional[str] = None,
    full_name: Optional[str] = None,
) -> dict:
    """
    Enriches a person via Apollo's People Match API.
    Returns normalized dict matching the mock_enrichment interface.
    """
    payload = {"reveal_personal_emails": False}

    if email:
        payload["email"] = email
    if full_name:
        payload["name"] = full_name
    if linkedin_url:
        payload["linkedin_url"] = linkedin_url
    if current_company:
        payload["organization_name"] = current_company

    response = httpx.post(
        "https://api.apollo.io/api/v1/people/match",
        headers={
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": APOLLO_API_KEY,
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    person = data.get("person") or {}

    employment = (person.get("employment_history") or [{}])[0]
    new_company = (
        person.get("organization", {}).get("name")
        or employment.get("organization_name")
        or current_company
    )
    new_title = (
        person.get("title")
        or employment.get("title")
        or current_title
    )

    return {
        "source": "apollo_v1",
        "fetched_at": datetime.utcnow().isoformat(),
        "person_id": person_id,
        "company": new_company,
        "title": new_title,
        "confidence_score": 0.90 if person else 0.0,
        "linkedin_url": person.get("linkedin_url") or linkedin_url,
        "raw": data,
    }
