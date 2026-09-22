# state.py
# ─────────────────────────────────────────────────────────────────────────────
# SHARED STATE — the single source of truth passed between all LangGraph nodes
#
# WHY THIS EXISTS:
#   In Phase 1, agents.py passed raw strings and dicts between functions.
#   Example: run_policy_agent(research_result["research_summary"], trip_context)
#   This meant each function had to guess the shape of its input.
#
#   In Phase 2, every node reads from and writes to this TypedDict.
#   LangGraph merges partial updates automatically — a node only needs to
#   return the fields it changed, not the entire state.
#
# HOW LANGGRAPH USES THIS:
#   graph.add_node("research", research_node)
#   When research_node returns {"research_summary": "..."}, LangGraph
#   merges that into the running state automatically.
#   The next node receives the full state with that field filled in.
# ─────────────────────────────────────────────────────────────────────────────

from typing import TypedDict, Optional, List, Dict, Any


class TravelState(TypedDict):
    # ── INPUT — set once at the start, never modified ────────────────────────

    user_input: str
    # The raw text the user typed. Example:
    # "Book a business trip for 2 people from ORD to Chennai
    #  on November 15 2026 for 5 days with a budget of $6000"

    is_international: bool
    # Detected from user_input by the orchestrator before routing.
    # True  → get_country_info will be called, insurance note added
    # False → skip country info, domestic policy caps used

    session_id: str
    # Unique ID for this conversation turn.
    # Format: "user_{username}_{timestamp}"
    # Used as the DynamoDB partition key for memory storage.

    # ── RESEARCH AGENT OUTPUT ─────────────────────────────────────────────────

    research_summary: str
    # Full text output from the Research Agent after all tools complete.
    # This is what the Policy Agent reads as input.
    # In Phase 1 this was research_result["research_summary"]

    tool_log: List[Dict[str, Any]]
    # Running list of every tool call made across all agents.
    # Each entry: {"agent": str, "step": int, "tool": str,
    #              "input": dict, "output": dict}
    # Shown in the Streamlit UI expander as the "Agent Reasoning" trace.
    # In Phase 1 this was assembled by combining tool_log from each agent.

    # ── POLICY AGENT OUTPUT ───────────────────────────────────────────────────

    policy_summary: str
    # Full text output from the Policy Agent after all checks complete.
    # This is what the Orchestrator reads as input.
    # In Phase 1 this was policy_result["policy_summary"]

    # ── VALIDATION AGENT OUTPUT ───────────────────────────────────────────────

    validation_passed: bool
    # True  → Orchestrator output passed quality check, show to user
    # False → Orchestrator output had issues, run orchestrator again
    # New in Phase 2 — did not exist in Phase 1

    validation_notes: str
    # Human-readable notes from the Validation Agent explaining
    # what it checked and any issues it found.
    # Shown in the UI expander for transparency.
    # New in Phase 2 — did not exist in Phase 1

    validation_attempts: int
    # How many times the Validation Agent has run this session.
    # Used to break out of retry loops — max 2 attempts.
    # Prevents infinite loop if orchestrator keeps producing bad output.
    # New in Phase 2 — did not exist in Phase 1

    # ── ORCHESTRATOR OUTPUT ───────────────────────────────────────────────────

    final_plan: str
    # The complete formatted travel plan shown to the user.
    # In Phase 1 this was result["result"]
    # Set by the Orchestrator, then validated by the Validation Agent.

    # ── MEMORY — DynamoDB conversation context ────────────────────────────────

    conversation_history: List[Dict[str, str]]
    # Previous turns in this session. Each entry:
    #   {"role": "user" | "assistant", "content": str}
    # Loaded from DynamoDB at the start of each turn.
    # Allows user to say "change the hotel to economy" without
    # re-entering the full trip details.
    # New in Phase 2 — did not exist in Phase 1

    previous_trip_context: Optional[Dict[str, Any]]
    # The structured trip data from the last successful plan.
    # If user refines the trip, this is merged with new input.
    # Example: user says "same trip but economy class only"
    # → previous_trip_context has origin, destination, dates
    # → new input just changes the constraint
    # New in Phase 2 — did not exist in Phase 1

    # ── METADATA ──────────────────────────────────────────────────────────────

    error: Optional[str]
    # If any node hits an unrecoverable error, it sets this field
    # and the graph routes to an error node instead of continuing.
    # The UI displays this as a user-friendly error message.

    steps_completed: int
    # Count of how many nodes have completed successfully.
    # Used for progress display in the Streamlit status widget.
    # In Phase 1 this was hardcoded as result["steps"] = 3


# ── DEFAULT STATE FACTORY ────────────────────────────────────────────────────
# Use this to create a clean starting state for each new request.
# Avoids KeyError when a node tries to read a field that hasn't been set yet.

def create_initial_state(
    user_input: str,
    session_id: str,
    is_international: bool = False,
    conversation_history: Optional[List] = None,
    previous_trip_context: Optional[Dict] = None
) -> TravelState:
    """
    Create a clean TravelState for a new agent run.

    Called by app_v2.py at the start of each user request.
    All Optional fields start as None or empty so nodes
    can check 'if state["field"]' safely.

    Args:
        user_input:            Raw text from the user
        session_id:            DynamoDB key for this session
        is_international:      Detected before graph starts
        conversation_history:  Loaded from DynamoDB (empty list if new session)
        previous_trip_context: Last trip data (None if first turn)
    """
    return TravelState(
        # Input
        user_input=user_input,
        is_international=is_international,
        session_id=session_id,

        # Research
        research_summary="",
        tool_log=[],

        # Policy
        policy_summary="",

        # Validation — starts at 0 attempts, not passed yet
        validation_passed=False,
        validation_notes="",
        validation_attempts=0,

        # Orchestrator
        final_plan="",

        # Memory — loaded from DynamoDB or empty for new sessions
        conversation_history=conversation_history or [],
        previous_trip_context=previous_trip_context,

        # Metadata
        error=None,
        steps_completed=0
    )