"""Server-side Qwen connection through GroqCloud."""
import json
import os
import queue
import threading
import time

import requests

from . import gemini_client


API_URL = 'https://api.groq.com/openai/v1/chat/completions'
DEFAULT_MODEL = 'qwen/qwen3.8-27b'
_active_requests = threading.BoundedSemaphore(2)
ModelError = gemini_client.GeminiError


def _configuration():
    values = gemini_client.read_settings()
    key = os.environ.get('GROQ_API_KEY', values.get('GROQ_API_KEY', '')).strip()
    model = os.environ.get('GROQ_MODEL', values.get('GROQ_MODEL', DEFAULT_MODEL)).strip()
    if key.casefold() in ('your_key', 'your_api_key', 'your_groq_api_key', 'replace_me'):
        key = ''
    if key and (len(key) > 512 or any(char.isspace() for char in key)):
        raise ModelError('configuration_error', 'GROQ_API_KEY has an invalid format.', 503)
    if not model or len(model) > 150 or any(char.isspace() for char in model):
        raise ModelError('configuration_error', 'Set GROQ_MODEL to a valid Groq model name.', 503)
    return key, model


def configuration_status():
    key, model = _configuration()
    return {'configured': bool(key), 'model': model, 'connection_verified': False}


def _timeout_error():
    return ModelError('timeout', 'The Groq request timed out. Please try again.', 504)


def _perform_request(key, model, prompt, system_instruction, max_output_tokens, deadline, json_schema):
    if json_schema is not None:
        formatting = ('For the response format, wrap the requested JSON result inside a single top-level '
                      'property named "action". The response must be {"action": <the requested JSON object>}. '
                      'The contents of "action" must follow the task instructions above. Return only this JSON.')
        system_instruction = (system_instruction or '') + '\n' + formatting
    messages = []
    if system_instruction:
        messages.append({'role': 'system', 'content': system_instruction})
    messages.append({'role': 'user', 'content': prompt})
    payload = {'model': model, 'messages': messages, 'max_completion_tokens': max_output_tokens}
    if model == DEFAULT_MODEL:
        payload['reasoning_effort'] = 'none'
    if json_schema is not None:
        # Wrap the existing action union in an object for provider compatibility.
        payload['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': 'agent_action', 'strict': True,
            'schema': {'type': 'object', 'properties': {'action': json_schema},
                       'required': ['action'], 'additionalProperties': False}}}
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _timeout_error()
    try:
        with requests.post(API_URL, headers={'Authorization': 'Bearer ' + key}, json=payload,
                           timeout=(min(5, remaining), remaining), allow_redirects=False,
                           stream=True) as response:
            status = response.status_code
            if status in (401, 403):
                raise ModelError('access_denied', 'Groq rejected access. Check GROQ_API_KEY and model access.', 503)
            if status == 429:
                raise ModelError('quota_exceeded', 'Groq rate or usage quota reached. Check Groq limits and try again later.', 429)
            if status == 404:
                raise ModelError('model_unavailable', 'The configured Groq model is unavailable. Check GROQ_MODEL.', 503)
            if status == 400:
                raise ModelError('request_rejected', 'Groq rejected this request. Check its context size and model settings.', 502)
            if not 200 <= status < 300:
                raise ModelError('service_unavailable', 'Groq is temporarily unavailable. Please try again later.', 503)
            chunks, size = [], 0
            for chunk in response.iter_content(chunk_size=8192):
                if time.monotonic() >= deadline:
                    raise _timeout_error()
                size += len(chunk)
                if size > gemini_client.MAX_RESPONSE_BYTES:
                    raise ModelError('invalid_response', 'Groq returned a response that is too large.', 502)
                chunks.append(chunk)
            body = json.loads(b''.join(chunks))
    except requests.exceptions.Timeout:
        raise _timeout_error() from None
    except requests.RequestException:
        raise ModelError('connection_error', 'Could not reach Groq. Check your internet connection.', 503) from None
    except (ValueError, TypeError):
        raise ModelError('invalid_response', 'Groq returned an unreadable response.', 502) from None
    if time.monotonic() >= deadline:
        raise _timeout_error()
    try:
        choice = body['choices'][0]
        text = choice['message']['content']
        if choice.get('finish_reason') != 'stop' or not isinstance(text, str) or not text.strip():
            raise ValueError()
        if json_schema is not None:
            decoded = json.loads(text)
            if not isinstance(decoded, dict) or set(decoded) != {'action'}:
                raise ValueError()
            text = json.dumps(decoded['action'], ensure_ascii=False)
    except (KeyError, IndexError, TypeError, ValueError):
        raise ModelError('invalid_response', 'Groq returned an incomplete or invalid answer. Please try again.', 502) from None
    return {'status': 'ok', 'provider': 'groq', 'model': model, 'text': text.strip().replace(key, '[redacted]')}


def generate_text(prompt, *, system_instruction=None, max_output_tokens=2048, json_schema=None,
                  timeout_seconds=60):
    gemini_client.validate_input(prompt, system_instruction, max_output_tokens, json_schema)
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 240:
        raise ModelError('invalid_input', 'Invalid Groq request timeout.', 400)
    key, model = _configuration()
    if not key:
        raise ModelError('not_configured', 'Add GROQ_API_KEY to Junior Test/.env to enable Qwen through Groq.', 503)
    if not _active_requests.acquire(blocking=False):
        raise ModelError('busy', 'The Groq connection is busy. Please try again shortly.', 503)
    started = time.monotonic()
    deadline = started + timeout_seconds
    results = queue.Queue(maxsize=1)

    def run():
        try:
            result = _perform_request(key, model, prompt.strip(), system_instruction,
                                      max_output_tokens, deadline, json_schema)
        except ModelError as error:
            result = error
        except Exception:
            result = ModelError('connection_error', 'The Groq connection could not complete this request.', 502)
        finally:
            _active_requests.release()
        results.put(result)

    try:
        threading.Thread(target=run, name='groq-request', daemon=True).start()
    except Exception:
        _active_requests.release()
        raise ModelError('connection_error', 'Could not start the Groq request.', 503) from None
    try:
        result = results.get(timeout=max(0, deadline - time.monotonic()))
    except queue.Empty:
        raise _timeout_error() from None
    if isinstance(result, ModelError):
        raise result
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    return result
