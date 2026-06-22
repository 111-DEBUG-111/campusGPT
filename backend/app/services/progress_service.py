import threading
from typing import Optional, Dict

_lock = threading.Lock()
# In-memory dictionary mapping conversation_id (int) -> progress details dict
_progress_store: Dict[int, dict] = {}

# RAG Pipeline Stages
STAGE_REWRITING = "Rewriting Query"
STAGE_RETRIEVING = "Retrieving Documents"
STAGE_RERANKING = "Reranking Results"
STAGE_GENERATING = "Generating Response"
STAGE_COMPLETE = "Complete"

# Progress Statuses
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


def update_progress(
    conversation_id: int,
    session_id: str,
    request_id: Optional[str],
    stage: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """
    Set or update the active progress state of a conversation's RAG pipeline.
    """
    with _lock:
        _progress_store[conversation_id] = {
            "session_id": session_id,
            "request_id": request_id,
            "stage": stage,
            "status": status,
            "error_message": error_message,
        }


def get_progress(conversation_id: int) -> dict:
    """
    Retrieve the current progress of a specific conversation.
    Defaults to 'Complete' / 'completed' if no active progress is recorded.
    """
    with _lock:
        return _progress_store.get(
            conversation_id,
            {
                "request_id": None,
                "stage": STAGE_COMPLETE,
                "status": STATUS_COMPLETED,
                "error_message": None,
            },
        )


def get_session_progress(session_id: str) -> dict:
    """
    Retrieve progress dictionary for all conversations active in the given session.
    """
    with _lock:
        return {
            str(conv_id): {
                "request_id": val["request_id"],
                "stage": val["stage"],
                "status": val["status"],
                "error_message": val["error_message"],
            }
            for conv_id, val in _progress_store.items()
            if val["session_id"] == session_id
        }


def clear_progress(conversation_id: int) -> None:
    """
    Remove a conversation's progress from the store.
    """
    with _lock:
        _progress_store.pop(conversation_id, None)
