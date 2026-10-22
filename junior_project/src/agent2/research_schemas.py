"""Strict request parsing plus the private LangGraph state schema."""
from datetime import datetime
from typing import TypedDict

from shared import ServiceError
from shared.cskg_service import validate_connection


def parse_request(body):
    if not isinstance(body, dict):
        raise ServiceError("Send a research request as a JSON object.", 400, code="invalid_input")
    values = {}
    for name in ("first_concept", "second_concept"):
        value = body.get(name)
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 200:
            raise ServiceError("Enter two concept names, each between 2 and 200 characters.", 400, code="invalid_input")
        values[name] = value.strip()
    values["connection"] = validate_connection(body.get("connection"))
    for name in ("start_year", "end_year"):
        value = body.get(name)
        if value is None or value == "":
            values[name] = None
        elif type(value) is int and 1000 <= value <= datetime.now().year:
            values[name] = value
        else:
            raise ServiceError("Years must be whole numbers between 1000 and the current year, or blank.",
                               400, code="invalid_years")
    if values["start_year"] is not None and values["end_year"] is not None and values["start_year"] > values["end_year"]:
        raise ServiceError("The start year cannot be after the end year.", 400, code="invalid_years")
    return values


class ResearchState(TypedDict, total=False):
    request: dict
    context: object
    status: str
    resolution: dict
    selections: dict
    relation: dict
    evidence: dict
    metadata: dict
    records: dict
    aggregate: dict
    validation: dict
    repair_round: int
    refresh_metadata: bool
    next_step: str
    error: dict
    reason: str
    result: dict
