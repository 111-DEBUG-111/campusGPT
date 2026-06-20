"""
CampusGPT Response Cache Package.

Provides KB-version-aware, TTL-bounded caching for RAG pipeline responses.
Backend: Upstash Redis (HTTP-based, survives Render free-tier restarts).
"""
