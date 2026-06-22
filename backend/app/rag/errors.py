"""
Custom exceptions for the RAG pipeline.
"""

class RagPipelineError(Exception):
    """
    Raised by run_rag_pipeline when a classified, user-safe error occurs.
    Carries a clean ``user_message`` and an HTTP ``status_code`` so the
    router can return a well-formed error response without leaking internals.
    """
    def __init__(self, user_message: str, status_code: int = 500):
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code
