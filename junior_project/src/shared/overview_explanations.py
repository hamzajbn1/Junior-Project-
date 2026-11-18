"""Overview-only chart prompts and server-side snapshots passed to Agent 3."""
import json
from uuid import uuid4

from agent3 import explanation_agent
from shared import ServiceError
from shared.chat_store import CHAT_STORE, encode


CHARTS = {
    "publications": {
        "field": "data", "metric": "Distinct supporting papers per publication period",
        "prompt": "Give a general explanation of publications over time. Use the displayed start/end periods exactly. "
                  "A point may cover several years. Distinguish observed zero counts from incomplete coverage, "
                  "and qualify partial years. Highlight peaks and overall movement without claiming a cause.",
    },
    "venues": {
        "field": "venue_data", "metric": "Distinct supporting papers by primary publication venue",
        "prompt": "Give a general explanation of the leading publication venues in these supporting papers. "
                  "These are up to five leading venues in the retrieved supporting papers, "
                  "not all venues worldwide. Mention unavailable venue metadata when relevant.",
    },
    "countries": {
        "field": "country_data", "metric": "Distinct supporting papers by author-affiliation country",
        "prompt": "Give a general explanation of the leading author-affiliation countries. Explain country codes "
                  "using their country names. A multinational paper counts once under each represented country, "
                  "so country totals can exceed the number of papers. Only up to five leading countries are displayed. "
                  "Affiliation countries do not establish author nationality. Qualify missing/partial country metadata.",
    },
    "citations": {
        "field": "top_cited_papers", "metric": "OpenAlex citations per supporting paper",
        "prompt": "Summarize the displayed citation ranking in one paragraph of 80-110 words. "
                  "Mention only the leading paper, or the top two if useful, with their citation counts; "
                  "do not enumerate every paper or repeat all full titles. Refer to the chart labels for the remaining entries. "
                  "Publication years are metadata, not yearly citation counts. "
                  "Citations are not downloads, views, or proof of research quality. The ranking covers only the "
                  "retrieved supporting papers. Qualify missing citation metadata.",
    },
}


def remember_overview(result, relationship):
    if result.get("status") not in {"ok", "no_years"}:
        return result
    identifier = str(uuid4())
    snapshot = {**result, "relationship": relationship}
    with CHAT_STORE.database() as connection:
        connection.execute("INSERT INTO overview_results (result_id, snapshot_json) VALUES (?, ?)",
                           (identifier, encode(snapshot)))
    return {**result, "overview_id": identifier}


def explain_overview_chart(identifier, chart_type):
    """Select a chart-specific prompt and call the existing Agent 3 once."""
    if (not isinstance(identifier, str) or not 1 <= len(identifier) <= 100
            or not isinstance(chart_type, str) or chart_type not in CHARTS):
        raise ServiceError("Select a supported Overview chart.", 400)
    with CHAT_STORE.database() as connection:
        row = connection.execute("SELECT snapshot_json FROM overview_results WHERE result_id = ?",
                                 (identifier,)).fetchone()
    if row is None:
        raise ServiceError("This Overview result was not found. Show the trend again.", 404)
    snapshot = json.loads(row[0])
    chart = CHARTS[chart_type]
    rows = snapshot.get(chart["field"], [])
    if not rows:
        raise ServiceError("There are no values available for this chart.", 409)
    warnings = snapshot.get("notes", [])
    output = explanation_agent.explain_chart(
        {"relationship": snapshot["relationship"], "rows": rows, "metric": chart["metric"],
         "bucket_size": snapshot.get("bucket_size") if chart_type == "publications" else None,
         "total_supporting_papers": snapshot.get("total_papers"), "coverage": snapshot.get("coverage", {}),
         "metadata_status": snapshot.get("metadata_status"), "warnings": warnings,
         "retrieved_at": snapshot.get("retrieved_at")}, guidance=chart["prompt"], provider="auto")
    return {**output, "overview_id": identifier, "chart_type": chart_type, "warnings": warnings}
