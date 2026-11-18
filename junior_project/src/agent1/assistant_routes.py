"""Background assistant turns with SQLite chat ownership enforced on every route."""
import copy
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from flask import Blueprint, request, jsonify
from ai_connection.model_client import ModelError, validate_provider
from shared import ServiceError
from shared.chat_store import CHAT_STORE
from .assistant_agent import run_turn


class AssistantJobs:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(2)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="assistant")

    def cleanup(self):
        now = time.monotonic()
        with self.lock:
            finished = sorted(((key, job) for key, job in self.jobs.items() if job["status"] not in
                               {"running", "needs_clarification"}), key=lambda pair: pair[1]["updated"])
            for index, (key, job) in enumerate(finished):
                if now - job["updated"] > 3600 or index < len(finished) - 30:
                    del self.jobs[key]

    @staticmethod
    def public(job):
        return copy.deepcopy({key: value for key, value in job.items() if key not in {"state", "updated"}})

    def create(self, body):
        if (not isinstance(body, dict) or set(body) - {"chat_id", "turn_id", "message", "provider"}
                or not {"chat_id", "message"} <= set(body)):
            raise ServiceError("Send a message in a saved conversation.", 400)
        provider = validate_provider(body.get("provider", "auto"))
        message = body["message"]
        identifier = body.get("turn_id", str(uuid4()))
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
            raise ServiceError("Enter between 1 and 2,000 characters.", 400)
        if not isinstance(identifier, str) or not 1 <= len(identifier) <= 100:
            raise ServiceError("Invalid message reference.", 400)
        chat_id = body["chat_id"]
        self.cleanup()
        with self.lock:
            if not self.slots.acquire(blocking=False):
                raise ServiceError("Two assistant requests are active. Please wait.", 429)
            try:
                # Reserve the chat before reading context so concurrent messages cannot race.
                snapshot, created = CHAT_STORE.start_turn(chat_id, identifier, message.strip(), provider=provider)
                if not created:
                    self.slots.release()
                    return snapshot
                self.jobs[identifier] = {**snapshot, "state": None, "updated": time.monotonic()}
                context = CHAT_STORE.load_chat(chat_id)
                history = []
                for turn in context["turns"]:
                    if turn["turn_id"] == identifier:
                        continue
                    history.append({"role": "user", "text": turn["message"]})
                    history.append({"role": "assistant", "text": turn.get("text", ""),
                                    "outputs": turn.get("outputs", [])})
                references = [graph["reference"] for graph in context["graphs"]]
                self.pool.submit(self.execute, identifier, message.strip(), history, references)
            except Exception:
                self.slots.release()
                if identifier in self.jobs:
                    self.jobs[identifier].update(status="failed", text="Could not start this request. Please try again.")
                    CHAT_STORE.save_turn(chat_id, self.public(self.jobs[identifier]))
                raise
        return snapshot

    def execute(self, identifier, message=None, history=None, references=None, previous=None, selections=None):
        chat_id = self.jobs[identifier]["chat_id"]

        def emit(event):
            with self.lock:
                self.jobs[identifier]["events"] = (self.jobs[identifier]["events"] + [event])[-100:]
        try:
            state = run_turn(message, history, references, emit, previous, selections, chat_id=chat_id,
                             provider=self.jobs[identifier].get("provider", "auto"))
            with self.lock:
                self.jobs[identifier].update(
                    status=state["status"], text=state.get("text", ""), outputs=state["outputs"],
                    model_calls=state.get("model_calls", []),
                    choices=state.get("action", {}).get("args", {}) if state["status"] == "needs_clarification" else {},
                    state=state if state["status"] == "needs_clarification" else None)
        except (ServiceError, ModelError) as error:
            with self.lock:
                self.jobs[identifier].update(status="failed", text=str(error), state=None)
        except Exception:
            logging.getLogger(__name__).exception("Assistant turn %s stopped unexpectedly.", identifier)
            with self.lock:
                self.jobs[identifier].update(status="failed", text="The assistant stopped unexpectedly. Please try again.", state=None)
        finally:
            try:
                with self.lock:
                    job = self.jobs[identifier]
                    job["updated"] = time.monotonic()
                    CHAT_STORE.save_turn(chat_id, self.public(job))
            except ServiceError:
                with self.lock:
                    self.jobs[identifier].update(status="failed", text="The reply could not be saved. Reopen this chat to check its saved graphs.")
            finally:
                self.slots.release()

    def snapshot(self, identifier, chat_id=None):
        self.cleanup()
        with self.lock:
            job = self.jobs.get(identifier)
            if job is not None and job.get("chat_id") == chat_id:
                if job["status"] != "running":
                    CHAT_STORE.save_turn(chat_id, self.public(job))
                return self.public(job)
        if chat_id is None:
            raise ServiceError("Select this request's conversation.", 404)
        return CHAT_STORE.load_turn(chat_id, identifier)

    def resume(self, identifier, body, chat_id=None):
        with self.lock:
            job = self.jobs.get(identifier)
            if not job or job.get("chat_id") != chat_id or job["status"] != "needs_clarification" or not job["state"]:
                raise ServiceError("This request is not awaiting a choice in this chat.", 409)
            choices = body.get("selections") if isinstance(body, dict) and set(body) == {"selections"} else None
            if not isinstance(choices, dict) or not choices or set(choices) - {"first", "second"}:
                raise ServiceError("Choose the intended concepts.", 400)
            for side, value in job["choices"].items():
                if not value.get("selected") and choices.get(side) not in {c["id"] for c in value["candidates"]}:
                    raise ServiceError("Choose only returned concepts.", 400)
            for side, selected in choices.items():
                if selected not in {c["id"] for c in job["choices"].get(side, {}).get("candidates", [])}:
                    raise ServiceError("Choose only returned concepts.", 400)
            if not self.slots.acquire(blocking=False):
                raise ServiceError("The assistant is busy. Please wait.", 429)
            previous = job["state"]
            prior = self.public(job)
            try:
                job.update(status="running", choices={})
                CHAT_STORE.save_turn(chat_id, self.public(job))
                self.pool.submit(self.execute, identifier, previous=previous, selections=choices)
            except Exception:
                job.update(prior)
                CHAT_STORE.save_turn(chat_id, prior)
                self.slots.release()
                raise


ASSISTANT_JOBS = AssistantJobs()


def create_assistant_blueprint():
    CHAT_STORE.interrupt_unfinished()
    routes = Blueprint("agent1", __name__)

    @routes.errorhandler(ModelError)
    @routes.errorhandler(ServiceError)
    def error_response(error):
        return jsonify({"error": str(error), "code": error.code}), error.status

    @routes.get("/api/assistant/chats")
    def list_chats():
        return jsonify({"chats": CHAT_STORE.list_chats()})

    @routes.post("/api/assistant/chats")
    def create_chat():
        if request.get_json(silent=True) != {}:
            raise ServiceError("Create an empty conversation.", 400)
        return jsonify(CHAT_STORE.create_chat()), 201

    @routes.get("/api/assistant/chats/<int:chat_id>")
    def load_chat(chat_id):
        chat = CHAT_STORE.load_chat(chat_id)
        # Merge live progress while the durable snapshot remains available after restart.
        chat["turns"] = [ASSISTANT_JOBS.snapshot(turn["turn_id"], chat_id) for turn in chat["turns"]]
        return jsonify(chat)

    @routes.post("/api/assistant/turns")
    def create():
        snapshot = ASSISTANT_JOBS.create(request.get_json(silent=True))
        return jsonify(snapshot), 202 if snapshot["status"] == "running" else 200

    @routes.get("/api/assistant/chats/<int:chat_id>/turns/<identifier>")
    def status(chat_id, identifier):
        return jsonify(ASSISTANT_JOBS.snapshot(identifier, chat_id))

    @routes.post("/api/assistant/chats/<int:chat_id>/turns/<identifier>/resume")
    def resume(chat_id, identifier):
        ASSISTANT_JOBS.resume(identifier, request.get_json(silent=True), chat_id)
        return jsonify({"turn_id": identifier, "status": "running"}), 202

    return routes
