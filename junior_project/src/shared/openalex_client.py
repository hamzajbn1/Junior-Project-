"""One metadata pass, shared by Overview and Agent 2. No counting or charts."""
import os
import re
from hashlib import sha256

import requests
from . import ServiceError

OPENALEX_BASE = "https://api.openalex.org/works"
OPENALEX_HEADERS = {"User-Agent": "ResearchTrendExplorer/1.0"}
BASE_FIELDS = "id,publication_year,display_name,cited_by_count,primary_location,authorships"


def fetch_works(work_ids, *, context=None, counts_only=False, refresh=False):
    """Fetch exactly the supplied work IDs. Context owns at most two attempts/batch.

    Overview makes one attempt, preserving its existing behavior. Agent 2 passes
    its shared RunContext. Credentials never enter the result or progress log.
    """
    ordered = sorted(set(work_ids))
    if any(not isinstance(value, str) or not re.fullmatch(r"W\d+", value) for value in ordered):
        raise ServiceError("OpenAlex requires verified supporting-work IDs.", 400, code="invalid_work_ids")
    works, failed, conflicts, batch_log = {}, set(), set(), []
    ignored = 0
    for start in range(0, len(ordered), 50):
        batch = ordered[start:start + 50]
        fields = "id,publication_year" if counts_only else BASE_FIELDS
        params = {"filter": "ids.openalex:" + "|".join(batch), "select": fields, "per_page": 50}
        if os.environ.get("OPENALEX_API_KEY"):
            params["api_key"] = os.environ["OPENALEX_API_KEY"]
        key = "openalex:" + sha256(("|".join(batch) + fields).encode()).hexdigest()[:16]

        def request_batch():
            try:
                remaining = context.remaining() if context else 45
                response = requests.get(OPENALEX_BASE, params=params, headers=OPENALEX_HEADERS,
                                        timeout=(min(10, remaining), min(45, remaining)))
                response.raise_for_status()
                results = response.json()["results"]
                if not isinstance(results, list):
                    raise ValueError("Invalid work list")
                return results
            except requests.RequestException as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                raise ServiceError("An OpenAlex batch could not be retrieved.", 502,
                                   retryable=status is None or status == 429 or status >= 500,
                                   code="openalex_request") from exc
            except (ValueError, KeyError, TypeError) as exc:
                raise ServiceError("OpenAlex returned an unreadable batch.", 502,
                                   code="openalex_response") from exc

        try:
            results = context.execute(key, "T4", request_batch, refresh=refresh) if context else request_batch()
            for work in results:
                if not isinstance(work, dict) or not isinstance(work.get("id"), str):
                    ignored += 1
                    continue
                match = re.fullmatch(r"https?://openalex\.org/(W\d+)", work["id"])
                identifier = match.group(1) if match else None
                if identifier not in batch:
                    ignored += 1
                    continue
                if identifier in works and works[identifier] != work:
                    conflicts.add(identifier)
                works.setdefault(identifier, work)
            batch_log.append({"operation": key, "requested": len(batch), "status": "complete",
                              "attempts": context.attempts[key] if context else 1})
        except ServiceError as error:
            if error.code == "task_timeout":
                raise
            failed.update(batch)
            batch_log.append({"operation": key, "requested": len(batch), "status": "failed",
                              "attempts": context.attempts.get(key, 0) if context else 1})
    if ordered and len(failed) == len(ordered):
        raise ServiceError("Publication details could not be retrieved from OpenAlex. Check the connection and API key, then try again.",
                           502, retryable=False, code="metadata_failed")
    return {"works": works, "failed_ids": sorted(failed), "missing_ids": sorted(set(ordered) - works.keys()),
            "conflicting_ids": sorted(conflicts), "ignored_records": ignored, "batches": batch_log}
