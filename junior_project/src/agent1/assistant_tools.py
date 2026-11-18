"""Authoritative current-chat result lookup and immutable year views. No history search."""
import copy
from uuid import uuid5, NAMESPACE_URL
from shared import ServiceError
from shared.chat_store import CHAT_STORE
from agent2.research_routes import JOBS, RESULT_STORE
from agent2.research_schemas import parse_request
from agent3.explanation_tools import T6_validate_input


def load_result(reference, chat_id=None):
    if not isinstance(reference, dict) or set(reference) - {"task_id", "start_year", "end_year"}:
        raise ServiceError("Invalid research reference.", 400)
    identifier = reference.get("task_id")
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 100:
        raise ServiceError("Invalid research reference.", 400)
    if chat_id is not None:
        result = CHAT_STORE.load_result(chat_id, reference)
        T6_validate_input(result)
        return result
    try:
        snapshot = RESULT_STORE.load_task(identifier)
    except ServiceError as error:
        if error.code != "task_not_found":
            raise
        snapshot = JOBS.snapshot(identifier)
    result = copy.deepcopy(snapshot.get("result"))
    T6_validate_input(result)
    if "start_year" in reference or "end_year" in reference:
        result = year_view(result, reference.get("start_year"), reference.get("end_year"))
    return result


def year_view(original, start, end):
    T6_validate_input(original)
    if original["status"] == "empty":
        raise ServiceError("This result has no annual data to filter.", 409, code="no_data")
    request = parse_request({**original["request"], "start_year": start, "end_year": end})
    old = original.get("filters", {})
    if ((old.get("start_year") is not None and (start is None or start < old["start_year"]))
            or (old.get("end_year") is not None and (end is None or end > old["end_year"]))):
        raise ServiceError("The saved scope does not cover these years. Research is needed.", 409, code="research_required")
    result = copy.deepcopy(original)
    rows = [row for row in result["yearly_counts"]
            if (start is None or row["year"] >= start) and (end is None or row["year"] <= end)]
    total = sum(row["papers"] or 0 for row in rows)
    result.update(request=request, filters={"start_year": start, "end_year": end},
                  yearly_counts=rows, counted_papers=total,
                  parent_result_id=original["result_id"],
                  result_id=str(uuid5(NAMESPACE_URL, f"{original['result_id']}:{start}:{end}")))
    result.pop("counted_paper_ids", None)  # Annual rows cannot identify individual papers after filtering.
    result["coverage"]["outside_requested_years"] += original["counted_papers"] - total
    result["coverage"]["counted_papers"] = total
    if not rows and result["status"] == "complete":
        result.update(status="empty", message="No dated supporting papers fall in the selected years.")
    T6_validate_input(result)
    return result


def describe(reference, result):
    return {"reference": reference, "concepts": [result["request"]["first_concept"], result["request"]["second_concept"]],
            "relationship": result["request"]["connection"], "filters": result.get("filters"),
            "status": result["status"], "coverage_complete": result.get("coverage", {}).get("year_counts_complete"),
            "yearly_counts": copy.deepcopy(result.get("yearly_counts", [])),
            "counted_papers": result.get("counted_papers"), "coverage": copy.deepcopy(result.get("coverage", {})),
            "warnings": list(result.get("warnings", [])), "source": copy.deepcopy(result.get("source", {})),
            "retrieved_at": result.get("retrieved_at")}
