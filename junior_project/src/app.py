"""Research Trend Explorer: Overview plus independent Agent 2 test routes."""
import collections
import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from ai_connection.gemini_connection import create_gemini_blueprint
from shared import ServiceError
from shared import cskg_service as cskg
from shared import openalex_client as openalex
from shared import research_processing as processing
from shared.cskg_service import (
    SPARQL_ENDPOINT, GRAPH, RESOURCE, ONTOLOGY, SEARCH_TIMEOUT, RELATION_TIMEOUT,
    CONNECTIONS, ALLOWED_PREDICATES, local_name, normalize, safe_tokens,
    search_query, rank, validate_concept,
)
from shared.research_processing import publication_year, supporting_insights, bucket
from shared.overview_explanations import remember_overview, explain_overview_chart

OPENALEX_BASE = openalex.OPENALEX_BASE
OPENALEX_HEADERS = openalex.OPENALEX_HEADERS
app = Flask(__name__)
CORS(app)
app.register_blueprint(create_gemini_blueprint())

@app.errorhandler(ServiceError)
def handle_service_error(error):
    return jsonify({"error": str(error)}), error.status

def run_query(query, timeout):
    return cskg.run_query(query, timeout)

def resolve_entities(text):
    return cskg.resolve_entities(text, query_fn=run_query)

def paper_ids(subject, predicate, obj):
    return cskg.paper_ids(subject, predicate, obj, query_fn=run_query)

def fetch_openalex_works(ids):
    result = openalex.fetch_works(ids)
    return result["works"], set(result["failed_ids"])

def relationship_trend(subject, predicate, obj):
    predicate = cskg.validate_connection(predicate)
    validate_concept(subject, "first")
    validate_concept(obj, "second")
    references, unusable = paper_ids(subject, predicate, obj)
    if not references:
        return {"status": "no_years" if unusable else "no_relationship", "data": [],
                "total_papers": unusable,
                "notes": [f"{unusable} paper references could not be matched to OpenAlex."] if unusable else [],
                **supporting_insights(set(), {}, set(), unusable)}
    works, failed = fetch_openalex_works(references)
    return processing.overview_result(references, works, failed, unusable)

@app.get("/api/connections")
def api_connections():
    return jsonify({"connections": CONNECTIONS})


@app.get("/api/entities")
def api_entities():
    text = (request.args.get("q") or "").strip()
    if not 2 <= len(text) <= 200:
        raise ServiceError("Enter between 2 and 200 characters.", 400)
    try:
        return jsonify(resolve_entities(text))
    except ServiceError as error:
        if str(error) == "__TIMEOUT__":
            raise ServiceError(
                f"The search took longer than {SEARCH_TIMEOUT} seconds and was stopped. Try a longer or more specific word.",
                504,
            ) from error
        raise


@app.get("/api/relationship")
def api_relationship():
    try:
        subject, predicate, obj = request.args.get("s"), request.args.get("p"), request.args.get("o")
        result = relationship_trend(subject, predicate, obj)
        return jsonify(remember_overview(result, {"first_concept": local_name(subject),
                       "connection": predicate, "second_concept": local_name(obj)}))
    except ServiceError as error:
        if str(error) == "__TIMEOUT__":
            raise ServiceError(
                f"The knowledge graph took longer than {RELATION_TIMEOUT} seconds to answer and was stopped. Please try again.",
                504,
            ) from error
        raise


@app.post("/api/overview/explain")
def api_overview_explain():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"overview_id", "chart_type"}:
        raise ServiceError("Select an Overview result and chart to explain.", 400)
    output = explain_overview_chart(body["overview_id"], body["chart_type"])
    return jsonify(output), 502 if output["status"] == "explanation_failed" else 200


# Kept from the original project. No page uses it yet.
@app.get("/api/authors/top")
def api_top_authors():
    subject = validate_concept(request.args.get("s"), "first")
    obj = validate_concept(request.args.get("o"), "second")
    predicate = request.args.get("p")
    if predicate not in ALLOWED_PREDICATES:
        raise ServiceError("Select an approved connection.", 400)

    references, _ = paper_ids(subject, predicate, obj)
    counts = collections.Counter()
    ordered = sorted(references)
    for start in range(0, len(ordered), 50):
        batch = ordered[start:start + 50]
        try:
            response = requests.get(
                OPENALEX_BASE,
                params={"filter": "ids.openalex:" + "|".join(batch),
                        "select": "authorships", "per_page": 50},
                headers=OPENALEX_HEADERS, timeout=(10, 45))
            response.raise_for_status()
            for work in response.json().get("results", []):
                for authorship in work.get("authorships", []):
                    name = (authorship.get("author") or {}).get("display_name")
                    if name:
                        counts[name] += 1
        except (requests.RequestException, ValueError, KeyError, TypeError):
            continue
    return jsonify({"data": [{"name": name, "papers": total}
                             for name, total in counts.most_common(5)]})


from agent2.research_routes import create_research_blueprint
app.register_blueprint(create_research_blueprint())

from agent1.assistant_routes import create_assistant_blueprint
app.register_blueprint(create_assistant_blueprint())

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
