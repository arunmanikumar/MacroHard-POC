# graph.py — PART 1 of 6
# ─────────────────────────────────────────────────────────────
# IMPORTS AND LLM SETUP
#
# WHY ONE SHARED LLM:
#   In Phase 1 every agent created its own boto3 client.
#   Here one LLM object is created once and shared by all agents.
#   ChatBedrockConverse is LangChain's wrapper around your
#   Phase 1 bedrock_runtime.invoke_model() calls.
#   Same model, same region — just cleaner interface.
# ─────────────────────────────────────────────────────────────

import json
import logging
from datetime import datetime
from typing import Literal

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent

from state import TravelState, create_initial_state
from tools_lc import RESEARCH_TOOLS, POLICY_TOOLS, TOOL_DISPLAY

# ── Logging ───────────────────────────────────────────────────
# JSON format so CloudWatch Insights can query fields like:
#   filter agent = "ResearchAgent" | stats count() by event
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("graph")


def log_event(agent: str, event: str, data: dict = None):
    """Emit structured log entry for CloudWatch."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "agent": agent,
        "event": event,
        "data": data or {}
    }
    logger.info(json.dumps(entry))


# ── Shared LLM ────────────────────────────────────────────────
# Same model as Phase 1: Claude Haiku 4.5 on us-east-2
# temperature=0 → deterministic responses
# Critical for policy checks — you want consistent PASS/FAIL
# not creative variation each run
llm = ChatBedrockConverse(
    model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name="us-east-2",
    max_tokens=4096,
    temperature=0
)

print("Part 1 loaded — LLM ready")

# graph.py — PART 2 of 6
# ─────────────────────────────────────────────────────────────
# SYSTEM PROMPTS — Phase 2 with DynamoDB memory support
#
# KEY CHANGES FROM PHASE 1:
#   ORCHESTRATOR — removed "NO memory" warning, added memory
#                  instructions, updated end message
#   RESEARCH     — added conversation history instructions
#                  so Turn 2 refinements call the right tools
#   POLICY       — added context awareness for refinements
#   VALIDATION   — relaxed for refinement requests,
#                  still strict for fresh plans
# ─────────────────────────────────────────────────────────────

RESEARCH_SYSTEM_PROMPT = """You are a Travel Research Agent for Macrohard Corporation.
Your job is to gather travel data using your tools.

MEMORY AND CONTEXT:
You may receive conversation history from previous turns.
If the current request is a REFINEMENT of a previous trip
(examples: "change to economy hotels", "add one more day",
"switch to Air India only") — read the previous conversation
context carefully to extract the full trip details:
  - Origin city
  - Destination city
  - Travel dates
  - Number of passengers
  - Budget
Then apply the new constraint on top of those details.
Call all relevant tools using the FULL trip context —
never skip tools just because the current message is short.

If this is a FRESH request — treat it as a new trip entirely.

AIRPORT CODE CONVERSION — always convert before calling tools:
  LAX = Los Angeles    ORD = Chicago       JFK = New York City
  LHR = London         MAA = Chennai       BOM = Mumbai
  DEL = New Delhi      NRT = Tokyo         SFO = San Francisco
  DFW = Dallas         ATL = Atlanta       SEA = Seattle
  MIA = Miami          BOS = Boston        DXB = Dubai
  SIN = Singapore      CDG = Paris         FRA = Frankfurt

CURRENCY ASSUMPTIONS:
  rupees / rupee = INR — convert to USD first
  dollars / USD  = no conversion needed
  pounds = GBP   euros = EUR   yen = JPY
  If currency unclear assume USD

DATE ASSUMPTIONS:
  No year mentioned → use 2026
  Month already passed in 2026 → use 2027
  No specific date → use 15th of the month

TRAVELER ASSUMPTIONS:
  Not mentioned → assume 1 person
  couple → 2 travelers

TOOL CALLING ORDER — always follow this sequence:
  1. convert_currency  — ONLY if budget is not in USD
  2. get_country_info  — international trips only
  3. get_weather       — for destination city
  4. search_flights    — for the route
  5. find_hotels       — for destination city

RULES:
  Return all raw data without analysis
  No policy checks — that is the Policy Agent's job
  No recommendations — just gather facts
  Always call all relevant tools even for short refinement requests"""


POLICY_SYSTEM_PROMPT = """You are a Travel Policy Validation Agent for Macrohard Corporation.
Your job is to validate travel expenses against company policy.

MEMORY AND CONTEXT:
You receive research data from the Research Agent.
Pay special attention to any hotel or flight the user
specifically requested — these must be validated first
and flagged clearly if they fail.

YOUR JOB:
Check every flight option and every hotel option against policy.
Check the total trip cost against approval thresholds.
Return clear PASS or FAIL for each item with the policy cap amount.
Never gather data — only validate what you receive.

APPROVAL LEVEL REPORTING:
For total_trip checks always report the approval level clearly:
  Under $1,000    → "Direct Manager approval — 3 business days notice"
  $1,000-$3,999   → "Direct Manager approval — 5 business days notice"  
  $4,000-$9,999   → "Director approval required"
  $10,000-$24,999 → "⚠️ VP approval required — 10 business days notice"
  $25,000+        → "🚨 C-Level approval required"

Never just say PASS for a total trip without stating
the approval level and notice period required.
A trip is only truly compliant when the right approval
is obtained — make this clear in your output.

USER-REQUESTED ITEMS:
If the user specifically asked for a hotel or flight by name
and it FAILS policy — you must:
  1. Mark it as FAIL with the exact policy cap
  2. Add a note: "USER REQUESTED — NON COMPLIANT"
  3. Identify the cheapest compliant alternative from research data
  4. Mark that alternative as "RECOMMENDED COMPLIANT ALTERNATIVE"

CRITICAL RULES:
  For hotel checks — pass the PER NIGHT rate not the total stay
    Example: $150/night for 10 nights → pass amount_usd: 150
  For flight checks — pass the PER PERSON cost not the total
    Example: $650/person for 2 people → pass amount_usd: 650
  If policy check returns POLICY_CHECK_UNAVAILABLE
    note it as pending and continue with remaining checks
  Never hide a policy violation — always surface it clearly
  Never mark a FAIL item as acceptable or recommended

VALIDATION ORDER:
  1. User-requested hotel or flight FIRST if specified
  2. Each remaining flight option — per person cost
  3. Each remaining hotel option — per night rate
  4. Total trip cost — approval threshold check

OUTPUT FORMAT FOR EACH ITEM:
  Item: [name]
  Amount: $[X] per night/person
  Policy Cap: $[Y]
  Status: PASS ✅ or FAIL ❌
  Note: [USER REQUESTED — NON COMPLIANT if applicable]
  Alternative: [cheapest compliant option if failed]"""


ORCHESTRATOR_SYSTEM_PROMPT = """You are a Travel Planning Orchestrator for Macrohard Corporation.

YOUR ROLE:
You synthesize research data and policy validation results
into a complete, accurate travel plan for the traveler.

MEMORY AND CONTEXT:
You have access to conversation history from previous turns
via DynamoDB session memory. Use this context to understand
what the traveler has already planned and what they are
refining in the current request.

If the current request is a REFINEMENT:
  Read the conversation history to understand the base trip
  Apply the new constraint and produce a complete updated plan

If this is a FRESH request:
  Build the plan entirely from research and policy data provided

POLICY VIOLATION HANDLING — CRITICAL:
If the user requested a specific hotel or flight that FAILS policy:
  Show it clearly as NON-COMPLIANT with this exact format:

  ❌ [Hotel/Flight Name] — NON-COMPLIANT
     Requested by traveler
     Cost: $X per night/person
     Policy cap: $Y
     Status: EXCEEDS POLICY — CANNOT BE BOOKED
     Action required: Manager approval needed OR choose compliant option

  Then immediately show the compliant alternative:
  ⭐ RECOMMENDED COMPLIANT ALTERNATIVE
     [Hotel/Flight Name]
     Cost: $X per night/person
     Policy cap: $Y
     Status: PASS ✅

Never bury a policy violation in the middle of the plan.
Never show a non-compliant item as if it is bookable.
The compliance status must be the first thing shown for
any item the user specifically requested.

REQUIRED OUTPUT SECTIONS — always include all of these:

TRIP SUMMARY
  Travelers, dates, origin, destination, budget, trip type

⚠️ POLICY ALERTS (show this section ONLY if any item fails)
  List every non-compliant item the user requested
  Show the compliant alternative for each

FLIGHTS
  List every option with:
    Airline, flight number, duration, stops
    Price per person and total price
    Policy status: PASS ✅ or FAIL ❌
    If FAIL: show reason and policy cap
  Mark the cheapest compliant option as ⭐ RECOMMENDED

WEATHER
  Temperature range, conditions, packing advice

DESTINATION INFO (international trips only)
  Currency and exchange rate
  Language, timezone, emergency number
  Visa requirements

HOTEL OPTIONS
  List every option with:
    Hotel name, rating
    Price per night and total stay cost
    Policy status: PASS ✅ or FAIL ❌
    If FAIL: show reason and policy cap
    If user requested this hotel and it fails:
      Show ❌ USER REQUESTED — NON COMPLIANT prominently
  Mark the compliant option as ⭐ RECOMMENDED

DAILY MEAL ALLOWANCE
  Per day allowance from policy
  Total meal budget for the trip

BUDGET BREAKDOWN
  Flight cost (recommended option)
  Hotel cost (recommended option)
  Meal allowance total
  Estimated transport
  Total estimated cost
  Remaining budget

POLICY COMPLIANCE SUMMARY
  Table format:
  Item | Requested | Amount | Policy Cap | Status
  Include every item checked — PASS and FAIL both shown

ACTION ITEMS
  Always start with the approval action based on total trip cost:

  If total trip under $1,000:
    "1. ⚠️ Submit travel request to Direct Manager
        — minimum 3 business days before departure"

  If total trip $1,000 to $3,999:
    "1. ⚠️ Submit travel request to Direct Manager
        — minimum 5 business days before departure"

  If total trip $4,000 to $9,999:
    "1. 🚨 Director approval required before booking anything
        — submit full trip details to your Director"

  If total trip $10,000 to $24,999:
    "1. 🚨 VP approval required — submit 10 business days in advance
        — include full business justification document"

  If total trip $25,000 or more:
    "1. 🚨 C-Level executive approval required
        — escalate immediately through your VP"

  If any item failed policy add as item 2:
    "2. ⚠️ Policy exception required for [failed item]
        — contact travel desk before booking"

  Then add remaining items in this order:
    "3. Book approved flight — [recommended airline and flight number]"
    "4. Book approved hotel — [recommended hotel name]"
    "5. Purchase mandatory travel insurance before departure"
    "6. Apply for visa if required — allow 4-6 weeks processing"
    "7. Register trip with corporate security portal"
    "8. Arrange foreign currency or notify bank of travel dates"
    "9. Save emergency contacts:
        — Local emergency: [from country info]
        — Corporate travel desk: 1-800-MACROHARD"

End every plan with exactly this line:
Plan complete. To refine this trip describe your changes
and I will update the plan using your saved session context.

ABSOLUTE RULES:
  Never ask questions — always produce a complete plan
  Never hide or downplay a policy violation
  Never mark a non-compliant item as recommended
  Never hallucinate facts — use only research and policy data
  Every section must be filled — no empty sections"""


VALIDATION_SYSTEM_PROMPT = """You are a Quality Validation Agent for Macrohard Corporation.
Your job is to check travel plans before the traveler sees them.

CONTEXT AWARENESS:
The plan may be a REFINEMENT of a previous trip
(example: user asked to change to economy hotels only).
In this case the plan is valid even if some sections
reference previous context. Do not fail a plan just because
it is a refinement — check that it is complete and consistent.

VALIDATION CHECKLIST — check every item:
  1. All required sections present?
       TRIP SUMMARY, FLIGHTS, WEATHER, HOTEL OPTIONS,
       BUDGET BREAKDOWN, POLICY COMPLIANCE SUMMARY, ACTION ITEMS
  2. Every flight option has PASS or FAIL policy status?
  3. Every hotel option has PASS or FAIL policy status?
  4. At least one RECOMMENDED option for flights?
  5. At least one RECOMMENDED option for hotels?
  6. Budget numbers are internally consistent?
       Total = flight + hotel + meals + transport
  7. No placeholder values like $0, TBD, or missing city names?
  8. Action items section has at least 3 items?

RESPOND IN EXACTLY THIS FORMAT — no other text:

If plan passes all checks:
VALIDATION: PASS
NOTES: [summarize what you checked in 2-3 sentences]

If plan has fixable issues:
VALIDATION: FAIL
ISSUES: [list each specific problem on its own line]
NOTES: [tell the orchestrator exactly what to fix]

IMPORTANT:
  Be strict on structure — all 8 sections must be present
  Be fair on content — a refinement plan is valid
  One retry only — if orchestrator fixed the issues say PASS
  Never fail a plan twice for the same issue"""

print("Part 2 loaded — system prompts ready")

# graph.py — PART 3 of 6
# ─────────────────────────────────────────────────────────────
# NODE FUNCTIONS
#
# A node is just a Python function that:
#   - Takes the full TravelState as input
#   - Does its job (calls LLM, calls tools, etc.)
#   - Returns a DICT of only the fields it changed
#
# LangGraph merges that dict back into the state automatically.
# You never return the full state — only what changed.
#
# THINK OF IT LIKE:
#   State = a shared whiteboard
#   Each node reads the whiteboard, adds its results, passes it on
# ─────────────────────────────────────────────────────────────

# ── Create ReAct agents once at module load ────────────────────
# create_react_agent() replaces your Phase 1 while loops entirely.
# It handles: tool calling, result parsing, looping until done.
# One line here = ~40 lines of while loop in Phase 1.

research_agent = create_react_agent(
    model=llm,
    tools=RESEARCH_TOOLS,
    prompt=RESEARCH_SYSTEM_PROMPT  # injects system prompt
)

policy_agent = create_react_agent(
    model=llm,
    tools=POLICY_TOOLS,
    prompt=POLICY_SYSTEM_PROMPT
)


def orchestrator_node(state: TravelState) -> dict:
    """
    Runs FIRST (expand context) and THIRD (synthesize plan).

    First run  → no research_summary yet → prepare context
    Second run → research_summary exists → build final plan

    This is new in Phase 2. Phase 1 orchestrator only ran once
    at the end and had no access to conversation history.
    """
    log_event("OrchestratorAgent", "start", {
        "has_research": bool(state.get("research_summary")),
        "attempt": state.get("validation_attempts", 0)
    })

    if not state.get("research_summary"):
        # ── FIRST PASS: build context from history ─────────────
        # New in Phase 2 — Phase 1 never did this
        history_text = ""
        if state.get("conversation_history"):
            history_text = "\n\nPREVIOUS CONVERSATION:\n"
            for turn in state["conversation_history"]:
                role = turn["role"].upper()
                # Truncate long turns to save tokens
                content = turn["content"][:500]
                history_text += f"{role}: {content}\n"

        prompt = (
            f"New trip request: {state['user_input']}"
            f"{history_text}\n\n"
            f"Trip type: "
            f"{'international' if state['is_international'] else 'domestic'}.\n"
            f"Confirm what you will research."
        )
        messages = [
            SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]
        llm.invoke(messages)  # context prep — output not stored
        return {"steps_completed": state.get("steps_completed", 0) + 1}

    else:
        # ── SECOND PASS: synthesize final plan ─────────────────
        # Add validation notes if this is a retry
        validation_notes = ""
        if state.get("validation_notes") and not state.get("validation_passed"):
            validation_notes = (
                f"\n\nFIX THESE ISSUES FROM PREVIOUS ATTEMPT:\n"
                f"{state['validation_notes']}"
            )

        prompt = (
            f"Original request: {state['user_input']}\n\n"
            f"Research results:\n{state['research_summary']}\n\n"
            f"Policy results:\n{state['policy_summary']}"
            f"{validation_notes}\n\n"
            f"Create the complete travel plan."
        )
        messages = [
            SystemMessage(content=ORCHESTRATOR_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ]
        response = llm.invoke(messages)
        return {
            "final_plan": response.content,
            "steps_completed": state.get("steps_completed", 0) + 1
        }


def research_node(state: TravelState) -> dict:
    """
    Runs the Research Agent with 5 tools via ReAct loop.
    Replaces run_research_agent() and its 40-line while loop.
    """
    log_event("ResearchAgent", "start", {
        "input": state["user_input"][:100]
    })

    # Build context from conversation history
    # This is critical for Turn 2+ — "change to economy hotels"
    # needs to know the original trip details from Turn 1
    history_context = ""
    if state.get("conversation_history"):
        history_context = "\n\nPREVIOUS CONVERSATION CONTEXT:\n"
        for turn in state["conversation_history"]:
            role = turn["role"].upper()
            # Only include user turns for brevity — they have the trip details
            if role == "USER":
                history_context += f"PREVIOUS REQUEST: {turn['content']}\n"

    result = research_agent.invoke({
    "messages": [HumanMessage(content=(
        f"Gather all travel data for this request: {state['user_input']}\n"
        f"Trip type: "
        f"{'international' if state['is_international'] else 'domestic'}\n"
        f"{history_context}\n\n"
        f"IMPORTANT — USER REQUESTED ITEMS:\n"
        f"If the user mentioned a specific hotel name or airline "
        f"in their request, note it explicitly in your summary "
        f"so the Policy Agent knows to check it first.\n"
        f"Example: 'User specifically requested: Taj Coromandel hotel'\n"
        f"Always still return all available options from your tools "
        f"so the traveler has compliant alternatives to choose from."
    ))]
})

    # Last message in the list is the agent's final summary
    research_summary = result["messages"][-1].content

    # Build tool log from message history
    # ToolMessage = a tool was called — name tells us which one
    tool_log = []
    for msg in result["messages"]:
        if hasattr(msg, "name") and msg.name in TOOL_DISPLAY:
            tool_log.append({
                "agent": "ResearchAgent",
                "tool": msg.name,
                "output": msg.content
            })

    log_event("ResearchAgent", "complete", {
        "tools_called": len(tool_log)
    })

    return {
        "research_summary": research_summary,
        # Append to existing tool_log — don't overwrite
        "tool_log": state.get("tool_log", []) + tool_log,
        "steps_completed": state.get("steps_completed", 0) + 1
    }


def policy_node(state: TravelState) -> dict:
    """
    Runs Policy Agent with check_travel_policy via ReAct loop.
    Replaces run_policy_agent() and its 40-line while loop.
    """
    log_event("PolicyAgent", "start")

    result = policy_agent.invoke({
    "messages": [HumanMessage(content=(
        f"Validate all expenses against policy.\n"
        f"Research data: {state['research_summary']}\n"
        f"International: {state['is_international']}\n"
        f"Original request: {state['user_input']}"
    ))]
})

    policy_summary = result["messages"][-1].content

    tool_log = []
    for msg in result["messages"]:
        if hasattr(msg, "name") and msg.name in TOOL_DISPLAY:
            tool_log.append({
                "agent": "PolicyAgent",
                "tool": msg.name,
                "output": msg.content
            })

    log_event("PolicyAgent", "complete", {
        "tools_called": len(tool_log)
    })

    return {
        "policy_summary": policy_summary,
        "tool_log": state.get("tool_log", []) + tool_log,
        "steps_completed": state.get("steps_completed", 0) + 1
    }


def validation_node(state: TravelState) -> dict:
    """
    New in Phase 2 — checks output quality before user sees it.
    If fails on attempt 1 → routes back to orchestrator for retry.
    If fails on attempt 2 → passes through anyway (no infinite loop).
    """
    attempts = state.get("validation_attempts", 0) + 1
    log_event("ValidationAgent", "start", {"attempt": attempts})

    # Safety valve — never retry more than twice
    if attempts > 2:
        return {
            "validation_passed": True,
            "validation_notes": "Max attempts — passing through",
            "validation_attempts": attempts
        }

    messages = [
        SystemMessage(content=VALIDATION_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Validate this travel plan:\n\n{state.get('final_plan', '')}"
        ))
    ]
    response = llm.invoke(messages)
    passed = "VALIDATION: PASS" in response.content

    log_event("ValidationAgent", "complete", {
        "passed": passed,
        "attempt": attempts
    })

    return {
        "validation_passed": passed,
        "validation_notes": response.content,
        "validation_attempts": attempts,
        "steps_completed": state.get("steps_completed", 0) + 1
    }

print("Part 3 loaded — all 4 nodes ready")

# graph.py — PART 4 of 6
# ─────────────────────────────────────────────────────────────
# ROUTING FUNCTIONS
#
# A routing function reads state and returns a STRING.
# That string tells LangGraph which node to go to next.
# ─────────────────────────────────────────────────────────────

def route_after_orchestrator(state: TravelState) -> str:
    """
    After orchestrator runs — where do we go?
    No final_plan yet → research (first pass)
    final_plan exists → validation (second pass)
    """
    if state.get("final_plan"):
        return "validation_node"
    return "research_node"


def route_after_validation(
    state: TravelState
) -> Literal["orchestrator_node", "__end__"]:
    """
    After validation runs — where do we go?
    PASS → END
    FAIL attempt 1 → orchestrator retry
    FAIL attempt 2 → END anyway
    """
    if state.get("validation_passed"):
        return "__end__"
    if state.get("validation_attempts", 0) >= 2:
        return "__end__"
    return "orchestrator_node"


INTERNATIONAL_KEYWORDS = [
    "india", "chennai", "mumbai", "delhi", "bangalore",
    "japan", "tokyo", "uk", "united kingdom", "london",
    "france", "paris", "germany", "australia", "sydney",
    "singapore", "dubai", "uae", "canada", "toronto",
    "mexico", "china", "south korea", "thailand", "ireland",
    "netherlands", "spain", "italy", "switzerland",
    "maa", "bom", "del", "nrt", "lhr", "cdg", "sin", "dxb"
]

DOMESTIC_KEYWORDS = [
    "los angeles", "chicago", "new york", "san francisco",
    "dallas", "miami", "seattle", "boston", "atlanta",
    "denver", "houston", "phoenix", "las vegas", "orlando",
    "washington dc", "nashville", "austin", "san diego",
    "ord", "lax", "jfk", "sfo", "dfw", "atl", "mia",
    "sea", "bos", "den", "las", "mco", "mdw"
]


def detect_international(user_input: str) -> bool:
    """Detect if trip is international from user input text."""
    input_lower = user_input.lower()
    if any(kw in input_lower for kw in INTERNATIONAL_KEYWORDS):
        return True
    if any(kw in input_lower for kw in DOMESTIC_KEYWORDS):
        return False
    return True


print("Part 4 loaded — routing ready")

# graph.py — PART 5 of 6
# ─────────────────────────────────────────────────────────────
# GRAPH ASSEMBLY
#
# This is where all the pieces connect.
# Reading order:
#   1. Create graph with state type
#   2. Register nodes (the boxes in the flowchart)
#   3. Add edges (the arrows between boxes)
#   4. Compile (validate and lock the structure)
#
# FIXED EDGE:    A always goes to B
# CONDITIONAL:   A goes to B or C depending on state
# ─────────────────────────────────────────────────────────────

def build_graph():
    """
    Build and compile the LangGraph StateGraph.
    Called once at startup. Returns a compiled runnable.
    """

    # Step 1 — create graph container with our state type
    graph = StateGraph(TravelState)

    # Step 2 — register all nodes
    # String name = what edges reference
    graph.add_node("orchestrator_node", orchestrator_node)
    graph.add_node("research_node",     research_node)
    graph.add_node("policy_node",       policy_node)
    graph.add_node("validation_node",   validation_node)

    # Step 3 — wire the edges
    #
    # FLOW DIAGRAM:
    #
    #   START
    #     │
    #     ▼
    #   orchestrator ──── no final_plan ────► research
    #         ▲                                  │
    #         │                                  ▼
    #         │                               policy
    #         │                                  │
    #         └──── validation FAIL ◄──── orchestrator
    #                     │               (synthesizes)
    #                     │
    #                     └── PASS ──► END

    # Always start at orchestrator
    graph.add_edge(START, "orchestrator_node")

    # After orchestrator — conditional based on whether plan exists
    graph.add_conditional_edges(
        "orchestrator_node",
        route_after_orchestrator,   # the routing function from Part 4
        {
            "research_node":    "research_node",
            "validation_node":  "validation_node"
        }
    )

    # Research always goes to policy
    graph.add_edge("research_node", "policy_node")

    # Policy always goes back to orchestrator (for synthesis)
    graph.add_edge("policy_node", "orchestrator_node")

    # After validation — conditional based on pass/fail
    graph.add_conditional_edges(
        "validation_node",
        route_after_validation,     # the routing function from Part 4
        {
            "orchestrator_node": "orchestrator_node",
            "__end__":           END
        }
    )

    # Step 4 — compile (validates structure, returns runnable)
    compiled = graph.compile()
    log_event("Graph", "compiled")
    return compiled

print("Part 5 loaded — graph builder ready")

# graph.py — PART 6 of 6
# ─────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
#
# This is what app_v2.py calls for every user request.
# Replaces run_multi_agent() from Phase 1 agents.py.
#
# WHAT CHANGED VS PHASE 1:
#   Phase 1: run_multi_agent(user_input, verbose=True)
#   Phase 2: run_graph(user_input, session_id,
#                      conversation_history, previous_trip_context)
#
# The extra parameters support multi-turn conversation.
# app_v2.py loads conversation_history from DynamoDB before
# calling this, and saves it back after.
# ─────────────────────────────────────────────────────────────

def run_graph(
    user_input: str,
    session_id: str,
    conversation_history: list = None,
    previous_trip_context: dict = None
) -> dict:
    """
    Run the full multi-agent graph for one travel request.

    Args:
        user_input:            Raw text from the user
        session_id:            DynamoDB key for this session
        conversation_history:  Previous turns from DynamoDB
        previous_trip_context: Last trip data for refinement

    Returns dict with:
        status:            "success" or "error"
        result:            Final travel plan text
        tool_log:          All tool calls made
        steps:             Node count completed
        validation_passed: Whether validation approved the plan
    """
    is_international = detect_international(user_input)

    # Build clean starting state from state.py factory function
    initial_state = create_initial_state(
        user_input=user_input,
        session_id=session_id,
        is_international=is_international,
        conversation_history=conversation_history or [],
        previous_trip_context=previous_trip_context
    )

    log_event("Graph", "run_start", {
        "session_id": session_id,
        "is_international": is_international,
        "has_history": bool(conversation_history)
    })

    try:
        graph = build_graph()
        final_state = graph.invoke(initial_state)

        log_event("Graph", "run_complete", {
            "steps": final_state.get("steps_completed", 0),
            "tools": len(final_state.get("tool_log", [])),
            "validation_passed": final_state.get("validation_passed")
        })

        return {
            "status": "success",
            "result": final_state.get("final_plan", "No plan generated"),
            "tool_log": final_state.get("tool_log", []),
            "steps": final_state.get("steps_completed", 0),
            "validation_passed": final_state.get("validation_passed", False),
            "validation_notes": final_state.get("validation_notes", "")
        }

    except Exception as e:
        log_event("Graph", "run_error", {"error": str(e)})
        return {
            "status": "error",
            "result": "The travel agent encountered an error. Please try again.",
            "tool_log": [],
            "steps": 0,
            "error": str(e)
        }


# Quick smoke test — run this file directly to verify graph compiles
if __name__ == "__main__":
    print("\nBuilding graph...")
    g = build_graph()
    print("Graph compiled successfully")
    print("Nodes:", list(g.nodes))