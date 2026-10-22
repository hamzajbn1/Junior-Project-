"""T1-T6 adapters over shared functions. No LLM, MCP, or duplicate retrieval code."""
from shared import ServiceError
from shared import cskg_service as cskg
from shared import openalex_client as openalex
from shared import research_processing as processing


def resolve_concepts(state):
    context, request = state["context"], state["request"]
    resolution = dict(state.get("resolution", {}))
    for side, field in (("first", "first_concept"), ("second", "second_concept")):
        if side not in resolution:
            resolution[side] = cskg.resolve_entities(request[field], query_fn=cskg.query_for_task(context, "T1"))
    for side, identifier in state.get("selections", {}).items():
        choice = next((item for item in resolution[side]["candidates"] if item["id"] == identifier), None)
        if choice is None:
            raise ServiceError("Choose one of this task's returned candidates.", 400, code="invalid_selection")
        resolution[side] = {**resolution[side], "selected": choice}
    if any(not value["candidates"] for value in resolution.values()):
        return {"resolution": resolution, "status": "empty", "reason": "concept_unresolved"}
    if any(not value["selected"] for value in resolution.values()):
        return {"resolution": resolution, "status": "needs_clarification", "reason": "Choose the intended concepts."}
    return {"resolution": resolution}


def check_relation(state):
    result = cskg.find_relations(
        state["resolution"]["first"]["selected"]["id"], state["request"]["connection"],
        state["resolution"]["second"]["selected"]["id"],
        query_fn=cskg.query_for_task(state["context"], "T2"))
    if not result["found"]:
        return {"relation": result, "status": "empty", "reason": "no_relationship"}
    return {"relation": result}


def retrieve_evidence(state):
    relation = state["relation"]
    evidence = cskg.get_evidence(relation["subject"], relation["predicate"], relation["object"],
                                 query_fn=cskg.query_for_task(state["context"], "T3"))
    if not evidence["work_ids"]:
        reason = "unmapped_evidence" if evidence["unmapped_references"] else "no_supporting_evidence"
        return {"evidence": evidence, "status": "empty", "reason": reason}
    return {"evidence": evidence}


def retrieve_metadata(state):
    metadata = openalex.fetch_works(state["evidence"]["work_ids"], context=state["context"],
                                   counts_only=True,
                                   refresh=state.get("refresh_metadata", False))
    extracted = processing.extract_records(metadata["works"], set(state["evidence"]["work_ids"]))
    return {"metadata": metadata, "records": extracted["records"], "refresh_metadata": False}


def aggregate_results(state):
    request = state["request"]
    return {"aggregate": processing.aggregate_research(
        state["records"], state["evidence"], state["metadata"],
        start_year=request["start_year"], end_year=request["end_year"])}


def validate_evidence(state):
    validation = processing.validate_result(state["request"], state["relation"], state["evidence"],
                                            state["metadata"], state["records"], state["aggregate"])
    return {"validation": validation}


TOOLS = {
    "T1": {"name": "resolve_entities", "description": "Resolve both concept names against live CS-KG; preserve candidates for clarification.", "run": resolve_concepts},
    "T2": {"name": "find_cskg_relations", "description": "Check the approved predicate in the requested direction.", "run": check_relation},
    "T3": {"name": "get_cskg_evidence", "description": "Retrieve complete supporting references and verified OpenAlex ID mappings.", "run": retrieve_evidence},
    "T4": {"name": "fetch_openalex_metadata", "description": "Fetch one shared batched collection and extract normalized records.", "run": retrieve_metadata},
    "T5": {"name": "aggregate_research_results", "description": "Count distinct supporting works per publication year within optional filters.", "run": aggregate_results},
    "T6": {"name": "validate_evidence_package", "description": "Validate relationship identity, membership, filters, counts and coverage.", "run": validate_evidence},
}
