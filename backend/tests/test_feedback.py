import os
# Force rate limiter to use in-memory storage for tests by clearing Upstash Redis env variables
os.environ["UPSTASH_REDIS_URL"] = ""
os.environ["UPSTASH_REDIS_TOKEN"] = ""

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from starlette.requests import Request
from starlette.datastructures import Headers

from app.models import Conversation, Message, Feedback
from app.routers.feedback import submit_feedback, get_negative_feedback
from app.schemas import FeedbackRequest


class TestFeedbackSystem(unittest.IsolatedAsyncioTestCase):

    @patch("app.routers.feedback.log_event", new_callable=AsyncMock)
    async def test_submit_feedback_happy_path(self, mock_log_event):
        # Setup mock db
        mock_db = AsyncMock()

        # Mock the assistant message
        mock_message = Message(
            id=123,
            conversation_id=456,
            role="assistant",
            content="This is the answer.",
            created_at=datetime.now(timezone.utc)
        )

        # Mock the preceding user message
        mock_user_message = Message(
            id=122,
            conversation_id=456,
            role="user",
            content="What is the question?",
            created_at=datetime.now(timezone.utc)
        )

        # Mock the conversation
        mock_conv = Conversation(
            id=456,
            title="Mock Title"
        )

        # Mock db execute returns:
        # First query: select(Message)
        # Second query: select(Feedback) (returns None - no duplicate)
        # Third query: select(Conversation)
        # Fourth query: select(Message) (preceding user message)
        mock_db_results = [
            MagicMock(scalar_one_or_none=lambda: mock_message),
            MagicMock(scalar_one_or_none=lambda: None),
            MagicMock(scalar_one_or_none=lambda: mock_conv),
            MagicMock(scalar_one_or_none=lambda: mock_user_message),
        ]
        
        async def mock_execute(statement, *args, **kwargs):
            return mock_db_results.pop(0) if mock_db_results else MagicMock(scalar_one_or_none=lambda: None)

        mock_db.execute.side_effect = mock_execute

        # Create a real Starlette Request object to satisfy slowapi
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/feedback",
            "headers": Headers().raw,
            "client": ("127.0.0.1", 12345),
            "app": MagicMock(),
        }
        mock_request = Request(scope)

        # Submit feedback
        req = FeedbackRequest(
            message_id=123,
            rating="not_helpful",
            comment="Not detailed"
        )

        fb = await submit_feedback(request=mock_request, body=req, db=mock_db, session_token="mock_session_token")

        # Verify new feedback record has snapshot fields populated
        self.assertEqual(fb.message_id, 123)
        self.assertEqual(fb.rating, "not_helpful")
        self.assertEqual(fb.comment, "Not detailed")
        self.assertEqual(fb.conversation_id, 456)
        self.assertEqual(fb.conversation_title, "Mock Title")
        self.assertEqual(fb.user_question, "What is the question?")
        self.assertEqual(fb.assistant_response, "This is the answer.")

        # Verify database commands called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        mock_log_event.assert_called_once_with(db=mock_db, event_type="feedback", query="not_helpful")

    async def test_submit_feedback_duplicate_prevention(self):
        mock_db = AsyncMock()

        # Mock the assistant message
        mock_message = Message(
            id=123,
            conversation_id=456,
            role="assistant",
            content="This is the answer."
        )

        # Mock existing feedback
        existing_fb = Feedback(
            id=999,
            message_id=123,
            rating="helpful",
            comment="Old feedback"
        )

        # Mock db execute returns:
        # First query: select(Message)
        # Second query: select(Feedback) (returns existing_fb)
        mock_db_results = [
            MagicMock(scalar_one_or_none=lambda: mock_message),
            MagicMock(scalar_one_or_none=lambda: existing_fb),
        ]
        
        async def mock_execute(statement, *args, **kwargs):
            return mock_db_results.pop(0) if mock_db_results else MagicMock(scalar_one_or_none=lambda: None)

        mock_db.execute.side_effect = mock_execute

        # Create a real Starlette Request object to satisfy slowapi
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/feedback",
            "headers": Headers().raw,
            "client": ("127.0.0.1", 12345),
            "app": MagicMock(),
        }
        mock_request = Request(scope)

        req = FeedbackRequest(
            message_id=123,
            rating="helpful",
            comment="New feedback"
        )

        fb = await submit_feedback(request=mock_request, body=req, db=mock_db, session_token="mock_session_token")

        # Verify duplicate was returned and no new record was added
        self.assertEqual(fb.id, 999)
        self.assertEqual(fb.comment, "Old feedback")
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    async def test_submit_feedback_bola_prevention(self):
        mock_db = AsyncMock()

        # Mock db execute returns None for the message select query
        mock_db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/feedback",
            "headers": Headers().raw,
            "client": ("127.0.0.1", 12345),
            "app": MagicMock(),
        }
        mock_request = Request(scope)

        req = FeedbackRequest(
            message_id=999,
            rating="helpful",
            comment="Should fail"
        )

        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            await submit_feedback(request=mock_request, body=req, db=mock_db, session_token="unauthorized_session")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Message not found")
        mock_db.add.assert_not_called()

    async def test_get_negative_feedback_admin(self):
        mock_db = AsyncMock()

        # Mock feedback list
        fb1 = Feedback(
            id=1,
            user_question="Q1",
            assistant_response="A1",
            conversation_title="Title1",
            rating="not_helpful",
            created_at=datetime.now(timezone.utc)
        )

        # Mock execute returns:
        # First query: count total
        # Second query: fetch list
        mock_db_results = [
            MagicMock(scalar_one=lambda: 1),
            MagicMock(scalars=lambda: MagicMock(all=lambda: [fb1])),
        ]
        
        async def mock_execute(statement, *args, **kwargs):
            return mock_db_results.pop(0)

        mock_db.execute.side_effect = mock_execute

        # Create a real Starlette Request object to satisfy slowapi
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/api/admin/feedback/negative",
            "headers": Headers().raw,
            "client": ("127.0.0.1", 12345),
            "app": MagicMock(),
        }
        mock_request = Request(scope)

        res = await get_negative_feedback(
            request=mock_request,
            page=1,
            limit=10,
            search="Q1",
            db=mock_db
        )

        self.assertEqual(res.total, 1)
        self.assertEqual(res.items[0].user_question, "Q1")
        self.assertEqual(res.page, 1)

    @patch("app.routers.feedback.log_event", new_callable=AsyncMock)
    async def test_submit_general_feedback_happy_path(self, mock_log_event):
        # Setup mock db
        mock_db = AsyncMock()

        # Create a real Starlette Request object to satisfy slowapi
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/feedback",
            "headers": Headers().raw,
            "client": ("127.0.0.1", 12345),
            "app": MagicMock(),
        }
        mock_request = Request(scope)

        # Submit general feedback (message_id is None)
        req = FeedbackRequest(
            message_id=None,
            rating="not_helpful",
            comment="This is a general suggestion."
        )

        fb = await submit_feedback(request=mock_request, body=req, db=mock_db, session_token="mock_session_token")

        # Verify new feedback record has snapshot fields populated
        self.assertIsNone(fb.message_id)
        self.assertEqual(fb.rating, "not_helpful")
        self.assertEqual(fb.comment, "This is a general suggestion.")
        self.assertIsNone(fb.conversation_id)
        self.assertEqual(fb.conversation_title, "General Suggestion")
        self.assertEqual(fb.user_question, "N/A")
        self.assertEqual(fb.assistant_response, "N/A")

        # Verify database commands called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        mock_log_event.assert_called_once_with(db=mock_db, event_type="feedback", query="not_helpful")
