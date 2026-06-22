"""
Tests for outcome classification heuristics.
"""
from app.rag.outcome_classifier import heuristic_outcome, classify_query_outcome


FOREIGN_TRIPS_ANSWER = """I understand you're curious about foreign trips the university might organize.

Official Information
The university's Code of Conduct applies to students participating in "immersion programmes" and "excursions/study tours" that occur off-campus. This indicates that such programs are part of university-sponsored activities.

However, the provided documents don't specify if these are foreign trips, how often they occur (e.g., "every year"), or provide details about their nature.

If you're interested in specific international opportunities, I'd recommend checking with your program lead or the international relations office for the most current information!"""

FEES_ANSWER = """I understand you're looking for information on your first-year fees. Unfortunately, the university documents I have access to mention the responsibility for "timely payment of fees and dues" but they don't specify the exact amount for the first-year fees.
For detailed information on your first-year fees, I'd recommend checking the official university admissions portal or contacting the accounts/finance department directly."""

CAKE_ANSWER = """I'm here to help with university and campus-related questions only. I can't help with recipes like how to make a cake, but I'd be happy to answer questions about academics, hostel life, placements, or campus policies!"""

ATTENDANCE_ANSWER = """According to the Academic Handbook, students must maintain a minimum of 75% attendance in each course to be eligible for end-semester examinations."""


class TestHeuristicOutcome:
    def test_foreign_trips_is_knowledge_gap(self):
        assert heuristic_outcome(
            "tell me about the foreign trips that the university takes every year?",
            FOREIGN_TRIPS_ANSWER,
        ) == "knowledge_gap"

    def test_fees_is_knowledge_gap(self):
        assert heuristic_outcome(
            "what's the fees of my first year?",
            FEES_ANSWER,
        ) == "knowledge_gap"

    def test_cake_is_off_topic(self):
        assert heuristic_outcome(
            "how to make a cake?",
            CAKE_ANSWER,
        ) == "off_topic"

    def test_attendance_is_inconclusive(self):
        assert heuristic_outcome(
            "what is the attendance policy?",
            ATTENDANCE_ANSWER,
        ) is None


class TestClassifyQueryOutcomeHeuristicPath:
    def test_uses_heuristic_without_llm(self):
        outcome = classify_query_outcome(
            "tell me about foreign trips",
            FOREIGN_TRIPS_ANSWER,
            retrieved_chunks=3,
        )
        assert outcome == "knowledge_gap"
