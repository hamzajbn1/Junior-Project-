"""T5-T7 for saved annual counts. No research requests and no year modification."""
import copy
import json
import re
from collections import Counter
from datetime import datetime

from shared import ServiceError
from shared.cskg_service import CONNECTIONS


def reject(message):
    raise ServiceError(message, 409, code="invalid_research_result", retryable=False)


def validate_input(result):
    """T6 input gate: check the public result, without claiming to re-audit papers."""
    if not isinstance(result, dict):
        reject("This research run has no result to explain.")
    if result.get("status") not in {"complete", "partial", "empty"}:
        reject("Finish Agent 2 research and any concept choices before using Agent 3.")
    if result["status"] == "empty":
        return
    if not isinstance(result.get("validation"), dict) or result["validation"].get("passed") is not True:
        reject("Agent 2 validation must pass before Agent 3 can explain the values.")
    if not isinstance(result.get("result_id"), str) or not result["result_id"]:
        reject("The research result is missing its internal reference.")
    relation = result.get("relationship")
    request = result.get("request")
    filters = result.get("filters")
    if not all(isinstance(value, dict) for value in (relation, request, filters)):
        reject("The result is missing its relationship or year scope.")
    if (relation.get("found") is not True or relation.get("predicate") not in {item["id"] for item in CONNECTIONS}
            or relation.get("predicate") != request.get("connection")):
        reject("The result does not identify an approved directed relationship.")
    resolution = result.get("resolution", {})
    for side, field in (("first", "subject"), ("second", "object")):
        selected = resolution.get(side, {}).get("selected") if isinstance(resolution, dict) else None
        if not isinstance(selected, dict) or selected.get("id") != relation.get(field):
            reject("The selected concepts do not match the result's direction.")
    for name in ("start_year", "end_year"):
        bound = filters.get(name)
        if bound is not None and (type(bound) is not int or not 1000 <= bound <= datetime.now().year):
            reject("The saved year scope is invalid.")
        if bound != request.get(name):
            reject("The saved filters do not match the research request.")
    if filters.get("start_year") is not None and filters.get("end_year") is not None:
        if filters["start_year"] > filters["end_year"]:
            reject("The saved year scope is reversed.")
    coverage = result.get("coverage")
    rows = result.get("yearly_counts")
    if not isinstance(coverage, dict) or not isinstance(rows, list) or len(rows) > datetime.now().year - 999:
        reject("The result has invalid yearly values or coverage.")
    complete = coverage.get("year_counts_complete")
    if type(complete) is not bool or complete != (result["status"] == "complete"):
        reject("The result status and its coverage disagree.")
    years = []
    total = 0
    for row in rows:
        if not isinstance(row, dict):
            reject("A yearly row is unreadable.")
        year, papers = row.get("year"), row.get("papers")
        if type(year) is not int or not 1000 <= year <= datetime.now().year:
            reject("A publication year is invalid.")
        if papers is not None and (type(papers) is not int or papers < 0):
            reject("Paper counts must be non-negative whole numbers or unknown.")
        if (complete and papers is None) or (not complete and papers == 0):
            reject("Unknown coverage must not be presented as an established zero.")
        if ((filters.get("start_year") is not None and year < filters["start_year"])
                or (filters.get("end_year") is not None and year > filters["end_year"])):
            reject("A yearly value is outside the saved scope.")
        years.append(year)
        total += papers or 0
    if years and years != list(range(min(years), max(years) + 1)):
        reject("Yearly rows must be unique, ordered, and preserve internal unknown years.")
    if type(result.get("counted_papers")) is not int or result["counted_papers"] != total:
        reject("The yearly values do not match the counted total.")
    if coverage.get("counted_papers") != total:
        reject("Coverage and yearly totals disagree.")
    fields = ("requested_work_ids", "retrieved_works", "missing_metadata", "missing_year",
              "outside_requested_years", "unmapped_references", "failed_work_ids")
    if any(type(coverage.get(name)) is not int or coverage[name] < 0 for name in fields):
        reject("The coverage statistics are invalid.")
    if (coverage["requested_work_ids"] != result.get("total_supporting_papers")
            or coverage["retrieved_works"] + coverage["missing_metadata"] != coverage["requested_work_ids"]
            or coverage["retrieved_works"] != total + coverage["missing_year"] + coverage["outside_requested_years"]
            or coverage["failed_work_ids"] > coverage["missing_metadata"]
            or coverage.get("evidence_retrieval_complete") is not True):
        reject("The coverage statistics do not match the saved result.")
    expected_complete = not any(coverage[name] for name in
                                ("missing_metadata", "missing_year", "unmapped_references", "failed_work_ids"))
    if complete != expected_complete:
        reject("The coverage completeness flag is inconsistent.")
    warnings = result.get("warnings")
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        reject("The saved warnings are unreadable.")


def prepare_graph_facts(result):
    """T5: calculate extrema and simple observed movement; keep the original rows."""
    known = [row for row in result["yearly_counts"] if row["papers"] is not None]
    if not known:
        return None
    highest = max(row["papers"] for row in known)
    lowest = min(row["papers"] for row in known)
    # Only compare adjacent known calendar years. Never bridge an unknown gap.
    changes = [right["papers"] - left["papers"] for left, right in
               zip(result["yearly_counts"], result["yearly_counts"][1:])
               if left["papers"] is not None and right["papers"] is not None]
    if len(known) == 1:
        kind = "single_year"
        trend = "Only one year has an observed count, so a year-to-year trend cannot be established."
    elif not changes:
        kind = "unknown_gaps"
        trend = "Unknown years separate the observed counts, so consecutive yearly changes cannot be established."
    elif any(value > 0 for value in changes) and any(value < 0 for value in changes):
        kind = "mixed"
        trend = "The observed counts include both increases and decreases."
    elif any(value > 0 for value in changes):
        kind = "increasing"
        trend = "The observed consecutive yearly counts increased or stayed the same."
    elif any(value < 0 for value in changes):
        kind = "decreasing"
        trend = "The observed consecutive yearly counts decreased or stayed the same."
    else:
        kind = "unchanged"
        trend = "The observed consecutive yearly counts stayed the same."
    return {
        "highest": {"papers": highest, "years": [row["year"] for row in known if row["papers"] == highest]},
        "lowest": {"papers": lowest, "years": [row["year"] for row in known if row["papers"] == lowest]},
        "trend": {"kind": kind, "text": trend},
        "counted_papers": result["counted_papers"],
        "coverage_complete": result["coverage"]["year_counts_complete"],
    }


def build_chart_spec(result):
    """T7: exact received values, automatic chart type, no new year filtering."""
    rows = result["yearly_counts"]
    if not rows or not any(row["papers"] is not None for row in rows):
        return None
    filters = result["filters"]
    first = filters.get("start_year") or rows[0]["year"]
    last = filters.get("end_year") or rows[-1]["year"]
    return {
        "result_id": result["result_id"], "version": result.get("version"),
        "type": "bar" if last - first + 1 <= 5 else "line",
        "x_label": "Publication year", "y_label": "Distinct supporting papers",
        "labels": [str(row["year"]) for row in rows],
        "values": [row["papers"] for row in rows],
        "filters": copy.deepcopy(filters), "span_years": last - first + 1,
        "warnings": list(result["warnings"]),
    }


def validate_explanation(text, facts):
    """T6 output check: required facts, exact numbers, no unsupported analysis."""
    try:
        answer = json.loads(text)
    except (ValueError, TypeError):
        raise ServiceError("Gemini returned an unreadable explanation. Retry the explanation.", 502,
                           code="invalid_explanation") from None
    valid = isinstance(answer, dict) and set(answer) == {"highest", "lowest", "trend"}
    if valid:
        valid = all(isinstance(value, str) and 1 <= len(value) <= 10000 for value in answer.values())
    if valid:
        for name in ("highest", "lowest"):
            sentence = answer[name]
            numbers = Counter(int(value) for value in re.findall(r"\d+", sentence))
            expected = Counter(facts[name]["years"] + [facts[name]["papers"]])
            valid = valid and numbers == expected and name + " observed" in sentence.casefold()
            valid = valid and ("lowest" if name == "highest" else "highest") not in sentence.casefold()
            valid = valid and not re.search(r"[-+%]|\d\.\d|\d,\d", sentence)
        # This sentence is computed, not an invitation to invent causes or forecasts.
        valid = valid and answer["trend"] == facts["trend"]["text"]
        forbidden = r"because|due to|driven by|caused|proves?|implies|suggests|popular|quality|funding|breakthrough|adoption|covid|pandemic|authors?|abstract|venues?|countr|citations?|forecast|predict|percent|<|>|https?://"
        valid = valid and not any(re.search(forbidden, value, re.I) for value in answer.values())
        # A number immediately before 'papers' must be the corresponding extremum.
        for name in ("highest", "lowest"):
            counts = re.findall(r"\b(\d+)\s+(?:supporting\s+)?papers?\b", answer[name], re.I)
            valid = valid and counts == [str(facts[name]["papers"])]
    if not valid:
        raise ServiceError("The explanation did not match the verified graph facts. Retry the explanation.",
                           502, code="invalid_explanation")
    return answer
