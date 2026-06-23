import unittest
import json
from unittest.mock import MagicMock, patch

from app.services.progress_service import (
    update_progress,
    get_progress,
    get_session_progress,
    clear_progress,
    STAGE_REWRITING,
    STAGE_RETRIEVING,
    STAGE_RERANKING,
    STAGE_GENERATING,
    STAGE_COMPLETE,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETED,
    STATUS_FAILED,
)
from app.rag.pipeline import run_rag_pipeline
from app.rag.errors import RagPipelineError


class TestProgressService(unittest.TestCase):

    def setUp(self):
        # Force get_redis to return None so that these tests always use the in-memory fallback
        # and do not attempt any real DNS/network calls that get blocked.
        self.get_redis_patcher = patch("app.services.progress_service.get_redis", return_value=None)
        self.mock_get_redis = self.get_redis_patcher.start()
        clear_progress(101)
        clear_progress(102)

    def tearDown(self):
        self.get_redis_patcher.stop()
        clear_progress(101)
        clear_progress(102)

    def test_update_and_get_progress(self):
        # Default behavior
        status = get_progress(101)
        self.assertEqual(status["stage"], STAGE_COMPLETE)
        self.assertEqual(status["status"], STATUS_COMPLETED)
        self.assertIsNone(status["error_message"])

        # Update to custom state
        update_progress(
            conversation_id=101,
            session_id="session-xyz",
            request_id="req-1",
            stage=STAGE_REWRITING,
            status=STATUS_IN_PROGRESS,
        )

        status = get_progress(101)
        self.assertEqual(status["stage"], STAGE_REWRITING)
        self.assertEqual(status["status"], STATUS_IN_PROGRESS)
        self.assertEqual(status["request_id"], "req-1")
        self.assertIsNone(status["error_message"])

    def test_get_session_progress(self):
        # Set up multiple active items
        update_progress(
            conversation_id=101,
            session_id="sess-A",
            request_id="req-A",
            stage=STAGE_RETRIEVING,
            status=STATUS_IN_PROGRESS,
        )
        update_progress(
            conversation_id=102,
            session_id="sess-A",
            request_id="req-B",
            stage=STAGE_GENERATING,
            status=STATUS_IN_PROGRESS,
        )
        update_progress(
            conversation_id=103,
            session_id="sess-B",
            request_id="req-C",
            stage=STAGE_GENERATING,
            status=STATUS_IN_PROGRESS,
        )

        # Get for sess-A
        sess_a_progress = get_session_progress("sess-A")
        self.assertEqual(len(sess_a_progress), 2)
        self.assertEqual(sess_a_progress["101"]["request_id"], "req-A")
        self.assertEqual(sess_a_progress["101"]["stage"], STAGE_RETRIEVING)
        self.assertEqual(sess_a_progress["102"]["request_id"], "req-B")
        self.assertEqual(sess_a_progress["102"]["stage"], STAGE_GENERATING)

        # Get for sess-B
        sess_b_progress = get_session_progress("sess-B")
        self.assertEqual(len(sess_b_progress), 1)
        self.assertEqual(sess_b_progress["103"]["request_id"], "req-C")

        # Cleanup
        clear_progress(103)


class TestProgressServiceRedis(unittest.TestCase):

    def setUp(self):
        # Mock Upstash Redis client
        self.mock_redis = MagicMock()
        self.get_redis_patcher = patch("app.services.progress_service.get_redis", return_value=self.mock_redis)
        self.mock_get_redis = self.get_redis_patcher.start()

    def tearDown(self):
        self.get_redis_patcher.stop()

    def test_update_progress_redis(self):
        update_progress(
            conversation_id=101,
            session_id="sess-xyz",
            request_id="req-123",
            stage=STAGE_REWRITING,
            status=STATUS_IN_PROGRESS,
            error_message="some error"
        )
        self.mock_redis.set.assert_called_once()
        args, kwargs = self.mock_redis.set.call_args
        self.assertEqual(args[0], "campusgpt:progress:101")
        val = json.loads(args[1])
        self.assertEqual(val["session_id"], "sess-xyz")
        self.assertEqual(val["request_id"], "req-123")
        self.assertEqual(val["stage"], STAGE_REWRITING)
        self.assertEqual(val["status"], STATUS_IN_PROGRESS)
        self.assertEqual(val["error_message"], "some error")
        self.assertEqual(kwargs.get("ex"), 300)

    def test_get_progress_redis(self):
        data = {
            "session_id": "sess-xyz",
            "request_id": "req-123",
            "stage": STAGE_RETRIEVING,
            "status": STATUS_IN_PROGRESS,
            "error_message": None,
        }
        self.mock_redis.get.return_value = json.dumps(data)

        status = get_progress(101)
        self.mock_redis.get.assert_called_once_with("campusgpt:progress:101")
        self.assertEqual(status["stage"], STAGE_RETRIEVING)
        self.assertEqual(status["status"], STATUS_IN_PROGRESS)
        self.assertEqual(status["request_id"], "req-123")

    def test_get_session_progress_redis(self):
        self.mock_redis.scan.return_value = (0, ["campusgpt:progress:101", "campusgpt:progress:102"])

        data1 = {
            "session_id": "sess-A",
            "request_id": "req-1",
            "stage": STAGE_RETRIEVING,
            "status": STATUS_IN_PROGRESS,
            "error_message": None,
        }
        data2 = {
            "session_id": "sess-B",
            "request_id": "req-2",
            "stage": STAGE_GENERATING,
            "status": STATUS_IN_PROGRESS,
            "error_message": None,
        }
        self.mock_redis.mget.return_value = [json.dumps(data1), json.dumps(data2)]

        res = get_session_progress("sess-A")
        self.mock_redis.scan.assert_called_once_with(0, match="campusgpt:progress:*", count=100)
        self.mock_redis.mget.assert_called_once_with("campusgpt:progress:101", "campusgpt:progress:102")

        self.assertIn("101", res)
        self.assertNotIn("102", res)
        self.assertEqual(res["101"]["request_id"], "req-1")
        self.assertEqual(res["101"]["stage"], STAGE_RETRIEVING)

    def test_clear_progress_redis(self):
        clear_progress(101)
        self.mock_redis.delete.assert_called_once_with("campusgpt:progress:101")

    def test_redis_error_fallback(self):
        # Force all Redis calls to raise exception to verify fallback to local in-memory
        self.mock_redis.set.side_effect = Exception("Redis connection lost")
        self.mock_redis.get.side_effect = Exception("Redis connection lost")
        self.mock_redis.delete.side_effect = Exception("Redis connection lost")
        self.mock_redis.scan.side_effect = Exception("Redis connection lost")

        # Set and get from fallback in-memory store
        update_progress(101, "sess-err", "req-err", STAGE_RERANKING, STATUS_IN_PROGRESS)
        status = get_progress(101)
        self.assertEqual(status["stage"], STAGE_RERANKING)

        # Get session progress from fallback in-memory store
        res = get_session_progress("sess-err")
        self.assertIn("101", res)

        # Clear from fallback in-memory store
        clear_progress(101)
        status = get_progress(101)
        self.assertEqual(status["stage"], STAGE_COMPLETE)


class TestPipelineProgressTracking(unittest.TestCase):

    def setUp(self):
        # Force get_redis to return None to avoid DNS calls
        self.get_redis_patcher = patch("app.services.progress_service.get_redis", return_value=None)
        self.mock_get_redis = self.get_redis_patcher.start()
        clear_progress(999)

    def tearDown(self):
        self.get_redis_patcher.stop()
        clear_progress(999)

    @patch("app.rag.pipeline.rewrite_query")
    @patch("app.rag.pipeline.hybrid_retrieve")
    @patch("app.rag.pipeline.llm_orchestrator")
    def test_pipeline_happy_path_progress_updates(
        self, mock_llm, mock_retrieve, mock_rewrite
    ):
        mock_rewrite.return_value = ["rewritten query"]
        mock_retrieve.return_value = [
            {"filename": "doc.txt", "category": "general", "text": "content", "source_type": "official"}
        ]
        mock_llm.generate_with_fallback.return_value = ("answer text", "gemini")

        # Track history of stages updated in the store
        stages_seen = []
        original_update = update_progress

        def spy_update_progress(
            conversation_id,
            session_id,
            request_id,
            stage,
            status,
            error_message=None,
        ):
            if conversation_id == 999:
                stages_seen.append((stage, status, error_message))
            original_update(
                conversation_id=conversation_id,
                session_id=session_id,
                request_id=request_id,
                stage=stage,
                status=status,
                error_message=error_message,
            )

        with patch("app.rag.pipeline.update_progress", side_effect=spy_update_progress):
            res = run_rag_pipeline(
                query="Hello?",
                conversation_id=999,
                session_id="session-user",
                request_id="req-123",
            )

        self.assertEqual(res["answer"], "answer text")
        self.assertEqual(
            stages_seen,
            [
                (STAGE_REWRITING, STATUS_IN_PROGRESS, None),
                (STAGE_RETRIEVING, STATUS_IN_PROGRESS, None),
                (STAGE_GENERATING, STATUS_IN_PROGRESS, None),
                (STAGE_COMPLETE, STATUS_COMPLETED, None),
            ],
        )

    @patch("app.rag.pipeline.rewrite_query")
    @patch("app.rag.pipeline.hybrid_retrieve")
    @patch("app.rag.pipeline.llm_orchestrator")
    def test_pipeline_llm_failure_emits_failed_progress(
        self, mock_llm, mock_retrieve, mock_rewrite
    ):
        mock_rewrite.return_value = ["rewritten query"]
        mock_retrieve.return_value = [
            {"filename": "doc.txt", "category": "general", "text": "content", "source_type": "official"}
        ]
        mock_llm.generate_with_fallback.side_effect = Exception("LLM connection timeout")

        with self.assertRaises(Exception):
            run_rag_pipeline(
                query="Hello?",
                conversation_id=999,
                session_id="session-user",
                request_id="req-123",
            )

        status = get_progress(999)
        self.assertEqual(status["stage"], STAGE_GENERATING)
        self.assertEqual(status["status"], STATUS_FAILED)
        self.assertEqual(status["error_message"], "Failed during generation")
