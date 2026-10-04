# tests/test_micromind.py
"""Privacy regression tests for optional MicroMind provider logging."""

import io
import logging
import unittest
from unittest.mock import patch

from server.app.services.micromind import MicroMindClient


class _Response:
    status_code = 503
    text = "provider echoed confidential patient prompt"


class _Client:
    def __init__(self, failure=None):
        self.failure = failure

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        if self.failure:
            raise self.failure
        return _Response()


class MicroMindLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_response_body_is_not_written_to_logs(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger("server.app.services.micromind")
        previous_level = logger.level
        logger.setLevel(logging.WARNING)
        logger.addHandler(handler)
        try:
            with patch("server.app.services.micromind.settings.USE_MICROMIND", True), \
                    patch("server.app.services.micromind.httpx.AsyncClient", return_value=_Client()):
                result = await MicroMindClient("https://provider.invalid/predict").query({"question": "private prompt"})
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        self.assertIsNone(result)
        self.assertIn("503", output.getvalue())
        self.assertNotIn("confidential patient prompt", output.getvalue())

    async def test_exception_message_is_not_written_to_logs(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger = logging.getLogger("server.app.services.micromind")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            with patch("server.app.services.micromind.settings.USE_MICROMIND", True), \
                    patch("server.app.services.micromind.httpx.AsyncClient", return_value=_Client(RuntimeError("private prompt token=secret"))):
                result = await MicroMindClient("https://provider.invalid/predict").query({"question": "private prompt"})
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        self.assertIsNone(result)
        self.assertIn("RuntimeError", output.getvalue())
        self.assertNotIn("private prompt", output.getvalue())
        self.assertNotIn("secret", output.getvalue())


class MicroMindDisabledTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_flag_makes_no_network_call(self):
        with patch("server.app.services.micromind.settings.USE_MICROMIND", False), \
                patch("server.app.services.micromind.httpx.AsyncClient") as client:
            result = await MicroMindClient("https://provider.invalid/predict").query({"question": "private prompt"})
        self.assertIsNone(result)
        client.assert_not_called()

    async def test_empty_url_makes_no_network_call(self):
        # MicroMindClient("") falls back to settings.MICROMIND_API_URL, which holds the
        # real flow URL when server/.env sets it; clear it so the test does not depend on that file.
        with patch("server.app.services.micromind.settings.USE_MICROMIND", True), \
                patch("server.app.services.micromind.settings.MICROMIND_API_URL", ""), \
                patch("server.app.services.micromind.httpx.AsyncClient") as client:
            result = await MicroMindClient("").query({"question": "private prompt"})
        self.assertIsNone(result)
        client.assert_not_called()


if __name__ == "__main__":
    unittest.main()