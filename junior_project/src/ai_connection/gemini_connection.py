"""This  will make Gimini to connect to flask, but This code does not directly communicate with Gemini. It calls functions
from gemini_client.py, which handles the actual Gemini requests. """
from flask import Blueprint, jsonify, request

from .gemini_client import GeminiError, check_connection, configuration_status, generate_text


def create_gemini_blueprint():
    blueprint = Blueprint('gemini_connection', __name__, url_prefix='/api/assistant/connection')

    @blueprint.errorhandler(GeminiError)
    def handle_gemini_error(error):
        return jsonify({'status': 'error', 'code': error.code, 'error': str(error)}), error.status

    @blueprint.get('/status')
    def status():
        return jsonify(configuration_status())

    @blueprint.post('/test')
    def test_connection():
        return jsonify({**check_connection(), 'connection_verified': True})

    @blueprint.post('/message')
    def message():
        # This is a single-message connection, without agents or saved memory.
        body = request.get_json(silent=True)
        text = body.get('message') if isinstance(body, dict) else None
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise GeminiError('invalid_input', 'Enter a message between 1 and 2,000 characters.', 400)
        result = generate_text(text.strip())
        return jsonify({**result, 'connection_verified': True})

    return blueprint
