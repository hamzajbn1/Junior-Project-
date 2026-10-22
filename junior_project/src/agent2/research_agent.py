"""Independent LangGraph research workflow with bounded repair. No LLM calls."""
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from shared import RunContext, ServiceError
from shared import cskg_service as cskg
from .research_schemas import ResearchState, parse_request
from .research_tools import TOOLS

# This function runs one research tool (T1–T6), checks its result, records its execution status, and handles errors.
def tool_node(step):
    def run(state):  
        context = state["context"]
        context.emit(step, "running", TOOLS[step]["description"])
        try:
            context.remaining() 
            update = TOOLS[step]["run"](state)
        except ServiceError as error:
            message = "The graph request timed out after its allowed attempts." if str(error) == "__TIMEOUT__" else str(error)
            context.emit(step, "failed", message, code=error.code)
            return {"status": "failed", "error": {"code": error.code, "message": message, "step": step}}
        state_after = {**state, **update}
        if state_after.get("status") in {"empty", "needs_clarification"}:
            context.emit(step, 
                        state_after["status"], 
                        state_after.get("reason", "Research stopped."))
        elif step == "T6" and not update["validation"]["passed"]:
            context.emit(step,
                        "invalid",
                        "Validation found inconsistencies; examining repair options.")
        else:
            context.emit(step,
                        "complete", 
                        TOOLS[step]["name"] + " completed.") 
        return update 
    return run  

# this will decide if the langgraph should continue or stop.
def route_after_tool(next_step):                                                                 
    return lambda state: "finish" if state["status"] in {"failed", "empty", "needs_clarification"} else next_step 


# Receives the research state after T6 checks the results, we know it was T6 because it said after validation.
def after_validation(state):
    if state["status"] == "failed" or state.get("validation", {}).get("passed"):
        return "finish"
    return "repair"

# this function is responsible for repairing research results when T6 detects validation errors.
def repair(state):
    errors = state["validation"]["errors"]  

    if state.get("repair_round", 0) >= 1 or any(error["repair"] is None for error in errors):
        return {"status": "failed",     
                "next_step": "finish",  
                "error": {"code": "validation_failed", 
                          "step": "T6",  
                          "message": "The evidence could not pass validation. Invalid counts were withheld."}} 
    target = "T4" if any(error["repair"] == "metadata" for error in errors) else "T5"
    state["context"].emit("repair", "running", "Repairing the affected stage, then repeating validation.", target=target)
    return {"repair_round": 1, "refresh_metadata": target == "T4", "next_step": target}


def finish(state):
    context = state["context"]
    valid = bool(state.get("validation", {}).get("passed")) and state["status"] != "failed"
    status = state["aggregate"]["status"] if valid else state["status"]
    if status == "running":
        status = "failed"

    relation = state.get("relation", {})   
    warnings = list(relation.get("warnings", [])) 

    # a dictionary mapping specific research outcome codes.
    messages = {
        "concept_unresolved": "No suitable concept was resolved in the searched CS-KG scope.",
        "no_relationship": "No matching directed relationship was found in the searched CS-KG data.",
        "no_supporting_evidence": "The relationship exists, but no supporting-paper references were returned.",
        "unmapped_evidence": "Supporting references were found, but none could be mapped to OpenAlex; this is not proof of no research.",
    }
    result = {
        "status": status, 
        "result_id": str(uuid4()),
        "version": 1, 
        "request": state["request"], 
        "resolution": state.get("resolution", {}), 
        "relationship": relation, 
        "message": messages.get(state.get("reason"), state.get("reason", "")),  
        "validation": state.get("validation", {"passed": False, "performed": False, "errors": []}),  
        "warnings": warnings, 
        "error": state.get("error"),  
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), 
        "source": {"cskg_endpoint": os.environ.get("CSKG_ENDPOINT", cskg.SPARQL_ENDPOINT), "graph": cskg.GRAPH,
                   "openalex": "https://api.openalex.org/works"}, 
        "max_attempts_per_operation": 2, 
        "attempts": dict(context.attempts),
        "elapsed_seconds": round(time.monotonic() - context.started, 2), 
        "execution": "langgraph", 
        "uses_llm": False, 
        "repair_rounds": state.get("repair_round", 0), 
    }
    evidence = state.get("evidence", {})
    if evidence:
        result["supporting_paper_ids"] = evidence["work_ids"]
        result["unmapped_references"] = evidence["unmapped_references"]
    if valid:
        result.update(state["aggregate"])
        result["warnings"] = warnings + state["aggregate"]["warnings"]
        result["batches"] = state["metadata"]["batches"]
    else:
        result["yearly_counts"] = []
        result["counted_papers"] = None
    context.emit("finish", status, "Research finished." if valid else result["error"]["message"] if result["error"] else result["message"])
    result["events"] = list(context.events)
    return {"result": result, "status": status}


def build_graph():
    graph = StateGraph(ResearchState)  
    for step in TOOLS:
        graph.add_node(step, tool_node(step))
    graph.add_node("repair", repair)
    graph.add_node("finish", finish)
    graph.add_edge(START, "T1")
    for step, next_step in zip(("T1", "T2", "T3", "T4", "T5"), ("T2", "T3", "T4", "T5", "T6")):
        graph.add_conditional_edges(step, route_after_tool(next_step), [next_step, "finish"])
    graph.add_conditional_edges("T6", after_validation, ["repair", "finish"])
    graph.add_conditional_edges("repair", lambda state: state["next_step"], ["T4", "T5", "finish"]) 
    graph.add_edge("finish", END)  
    return graph.compile() 


GRAPH = build_graph()

def run_research(body, *, context=None, previous_state=None, selections=None):
    request = parse_request(body) 
    state = dict(previous_state or {})
    state.update(  
                request=request, 
                context=context or RunContext(), # tracking time.
                status="running", 
                selections=selections or {}, 
                reason="", 
                error=None)
    completed = GRAPH.invoke(state, config={"recursion_limit": 24})
    return completed["result"], completed
