"""Reusable server-side Gemini connection shared by Assistant and Agent 3."""
import json
import logging
import os
import queue
import re
import threading
import time
from pathlib import Path

import requests

API_URL = 'https://generativelanguage.googleapis.com/v1beta/interactions'
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
TIMEOUT_SECONDS = 240
MAX_RESPONSE_BYTES = 1024 * 1024
ENV_PATH = Path(__file__).resolve().parents[2] / '.env'
_active_requests = threading.BoundedSemaphore(2)


class GeminiError(Exception):  
    """A safe error message; never include provider responses or credentials."""

    # This defines the constructor, which runs automatically when you create a GeminiError object.
    def __init__(self, code, message, status=502, *, provider_status=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.provider_status = provider_status


# Reads Gemini settings from .env; existing process environment values take priority.
def read_settings():
    """Read provider settings without changing the process environment."""
    values = {}  
    path = ENV_PATH
    try:
        lines = path.read_text(encoding='utf-8-sig').splitlines() if path.exists() else []
    except (OSError, UnicodeError): 
        raise GeminiError('configuration_error', 'Could not read Gemini settings from .env.', 503) from None
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1) 
        name, value = name.strip(), value.strip()
        if name not in ('GEMINI_API_KEY', 'GEMINI_MODEL', 'GROQ_API_KEY', 'GROQ_MODEL',
                        'GEMINI_TIMEOUT_SECONDS', 'GROQ_TIMEOUT_SECONDS'):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def _configuration():
    values = read_settings()
    key = os.environ.get('GEMINI_API_KEY', values.get('GEMINI_API_KEY', '')).strip()
    model = os.environ.get('GEMINI_MODEL', values.get('GEMINI_MODEL', DEFAULT_MODEL)).strip()
    if not re.fullmatch(r'gemini-[a-zA-Z0-9.-]{1,100}', model):  # Checks whether the model name matches the permitted format.
        raise GeminiError('configuration_error', 'Set GEMINI_MODEL to a valid Gemini model name.', 503)
    if key.casefold() in ('your_key', 'your_api_key', 'your_gemini_api_key', 'replace_me'):
        key = ''
    if key and (len(key) > 512 or any(char.isspace() for char in key)):
        raise GeminiError('configuration_error', 'GEMINI_API_KEY has an invalid format.', 503)
    return key, model


def configuration_status():
    """Configuration only; no network call and no claim of live connectivity."""
    key, model = _configuration()
    return {
        'status': 'configured' if key else 'not_configured',
        'configured': bool(key),
        'connection_verified': False, 
        'model': model,
        'timeout_seconds': TIMEOUT_SECONDS, 
        'message': 'Key configured. Run the connection check to verify access.' if key else
                   'Add GEMINI_API_KEY to Junior Test/.env to enable the connection.',
    }


def _timeout_error():
    return GeminiError('timeout', 'The Gemini request timed out. Please try again.', 504)


# This function is responsible for communicating directly with the Google Gemini API.
def _perform_request(key, model, prompt, system_instruction, max_output_tokens, deadline, json_schema=None):
    payload = {
        'model': model,
        'input': prompt,
        'store': False, 
        'generation_config': {
            'max_output_tokens': max_output_tokens,
            'thinking_level': 'minimal' if model == 'gemini-3.5-flash-lite' else 'low',
        },
    }

    if system_instruction:
        payload['system_instruction'] = system_instruction
    
    if json_schema is not None:
        payload['response_format'] = {'type': 'text', 'mime_type': 'application/json', 'schema': json_schema}
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise _timeout_error()
    try:   
        # Sends an HTTP POST request containing your data.
        with requests.post(API_URL,  
                        headers={'x-goog-api-key': key}, 
                        json=payload, 
                        timeout=(min(5, remaining), remaining),
                        allow_redirects=False, 
                        stream=True) as response: 

            status = response.status_code  # Read the HTTP status code; 200 means success, while other values may indicate errors.
            if not 200 <= status < 300:
                logging.getLogger(__name__).warning('Gemini API returned HTTP %s.', status)
            if status in (401, 403): # Authentication or permission denied
                raise GeminiError('access_denied', 'Gemini rejected access. Check your API key and project permissions.', 503)
            if status == 404: # Requested resource/model not found.
                raise GeminiError('model_unavailable', 'The configured Gemini model is unavailable. Check GEMINI_MODEL and account access.', 503)
            if status == 429: # Rate or usage quota exceeded.
                raise GeminiError('quota_exceeded', 'Gemini rate or usage quota reached. Check AI Studio limits and try again later.', 429, provider_status=status)
            if status == 400: # Bad request, report that Gemini rejected the request.
                raise GeminiError('request_rejected', 'Gemini rejected this request. Check model support and API settings.', 502)
            if status in (500, 502, 503, 504):
                raise GeminiError('service_unavailable', 'The configured Gemini model is temporarily unavailable. Try again later or use another model.', 503, provider_status=status)
            if not 200 <= status < 300: # Catch unexpected provider errors.
                raise GeminiError('provider_error', 'Gemini is unavailable or returned an unexpected response. Try again later.', 502)

            # Reading Gemini response.
            chunks, size = [], 0 
            for chunk in response.iter_content(chunk_size=8192): 
                if time.monotonic() >= deadline: 
                    raise _timeout_error()
                size += len(chunk) 
                if size > MAX_RESPONSE_BYTES: 
                    raise GeminiError('invalid_response', 'Gemini returned a response that is too large.', 502)
                chunks.append(chunk) 
            body = json.loads(b''.join(chunks)) 
    
    except requests.exceptions.Timeout:
        raise _timeout_error() from None
    except requests.exceptions.SSLError: # Catches secure HTTPS connection errors.
        raise GeminiError('connection_error', 'Could not establish a secure connection to Gemini.', 503) from None
    except requests.RequestException: # Catches other Requests networking errors.
        raise GeminiError('connection_error', 'Could not reach Gemini. Check your internet connection.', 503) from None
    except (ValueError, TypeError):  # Handles unreadable or invalid JSON data.
        raise GeminiError('invalid_response', 'Gemini returned an unreadable response.', 502) from None

    if time.monotonic() >= deadline:
        raise _timeout_error()
    if not isinstance(body, dict) or body.get('status') != 'completed':
        raise GeminiError('incomplete_response', 'Gemini did not return a completed answer.', 502)
    
    texts = []  
    steps = body.get('steps') 
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict) or step.get('type') != 'model_output':
                continue
            content = step.get('content')
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text' and isinstance(item.get('text'), str):
                    texts.append(item['text'])

    text = '\n'.join(texts).strip()
    if not text:
        raise GeminiError('empty_response', 'Gemini returned no usable answer. The response may have been blocked or exhausted its output limit.', 502)
    return {'status': 'ok',
            'model': model,
            'text': text.replace(key, '[redacted]')} 


def validate_input(prompt, system_instruction, max_output_tokens, json_schema):

    if not isinstance(prompt, str) or not prompt.strip():
        raise GeminiError('invalid_input', 'Provide a non-empty text prompt.', 400)
    if len(prompt) > 1000000:
        raise GeminiError('context_too_large', 'This chat exceeds the supported context size. Its data is saved. Start a new chat for further research.', 400)
    
    if system_instruction is not None and (not isinstance(system_instruction, str) or len(system_instruction) > 20000):
        raise GeminiError('invalid_input', 'System instructions must be text of at most 20,000 characters.', 400)

    if type(max_output_tokens) is not int or not 32 <= max_output_tokens <= 4096:
        raise GeminiError('invalid_input', 'Output limit must be an integer between 32 and 4,096 tokens.', 400)
    if json_schema is not None and not isinstance(json_schema, dict):
        raise GeminiError('invalid_input', 'JSON schema must be an object.', 400)


def generate_text(prompt, *, system_instruction=None, max_output_tokens=2048, json_schema=None,
                  timeout_seconds=None):
    validate_input(prompt, system_instruction, max_output_tokens, json_schema)
    if timeout_seconds is None:
        timeout_seconds = TIMEOUT_SECONDS
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= TIMEOUT_SECONDS:
        raise GeminiError('invalid_input', 'Invalid Gemini request timeout.', 400)
    key, model = _configuration()
    if not key:
        raise GeminiError('not_configured', 'Add GEMINI_API_KEY to Junior Test/.env before checking the connection.', 503)
    if not _active_requests.acquire(blocking=False):
        raise GeminiError('busy', 'The Gemini connection is busy. Try again after the current requests finish.', 503)
    started = time.monotonic() 
    deadline = started + timeout_seconds
    result_queue = queue.Queue(maxsize=1)

    def run():
        try:
            result = _perform_request(key, model, prompt.strip(), system_instruction, max_output_tokens, deadline, json_schema)
        except GeminiError as error:
            result = error
        except Exception:
            result = GeminiError('connection_error', 'The Gemini connection could not complete this request.', 502)
        finally:
            _active_requests.release()
        result_queue.put(result)

    try:
        threading.Thread(target=run, name='gemini-request', daemon=True).start()
    except Exception:
        _active_requests.release()
        raise GeminiError('connection_error', 'Could not start the Gemini request.', 503) from None

    try:
        result = result_queue.get(timeout=max(0, deadline - time.monotonic()))
    except queue.Empty:
        raise _timeout_error() from None
    if isinstance(result, GeminiError):
        raise result
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    return result


def check_connection():
    """Test whether your application can successfully communicate with Gemini."""
    return generate_text('Reply with only: Gemini connection is working.', max_output_tokens=2048)

if __name__ == '__main__':
    import argparse 
    parser = argparse.ArgumentParser(description='Check the server-side Gemini connection.')
    parser.add_argument('--check', 
                        action='store_true', 
                        help='Make one real Gemini request; consumes API quota.')
    args = parser.parse_args() 
    try:
        print(json.dumps(check_connection() if args.check else configuration_status(), indent=2))
    except GeminiError as error:
        print(json.dumps({'status': 'error', 'code': error.code, 'error': str(error)}, indent=2))
        raise SystemExit(1)

