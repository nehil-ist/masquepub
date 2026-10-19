"""Answers PHP gave on its own: the JSON 'Server error' for any crash and the JSON 'Not found.' for an unknown action."""
import logging

from flask import Flask
from werkzeug.exceptions import HTTPException

from .actions.base import Reply

log = logging.getLogger("masque")


class ErrorPages:
    """Plugs the crash and not-found answers into a Flask app (PHP: set_exception_handler and the final out(['e'=>'Not found.'], 404))."""

    CRASH = "Server error. Please try again."
    MISSING = "Not found."
    STARTING = "Starting up. Please try again in a moment."

    def install(self, app: Flask) -> None:
        app.register_error_handler(Exception, self.crash)

    def crash(self, exc: Exception):
        if isinstance(exc, HTTPException):  # 404/405/413 raised by Flask itself keep their own status
            return Reply.error(exc.description or self.CRASH, exc.code or 500).to_response()
        log.exception("unhandled error")
        return Reply.error(self.CRASH, 500).to_response()

    def not_found(self):
        return Reply.error(self.MISSING, 404).to_response()

    def starting(self):
        return Reply.error(self.STARTING, 503).to_response()
