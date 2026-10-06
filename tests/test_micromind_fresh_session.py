# tests/test_micromind_fresh_session.py
"""After an empty agent answer the chat's flow session is replaced (Session 126)."""
import asyncio
import json
import unittest
from unittest.mock import patch

from server.app.services.micromind import MicroMindClient


def run(coro):
    return asyncio.run(coro)


class FreshSessionAfterEmptyAnswerTests(unittest.TestCase):
    def make_client(self, answers):
        """A client whose flow call returns the queued answers (None = empty answer)."""
        client = MicroMindClient(api_url="http://flow.test")
        sent = []

        async def fake_once(payload, wait):
            sent.append(json.dumps(payload))
            answer = answers.pop(0)
            if answer is None:
                client._fail("agent", "empty_answer")
                return None
            client._ok()
            return {"text": answer}

        client._agent_once = fake_once
        return client, sent

    def ask(self, client, session_id="rsh-abc"):
        with patch("server.app.services.micromind.settings.USE_MICROMIND", True):
            return run(client.query_agent("question", "rsh1.token", session_id=session_id))

    def test_the_retry_after_an_empty_answer_uses_a_fresh_session(self):
        client, sent = self.make_client([None, "ok"])
        self.assertEqual(self.ask(client), {"text": "ok"})
        self.assertEqual(len(sent), 2)
        self.assertIn("rsh-abc", sent[0])
        self.assertNotIn("rsh-abc-r1", sent[0])
        self.assertIn("rsh-abc-r1", sent[1])

    def test_the_next_message_of_the_same_chat_stays_on_the_fresh_session(self):
        client, sent = self.make_client([None, "ok", "again"])
        self.ask(client)
        self.ask(client)
        self.assertEqual(len(sent), 3)
        self.assertIn("rsh-abc-r1", sent[2])

    def test_a_chat_without_empty_answers_keeps_its_own_session(self):
        client, sent = self.make_client(["ok", "again"])
        self.ask(client)
        self.ask(client)
        self.assertTrue(all("rsh-abc-r" not in item for item in sent))

    def test_no_session_id_stays_no_memory(self):
        client, sent = self.make_client([None, "ok"])
        self.assertEqual(self.ask(client, session_id=None), {"text": "ok"})
        self.assertEqual(len(sent), 2)

    def test_another_chat_is_not_affected(self):
        client, sent = self.make_client([None, "ok", "other"])
        self.ask(client, "rsh-abc")
        self.ask(client, "rsh-other")
        self.assertNotIn("-r1", sent[2])


if __name__ == "__main__":
    unittest.main()