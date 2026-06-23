import unittest
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
        # Clear out any state for clean tests
        clear_progress(101)
        clear_progress(102)

    def tearDown(self):
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


class TestPipelineProgressTracking(unittest.TestCase):

    def setUp(self):
        clear_progress(999)

    def tearDown(self):
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
        # Ensure correct sequential progress states were emitted
        self.assertEqual(
            stages_seen,
            [
                (STAGE_REWRITING, STATUS_IN_PROGRESS, None),
                (STAGE_RETRIEVING, STATUS_IN_PROGRESS, None),
                # Note: STAGE_RERANKING is simulated inside hybrid_retrieve callback,
                # but since hybrid_retrieve is mocked, we test it separately
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
