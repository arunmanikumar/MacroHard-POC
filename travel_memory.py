# memory.py
# ─────────────────────────────────────────────────────────────────────────────
# DYNAMODB CONVERSATION MEMORY
#
# WHAT THIS FILE DOES:
#   Stores and retrieves conversation history per user session.
#   Every request loads previous turns so the agent has context.
#   Every response saves the new turn for next time.
#
# WHAT THIS REPLACES:
#   Nothing in Phase 1 — memory is completely new in Phase 2.
#   Phase 1 every request was stateless — user had to retype
#   full trip details every single time.
#
# HOW IT FITS THE GRAPH:
#   app_v2.py calls load_history() BEFORE calling run_graph()
#   app_v2.py calls save_turn() AFTER run_graph() returns
#   graph.py receives history as part of initial_state
#   orchestrator_node reads history to understand context
#
# DYNAMODB TABLE STRUCTURE:
#   Partition key: session_id (String)
#   Fields stored per session:
#     history      → list of conversation turns
#     last_trip    → structured data from last successful plan
#     updated_at   → timestamp of last update
#     turn_count   → how many turns this session has had
#
# FREE TIER MATH:
#   25 GB storage free forever
#   25 read capacity units free forever
#   25 write capacity units free forever
#   PAY_PER_REQUEST mode — only pay when you exceed free tier
#   A POC with 100 demo runs uses essentially $0
# ─────────────────────────────────────────────────────────────────────────────

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# ── Logging ───────────────────────────────────────────────────────────────────
logger = logging.getLogger("memory")
logging.basicConfig(level=logging.INFO)

# ── Constants ─────────────────────────────────────────────────────────────────

# Table name must match what you created in AWS
TABLE_NAME = "travel-agent-sessions"

# Region must match your Bedrock region
REGION = "us-east-2"

# How many conversation turns to keep in memory
# Older turns are trimmed to save tokens when passed to the LLM
# 10 turns = 5 user messages + 5 assistant responses
# Enough context for a full trip refinement conversation
MAX_HISTORY_TURNS = 10

# How many characters of each assistant turn to store
# Full plans can be 3000+ characters — we truncate for storage efficiency
# The user sees the full plan in the UI — this is just for context loading
MAX_ASSISTANT_CHARS = 1000

print("Part 1 loaded — constants ready")

# memory.py — PART 2
# ─────────────────────────────────────────────────────────────
# DYNAMODB CLIENT
#
# WHY A FUNCTION INSTEAD OF A GLOBAL:
#   A global client created at import time fails immediately
#   if AWS credentials are not configured.
#   A function creates the client only when first called.
#   This means the app can start and show the UI even if
#   DynamoDB is temporarily unreachable.
#
# IN .NET TERMS:
#   Like lazy initialization of a database connection.
#   You don't open the connection at app startup —
#   you open it when you first need it.
# ─────────────────────────────────────────────────────────────

# Module-level client — created once, reused for all calls
# None means not yet initialized
_dynamodb_client = None
_dynamodb_table = None


def get_table():
    """
    Get or create the DynamoDB table resource.
    Uses module-level caching — client created only once per process.
    This is the standard pattern for Lambda functions where you
    want to reuse connections across warm invocations.
    """
    global _dynamodb_client, _dynamodb_table

    # Return cached table if already initialized
    if _dynamodb_table is not None:
        return _dynamodb_table

    try:
        # boto3.resource gives a higher-level interface than boto3.client
        # resource lets you do table.get_item() instead of
        # client.get_item(TableName="...") — less boilerplate
        _dynamodb_client = boto3.resource(
            "dynamodb",
            region_name=REGION
        )
        _dynamodb_table = _dynamodb_client.Table(TABLE_NAME)

        logger.info(f"DynamoDB connected — table: {TABLE_NAME}")
        return _dynamodb_table

    except Exception as e:
        logger.error(f"DynamoDB connection failed: {e}")
        # Return None — callers must handle None gracefully
        # We never want memory failure to crash the travel agent
        return None

print("Part 2 loaded — DynamoDB client ready")

# memory.py — PART 3
# ─────────────────────────────────────────────────────────────
# LOAD CONVERSATION HISTORY
#
# CALLED BY: app_v2.py before every run_graph() call
#
# WHAT IT RETURNS:
#   history  → list of previous turns for the LLM to read
#   context  → structured trip data from the last successful plan
#
# FAILURE BEHAVIOR:
#   If DynamoDB is unreachable → returns empty history
#   The agent still runs — just without memory context
#   We never block the user because of a memory service failure
#   This is called "graceful degradation" in industry
# ─────────────────────────────────────────────────────────────

def load_history(session_id: str) -> dict:
    """
    Load conversation history for a session from DynamoDB.

    Args:
        session_id: Unique session identifier (e.g. "user_arun_1234")

    Returns:
        dict with keys:
          conversation_history  → list of {role, content} dicts
          previous_trip_context → dict of last trip data or None
          turn_count            → how many turns this session has had
    """
    # Default return — used when no history exists or on any error
    empty_result = {
        "conversation_history": [],
        "previous_trip_context": None,
        "turn_count": 0
    }

    table = get_table()
    if table is None:
        # DynamoDB unavailable — continue without memory
        logger.warning("DynamoDB unavailable — running without memory")
        return empty_result

    try:
        # get_item is a direct key lookup — O(1) operation
        # Much faster than a query or scan
        response = table.get_item(
            Key={"session_id": session_id}
        )

        # "Item" key only exists if the record was found
        # Missing key means this is a new session
        item = response.get("Item")

        if not item:
            logger.info(f"New session: {session_id}")
            return empty_result

        # Load conversation history
        # json.loads because we store history as a JSON string
        # DynamoDB stores everything as strings or numbers
        history_raw = item.get("history", "[]")
        history = json.loads(history_raw) if isinstance(
            history_raw, str
        ) else history_raw

        # Trim to last MAX_HISTORY_TURNS to control token usage
        # We keep the most recent turns — they are most relevant
        if len(history) > MAX_HISTORY_TURNS:
            history = history[-MAX_HISTORY_TURNS:]
            logger.info(
                f"Trimmed history to {MAX_HISTORY_TURNS} turns"
            )

        # Load last trip context if it exists
        context_raw = item.get("last_trip_context")
        last_trip = None
        if context_raw:
            try:
                last_trip = json.loads(context_raw) if isinstance(
                    context_raw, str
                ) else context_raw
            except json.JSONDecodeError:
                last_trip = None

        turn_count = int(item.get("turn_count", 0))

        logger.info(
            f"Loaded session {session_id} — "
            f"{len(history)} turns, "
            f"context: {bool(last_trip)}"
        )

        return {
            "conversation_history": history,
            "previous_trip_context": last_trip,
            "turn_count": turn_count
        }

    except ClientError as e:
        # AWS-specific error — log the error code for debugging
        error_code = e.response["Error"]["Code"]
        logger.error(f"DynamoDB ClientError {error_code}: {e}")
        return empty_result

    except Exception as e:
        logger.error(f"load_history failed: {e}")
        return empty_result

print("Part 3 loaded — load_history ready")

# memory.py — PART 4
# ─────────────────────────────────────────────────────────────
# SAVE CONVERSATION TURN
#
# CALLED BY: app_v2.py after every successful run_graph() call
#
# WHAT IT SAVES:
#   - The user's message (full text)
#   - The assistant's response (truncated for storage)
#   - Updated turn count
#   - Timestamp
#   - Last trip context (structured data for refinement)
#
# UPSERT PATTERN:
#   If session exists → update it (add new turns)
#   If session is new → create it
#   DynamoDB put_item handles both cases automatically
# ─────────────────────────────────────────────────────────────

def save_turn(
    session_id: str,
    user_message: str,
    assistant_message: str,
    trip_context: Optional[dict] = None
) -> bool:
    """
    Save a conversation turn to DynamoDB.

    Args:
        session_id:        Session identifier
        user_message:      What the user typed
        assistant_message: What the agent responded
        trip_context:      Structured trip data to save for refinement

    Returns:
        True if saved successfully, False if failed
        Caller should log but not crash on False
    """
    table = get_table()
    if table is None:
        logger.warning("DynamoDB unavailable — turn not saved")
        return False

    try:
        # Load existing history first so we can append to it
        existing = load_history(session_id)
        history = existing["conversation_history"]
        turn_count = existing["turn_count"]

        # Build the new turn entries
        # We store role/content pairs — same format LangChain uses
        # This means we can pass history directly to the LLM
        new_turns = [
            {
                "role": "user",
                # Store full user message — usually short
                "content": user_message
            },
            {
                "role": "assistant",
                # Truncate long assistant responses
                # Full plan shown in UI — this is just for context
                "content": assistant_message[:MAX_ASSISTANT_CHARS]
            }
        ]

        # Append new turns to existing history
        updated_history = history + new_turns

        # Trim if over limit — keep most recent turns
        if len(updated_history) > MAX_HISTORY_TURNS:
            updated_history = updated_history[-MAX_HISTORY_TURNS:]

        # Build the item to save
        # All complex types stored as JSON strings
        # DynamoDB natively supports strings, numbers, booleans
        item = {
            "session_id": session_id,
            "history": json.dumps(updated_history),
            "turn_count": turn_count + 1,
            # timezone.utc makes this timezone-aware
            # Fixes the utcnow() deprecation warning from graph.py
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save trip context if provided
        # This is the structured data the agent uses for refinement
        # Example: origin, destination, dates, budget, passengers
        if trip_context:
            item["last_trip_context"] = json.dumps(trip_context)

        # put_item creates or replaces the entire item
        # This is the upsert pattern — no need to check if exists
        table.put_item(Item=item)

        logger.info(
            f"Saved turn for {session_id} — "
            f"total turns: {turn_count + 1}"
        )
        return True

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        logger.error(f"DynamoDB save ClientError {error_code}: {e}")
        return False

    except Exception as e:
        logger.error(f"save_turn failed: {e}")
        return False

print("Part 4 loaded — save_turn ready")

# memory.py — PART 5
# ─────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
#
# clear_session  → used when user clicks "New Trip" in UI
# get_session_id → generates consistent session IDs
# test_connection → health check on startup
# ─────────────────────────────────────────────────────────────

def clear_session(session_id: str) -> bool:
    """
    Delete all history for a session.
    Called when user clicks 'Start New Trip' in app_v2.py.
    In industry this is called a 'session reset' or 'context clear'.
    """
    table = get_table()
    if table is None:
        return False

    try:
        table.delete_item(Key={"session_id": session_id})
        logger.info(f"Cleared session: {session_id}")
        return True
    except Exception as e:
        logger.error(f"clear_session failed: {e}")
        return False


def get_session_id(username: str) -> str:
    """
    Generate a session ID for a user.

    FORMAT: user_{username}_{date}
    Example: user_arun_20261115

    WHY DATE-BASED:
      A new day = a new session automatically.
      Users don't need to manually clear history.
      Yesterday's Tokyo trip doesn't confuse today's Chennai trip.
      For the demo, all runs today share one session —
      showing the multi-turn refinement capability.

    IN PRODUCTION:
      You might use a UUID per browser tab instead,
      or let users name their trips explicitly.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    # Sanitize username — remove spaces and special chars
    clean_username = "".join(
        c for c in username.lower() if c.isalnum()
    )
    return f"user_{clean_username}_{today}"


def test_connection() -> dict:
    """
    Test DynamoDB connectivity on app startup.
    Called by app_v2.py to show connection status in the UI.

    Returns dict with:
      connected  → True/False
      table      → table name
      message    → human readable status
    """
    table = get_table()
    if table is None:
        return {
            "connected": False,
            "table": TABLE_NAME,
            "message": "DynamoDB connection failed"
        }

    try:
        # load() fetches table metadata — lightweight operation
        # If this works, the table exists and we have access
        table.load()
        return {
            "connected": True,
            "table": TABLE_NAME,
            "message": f"Connected to {TABLE_NAME}"
        }
    except ClientError as e:
        return {
            "connected": False,
            "table": TABLE_NAME,
            "message": f"Error: {e.response['Error']['Code']}"
        }
    except Exception as e:
        return {
            "connected": False,
            "table": TABLE_NAME,
            "message": f"Error: {str(e)}"
        }


print("Part 5 loaded — utilities ready")


# ─────────────────────────────────────────────────────────────
# SMOKE TEST — run this file directly to verify everything works
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n── Memory Module Smoke Test ──")

    # Test 1 — connection
    print("\nTest 1: DynamoDB connection")
    result = test_connection()
    print(f"  Connected: {result['connected']}")
    print(f"  Message:   {result['message']}")

    if not result["connected"]:
        print("  ❌ Connection failed — check AWS credentials and region")
        exit(1)

    # Test 2 — save a turn
    print("\nTest 2: Save a turn")
    test_session = get_session_id("test_user")
    print(f"  Session ID: {test_session}")

    saved = save_turn(
        session_id=test_session,
        user_message="Book a trip from Chicago to Chennai",
        assistant_message="Here is your travel plan...",
        trip_context={"origin": "Chicago", "destination": "Chennai"}
    )
    print(f"  Saved: {saved}")

    # Test 3 — load it back
    print("\nTest 3: Load history")
    loaded = load_history(test_session)
    print(f"  Turns loaded: {len(loaded['conversation_history'])}")
    print(f"  Turn count:   {loaded['turn_count']}")
    print(f"  Has context:  {bool(loaded['previous_trip_context'])}")

    # Test 4 — clear session
    print("\nTest 4: Clear session")
    cleared = clear_session(test_session)
    print(f"  Cleared: {cleared}")

    # Test 5 — verify cleared
    print("\nTest 5: Verify cleared")
    after_clear = load_history(test_session)
    print(f"  Turns after clear: {len(after_clear['conversation_history'])}")

    print("\n── All tests passed ✅ ──")