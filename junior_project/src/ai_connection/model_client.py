"""One model interface for explicit provider selection and Gemini-first fallback."""
import logging
import os

from . import gemini_client, groq_client


# Keep the existing safe exception contract for current routes and callers.
ModelError = gemini_client.GeminiError
PROVIDERS = ('auto', 'gemini', 'groq')
FALLBACK_ERRORS = frozenset({'quota_exceeded', 'service_unavailable', 'connection_error', 'timeout',
                             'busy', 'not_configured', 'model_unavailable', 'access_denied'})


def validate_provider(provider):
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ModelError('invalid_input', 'Choose Auto, Gemini, or Groq.', 400)
    return provider


def _timeout_setting(name, default):
    values = gemini_client.read_settings()
    raw = os.environ.get(name, values.get(name, str(default)))
    try:
        seconds = int(raw)
        if not 1 <= seconds <= 240:
            raise ValueError()
    except (TypeError, ValueError):
        raise ModelError('configuration_error', f'Set {name} to a whole number between 1 and 240.', 503) from None
    return seconds


def generate_text(prompt, *, system_instruction=None, max_output_tokens=2048, json_schema=None,
                  provider='auto'):
    validate_provider(provider)
    gemini_client.validate_input(prompt, system_instruction, max_output_tokens, json_schema)
    arguments = {'system_instruction': system_instruction, 'max_output_tokens': max_output_tokens,
                 'json_schema': json_schema}
    if provider == 'groq':
        return groq_client.generate_text(prompt, **arguments,
                                        timeout_seconds=_timeout_setting('GROQ_TIMEOUT_SECONDS', 60))
    try:
        reply = gemini_client.generate_text(prompt, **arguments,
                                           timeout_seconds=_timeout_setting('GEMINI_TIMEOUT_SECONDS', 30))
        return {**reply, 'provider': 'gemini'}
    except ModelError as error:
        if provider != 'auto' or error.code not in FALLBACK_ERRORS:
            raise
        logging.getLogger(__name__).warning('Gemini failed (%s, HTTP %s); trying Groq.',
                                           error.code, error.provider_status)
    try:
        return groq_client.generate_text(prompt, **arguments,
                                        timeout_seconds=_timeout_setting('GROQ_TIMEOUT_SECONDS', 60))
    except ModelError as error:
        raise ModelError('providers_unavailable',
                         'Gemini could not answer and the Groq backup also failed. ' + str(error),
                         error.status) from None


def configuration_status():
    primary = gemini_client.configuration_status()
    backup = groq_client.configuration_status()
    configured = primary['configured'] or backup['configured']
    return {**primary, 'configured': configured, 'status': 'configured' if configured else 'not_configured',
            'providers': {'gemini': primary, 'groq': backup}, 'default_provider': 'auto'}
