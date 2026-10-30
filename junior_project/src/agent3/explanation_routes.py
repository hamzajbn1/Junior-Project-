"""Local test integration. Load the exact Agent 2 result on the server."""
from flask import Blueprint, jsonify, request

from agent2 import research_routes
from shared import ServiceError
from .explanation_agent import explain_result


def create_explanation_blueprint():
    routes = Blueprint("agent3", __name__)

    @routes.errorhandler(ServiceError)
    def service_error(error):
        return jsonify({"status": "failed", "code": error.code, "error": str(error)}), error.status

    @routes.post("/api/agent3/explain")
    def explain():
        body = request.get_json(silent=True)
        if (not isinstance(body, dict) or set(body) != {"task_id"}
                or not isinstance(body["task_id"], str) or not 1 <= len(body["task_id"]) <= 100):
            raise ServiceError("Select an Agent 2 research run to explain.", 400, code="invalid_input")
        identifier = body["task_id"]
        try:
            snapshot = research_routes.JOBS.snapshot(identifier)
            origin = "current_run"
        except ServiceError as error:
            if error.code != "task_not_found":
                raise
            snapshot = research_routes.RESULT_STORE.load_task(identifier)
            origin = "sqlite"
        if snapshot["status"] == "running":
            raise ServiceError("Wait for Agent 2 research to finish.", 409, code="research_running")
        output = explain_result(snapshot.get("result"))
        output.update(task_id=identifier, origin=origin)
        return jsonify(output), 502 if output["status"] == "explanation_failed" else 200

    return routes
