"""Plain test-page API; bounded, ephemeral local jobs with live progress."""
import copy
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from flask import Blueprint, jsonify, request
from shared import RunContext, ServiceError
from .research_schemas import parse_request


class ResearchJobs:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(2)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent2")

    def cleanup(self):
        with self.lock:
            now = time.monotonic()
            done = sorted(((key, job) for key, job in self.jobs.items() if job["status"] != "running"),
                          key=lambda item: item[1]["updated"])
            for index, (key, job) in enumerate(done):
                if now - job["updated"] > 1800 or index < len(done) - 20:
                    del self.jobs[key]

    def create(self, body):
        parsed = parse_request(body)
        self.cleanup()
        if not self.slots.acquire(blocking=False):
            raise ServiceError("Two research runs are already active. Wait for one to finish.", 429,
                               retryable=False, code="busy")
        identifier = str(uuid4())
        job = {"task_id": identifier, "status": "running", "request": parsed, "events": [],
               "result": None, "state": None, "updated": time.monotonic()}

        def progress(event):
            with self.lock:
                job["events"].append(dict(event))
                job["updated"] = time.monotonic()

        timeout = os.environ.get("AGENT2_TIMEOUT_SECONDS", "180")
        try:
            timeout = max(30, min(300, float(timeout)))
        except ValueError:
            timeout = 180
        job["context"] = RunContext(timeout_seconds=timeout, on_event=progress)
        with self.lock:
            self.jobs[identifier] = job
        self.pool.submit(self.execute, identifier)
        return identifier

    def execute(self, identifier, selections=None):
        with self.lock:
            job = self.jobs[identifier]
        try:
            from .research_agent import run_research
            result, state = run_research(job["request"], context=job["context"],
                                         previous_state=job["state"], selections=selections)
            with self.lock:
                job["result"] = result
                job["status"] = result["status"]
                # Retain only the resolver state while waiting for a choice.
                # No paper collection is retained after a completed run.
                job["state"] = state if result["status"] == "needs_clarification" else None
                if job["state"] is None:
                    job["context"].cache.clear()
        except Exception:
            # Never return raw provider bodies, credentials, or private graph state.
            with self.lock:
                job["status"] = "failed"
                job["state"] = None
                job["context"].cache.clear()
                job["result"] = {"status": "failed", "yearly_counts": [], "counted_papers": None,
                                 "validation": {"passed": False}, "uses_llm": False,
                                 "error": {"code": "internal_error", "message": "Research stopped because of an unexpected backend error. Check the backend console."},
                                 "events": list(job["events"])}
            import logging
            # No exception payload is logged: transport exceptions can include keys.
            logging.getLogger(__name__).error("Agent 2 task %s stopped with an internal error.", identifier)
        finally:
            with self.lock:
                job["updated"] = time.monotonic()
            self.slots.release()

    def snapshot(self, identifier):
        self.cleanup()
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None:
                raise ServiceError("This test run expired or the backend restarted. Start a new run.", 404,
                                   retryable=False, code="task_not_found")
            return copy.deepcopy({key: job[key] for key in ("task_id", "status", "request", "events", "result")})

    def resume(self, identifier, body):
        if not isinstance(body, dict) or not isinstance(body.get("selections"), dict) or not body["selections"]:
            raise ServiceError("Choose the intended concepts before continuing.", 400, code="invalid_selection")
        with self.lock:
            job = self.jobs.get(identifier)
            if job is None:
                raise ServiceError("This run is no longer available.", 404, code="task_not_found")
            if job["status"] != "needs_clarification":
                raise ServiceError("This run is not waiting for clarification.", 409, code="invalid_state")
            selections = body["selections"]
            resolution = job["state"]["resolution"]
            for side, identifier_value in selections.items():
                if side not in resolution or identifier_value not in {item["id"] for item in resolution[side]["candidates"]}:
                    raise ServiceError("Choose only candidates returned for this run.", 400, code="invalid_selection")
            for side, resolved in resolution.items():
                if not resolved["selected"] and side not in selections:
                    raise ServiceError("Select an intended meaning for each ambiguous concept.", 400, code="invalid_selection")
            if not self.slots.acquire(blocking=False):
                raise ServiceError("Two research runs are already active. Wait for one to finish.", 429, code="busy")
            # Waiting for the researcher does not consume the execution deadline.
            # Request attempt counters and cached resolution remain unchanged.
            job["context"].started = time.monotonic()
            job["status"] = "running"
            job["result"] = None
            self.pool.submit(self.execute, job["task_id"], dict(selections))


JOBS = ResearchJobs()


def create_research_blueprint():
    routes = Blueprint("agent2", __name__)

    @routes.errorhandler(ServiceError)
    def service_error(error):
        return jsonify({"status": "failed", "code": error.code, "error": str(error)}), error.status

    @routes.post("/api/agent2/tasks")
    def create_task():
        identifier = JOBS.create(request.get_json(silent=True))
        return jsonify({"task_id": identifier, "status": "running"}), 202

    @routes.get("/api/agent2/tasks/<identifier>")
    def task_status(identifier):
        return jsonify(JOBS.snapshot(identifier))

    @routes.post("/api/agent2/tasks/<identifier>/resume")
    def resume_task(identifier):
        JOBS.resume(identifier, request.get_json(silent=True))
        return jsonify({"task_id": identifier, "status": "running"}), 202

    return routes
