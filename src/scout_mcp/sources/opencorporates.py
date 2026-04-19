"""OpenCorporates API — company registry data from 140+ jurisdictions.

Free tier provides:
- Company name, registration number, status
- Incorporation date, jurisdiction
- Registered address
- Company type (LLC, Inc, Ltd, etc.)
- Current status (active, dissolved, etc.)
"""

import logging
import httpx

from ..config import REQUEST_TIMEOUT

logger = logging.getLogger(__name__)

_OC_BASE = "https://api.opencorporates.com/v0.4"


async def search_company(company_name: str) -> dict:
    """Search OpenCorporates for company registration data.

    Returns dict with: company_name, company_number, jurisdiction,
    incorporation_date, company_type, status, registered_address, opencorporates_url.
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(
                f"{_OC_BASE}/companies/search",
                params={"q": company_name, "per_page": 3, "order": "score"},
            )
            if resp.status_code != 200:
                logger.info("OpenCorporates: %d for '%s'", resp.status_code, company_name)
                return {}

            data = resp.json()
            results = data.get("results", {}).get("companies", [])
            if not results:
                logger.info("OpenCorporates: no results for '%s'", company_name)
                return {}

            # Pick the best match — prefer active companies with matching name
            best = None
            for item in results:
                company = item.get("company", {})
                name = (company.get("name") or "").lower()
                if company_name.lower() in name or name in company_name.lower():
                    if company.get("current_status", "").lower() == "active":
                        best = company
                        break
                    if best is None:
                        best = company

            if best is None:
                best = results[0].get("company", {})

            result = {}
            if best.get("name"):
                result["legal_name"] = best["name"]
            if best.get("company_number"):
                result["company_number"] = best["company_number"]
            if best.get("jurisdiction_code"):
                result["jurisdiction"] = best["jurisdiction_code"].upper()
            if best.get("incorporation_date"):
                result["incorporation_date"] = best["incorporation_date"]
            if best.get("company_type"):
                result["company_type"] = best["company_type"]
            if best.get("current_status"):
                result["status"] = best["current_status"]
            if best.get("registered_address_in_full"):
                result["registered_address"] = best["registered_address_in_full"]
            if best.get("opencorporates_url"):
                result["opencorporates_url"] = best["opencorporates_url"]
            if best.get("registry_url"):
                result["registry_url"] = best["registry_url"]

            logger.info("OpenCorporates: found '%s' in %s", result.get("legal_name", "?"), result.get("jurisdiction", "?"))
            return result

    except Exception as e:
        logger.warning("OpenCorporates search failed for '%s': %s", company_name, e)
        return {}
