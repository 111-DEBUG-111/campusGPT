import threading
import json
import logging
from typing import Optional, Dict

from app.cache.client import get_redis

logger = logging.getLogger(__name__)

_lock = threading.Lock()
# In-memory dictionary mapping conversation_id (int) -> progress details dict
# Used as fallback when Upstash Redis is not configured or fails.
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
    Stores the state in Upstash Redis with a 5-minute TTL. Falls back to local memory.
    """
    data = {
        "session_id": session_id,
        "request_id": request_id,
        "stage": stage,
        "status": status,
        "error_message": error_message,
    }

    redis = get_redis()
    if redis is not None:
        key = f"campusgpt:progress:{conversation_id}"
        try:
            raw = json.dumps(data, ensure_ascii=False)
            # Store in Redis with a short TTL (5 minutes = 300 seconds)
            redis.set(key, raw, ex=300)
            return
        except Exception as exc:
            logger.error(f"Failed to update progress in Redis for conversation {conversation_id}: {exc}")

    # Fallback to in-memory store
    with _lock:
        _progress_store[conversation_id] = data


def get_progress(conversation_id: int) -> dict:
    """
    Retrieve the current progress of a specific conversation.
    Defaults to 'Complete' / 'completed' if no active progress is recorded.
    """
    redis = get_redis()
    if redis is not None:
        key = f"campusgpt:progress:{conversation_id}"
        try:
            raw = redis.get(key)
            if raw is not None:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(raw)
        except Exception as exc:
            logger.error(f"Failed to get progress from Redis for conversation {conversation_id}: {exc}")

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
    redis = get_redis()
    if redis is not None:
        try:
            pattern = "campusgpt:progress:*"
            cursor = 0
            keys = []
            while True:
                cursor, scan_keys = redis.scan(cursor, match=pattern, count=100)
                if scan_keys:
                    keys.extend(scan_keys)
                if cursor == 0:
                    break

            result = {}
            if keys:
                # Retrieve the values in bulk
                raw_values = redis.mget(*keys)
                for key, raw in zip(keys, raw_values):
                    if raw is not None:
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        val = json.loads(raw)
                        if val.get("session_id") == session_id:
                            if isinstance(key, bytes):
                                key_str = key.decode("utf-8")
                            else:
                                key_str = str(key)
                            conv_id = key_str.split(":")[-1]
                            result[conv_id] = {
                                "request_id": val["request_id"],
                                "stage": val["stage"],
                                "status": val["status"],
                                "error_message": val["error_message"],
                            }
            return result
        except Exception as exc:
            logger.error(f"Failed to get session progress from Redis for session {session_id}: {exc}")

    # Fallback to in-memory store
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
    redis = get_redis()
    if redis is not None:
        key = f"campusgpt:progress:{conversation_id}"
        try:
            redis.delete(key)
            return
        except Exception as exc:
            logger.error(f"Failed to clear progress from Redis for conversation {conversation_id}: {exc}")

    with _lock:
        _progress_store.pop(conversation_id, None)
