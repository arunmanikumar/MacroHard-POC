# agents.py
import boto3
import json
from tools import TOOLS
from api_calls import execute_tool

bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name="us-east-2"
)

MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(
            f"agent_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler()
    ]
)

def get_logger(name):
    return logging.getLogger(name)

# ─────────────────────────────────────────
# RESEARCH AGENT
# ─────────────────────────────────────────

RESEARCH_TOOLS = [t for t in TOOLS if t["name"] in [
    "get_weather",
    "search_flights",
    "get_country_info",
    "convert_currency",
    "find_hotels"
]]

RESEARCH_SYSTEM_PROMPT = """You are a Travel Research Agent for Macrohard Corporation.
Your only job is to gather travel data using your tools.
Call all relevant tools for the trip request.
Return all gathered data in a structured format.
Do not validate policy — that is another agent's job.
Do not make recommendations — just gather facts.

SAFE ASSUMPTIONS — apply these silently before calling tools:

Airport codes — always convert to city names:
  LAX = Los Angeles
  ORD = Chicago
  JFK = New York City
  LHR = London
  MAA = Chennai
  BOM = Mumbai
  DEL = New Delhi
  NRT = Tokyo
  SFO = San Francisco
  DFW = Dallas
  ATL = Atlanta
  SEA = Seattle
  MIA = Miami
  BOS = Boston
  DXB = Dubai
  SIN = Singapore
  CDG = Paris
  FRA = Frankfurt

Currency assumptions:
  rupees / ruppee / rupee = INR — convert to USD first
  dollars / USD = no conversion needed
  pounds = GBP — convert to USD
  euros = EUR — convert to USD
  yen = JPY — convert to USD
  If currency unclear assume USD

Date assumptions:
  If no year mentioned use 2026
  If month already passed in 2026 use 2027
  If no specific date use 15th of the month
  Calculate return date from departure date plus number of days

Traveler assumptions:
  If not mentioned assume 1 person
  couple = 2 travelers

Always call tools in this exact order:
1. convert_currency ONLY if budget currency is not USD
   Skip entirely if budget is already in USD
2. get_country_info for international trips only
   Skip for domestic US trips
3. get_weather for destination city
4. search_flights for route
5. find_hotels for destination city

Return all raw data from tools without any analysis.
Do not validate policy.
Do not make recommendations.
Just gather and return the facts."""


def run_research_agent(user_input, trip_context):
    logger = get_logger("ResearchAgent")
    logger.info(f"Starting research for: {user_input[:100]}")

    messages = [{
        "role": "user",
        "content": (
            f"Gather all travel data for this request: {user_input}\n"
            f"Trip context: {json.dumps(trip_context)}"
        )
    }]

    tool_log = []
    step = 0

    while True:
        step += 1
        logger.info(f"Research Agent Step {step} — calling Bedrock")

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": RESEARCH_SYSTEM_PROMPT,
            "tools": RESEARCH_TOOLS,
            "messages": messages
        })

        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            body=body,
            contentType="application/json"
        )
        raw = json.loads(response["body"].read())
        stop_reason = raw.get("stop_reason")

        logger.info(f"Research Agent Step {step} stop_reason: {stop_reason}")

        if stop_reason == "end_turn":
            final = next(
                (b["text"] for b in raw.get("content", [])
                 if b.get("type") == "text"),
                ""
            )
            logger.info(
                f"Research Agent complete. "
                f"Steps: {step} Tools: {len(tool_log)}"
            )
            return {
                "research_summary": final,
                "tool_log": tool_log
            }

        if stop_reason == "tool_use":
            messages.append({
                "role": "assistant",
                "content": raw.get("content", [])
            })

            tool_results = []
            for block in raw.get("content", []):
                if block.get("type") == "tool_use":
                    tool_name = block["name"]
                    tool_input = block["input"]

                    logger.info(
                        f"Research Agent calling tool: {tool_name} "
                        f"with input: {json.dumps(tool_input)[:200]}"
                    )

                    result = execute_tool(tool_name, tool_input)

                    logger.info(
                        f"Tool {tool_name} returned: "
                        f"{json.dumps(result)[:200]}"
                    )

                    tool_log.append({
                        "agent": "ResearchAgent",
                        "step": step,
                        "tool": tool_name,
                        "input": tool_input,
                        "output": result
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": json.dumps(result)
                    })

            messages.append({
                "role": "user",
                "content": tool_results
            })

        if step > 15:
            logger.warning("Research Agent hit step limit")
            return {
                "research_summary": "Research incomplete",
                "tool_log": tool_log
            }


# ─────────────────────────────────────────
# POLICY AGENT
# ─────────────────────────────────────────

POLICY_TOOLS = [t for t in TOOLS if t["name"] == "check_travel_policy"]

POLICY_SYSTEM_PROMPT = """You are a Travel Policy Validation Agent.
Your only job is to validate travel expenses against company policy.
You receive research data from the Research Agent.
Check every flight option and every hotel option against policy.
Check the total trip cost against approval thresholds.
Return clear PASS or FAIL for each item with the policy cap amount.
Never gather data — only validate what you receive.

IMPORTANT RULES:
- For hotel checks always pass the per night rate NOT the total stay cost
  Example: hotel is $150 per night for 10 nights
  Pass amount_usd: 150 not amount_usd: 1500
- For flight checks always pass the per person cost NOT the total
  Example: flight is $650 per person for 2 passengers
  Pass amount_usd: 650 not amount_usd: 1300
- If policy check returns POLICY_CHECK_UNAVAILABLE
  note it as pending and continue with remaining checks

Always check in this order:
1. Each flight option per person cost
2. Each hotel option per night rate
3. Total trip cost for approval threshold"""


def run_policy_agent(research_data, trip_context):
    logger = get_logger("PolicyAgent")
    logger.info("Starting policy validation")

    messages = [{
        "role": "user",
        "content": (
            f"Validate all expenses against company travel policy.\n"
            f"Research data: {research_data}\n"
            f"Trip context: {json.dumps(trip_context)}"
        )
    }]

    tool_log = []
    step = 0

    while True:
        step += 1
        logger.info(f"Policy Agent Step {step} — calling Bedrock")

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": POLICY_SYSTEM_PROMPT,
            "tools": POLICY_TOOLS,
            "messages": messages
        })

        response = bedrock_runtime.invoke_model(
            modelId=MODEL_ID,
            body=body,
            contentType="application/json"
        )
        raw = json.loads(response["body"].read())
        stop_reason = raw.get("stop_reason")

        logger.info(f"Policy Agent Step {step} stop_reason: {stop_reason}")

        if stop_reason == "end_turn":
            final = next(
                (b["text"] for b in raw.get("content", [])
                 if b.get("type") == "text"),
                ""
            )
            logger.info(
                f"Policy Agent complete. "
                f"Steps: {step} Tools: {len(tool_log)}"
            )
            return {
                "policy_summary": final,
                "tool_log": tool_log
            }

        if stop_reason == "tool_use":
            messages.append({
                "role": "assistant",
                "content": raw.get("content", [])
            })

            tool_results = []
            for block in raw.get("content", []):
                if block.get("type") == "tool_use":
                    tool_name = block["name"]
                    tool_input = block["input"]

                    logger.info(
                        f"Policy Agent calling tool: {tool_name} "
                        f"with input: {json.dumps(tool_input)[:200]}"
                    )

                    result = execute_tool(tool_name, tool_input)

                    logger.info(
                        f"Tool {tool_name} returned: "
                        f"{json.dumps(result)[:200]}"
                    )

                    tool_log.append({
                        "agent": "PolicyAgent",
                        "step": step,
                        "tool": tool_name,
                        "input": tool_input,
                        "output": result
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": json.dumps(result)
                    })

            messages.append({
                "role": "user",
                "content": tool_results
            })

        if step > 15:
            logger.warning("Policy Agent hit step limit")
            return {
                "policy_summary": "Policy validation incomplete",
                "tool_log": tool_log
            }


# ─────────────────────────────────────────
# ORCHESTRATOR AGENT
# ─────────────────────────────────────────

ORCHESTRATOR_SYSTEM_PROMPT = """You are a Travel Planning Orchestrator Agent for Macrohard Corporation.

YOUR JOB:
You receive research data and policy validation results
from two specialist agents.
Your job is to synthesize everything into a clear travel plan.

OUTPUT FORMAT:
Always include all these sections:

TRIP SUMMARY
  Travelers, dates, origin, destination, budget

POLICY COMPLIANCE SUMMARY
  Table: Item | Amount | Cap | Status

FLIGHTS
  Each option with policy status PASS or FAIL
  Mark cheapest compliant option as RECOMMENDED

HOTEL OPTIONS
  Each with nightly rate and policy status
  Mark compliant option as RECOMMENDED

BUDGET BREAKDOWN
  All costs, total, remaining budget

WEATHER
  Temperature, conditions, packing advice

DESTINATION INFO (international only)
  Currency, language, timezone, emergency number, visa

DAILY MEAL ALLOWANCE
  From policy validation results

ACTION ITEMS
  Everything traveler must do before booking

End with exactly:
Plan complete. To modify this trip please submit
a new request with your updated requirements.

ABSOLUTE RULES:
- Never ask questions
- Never offer follow-up options
- Use only data from research and policy agents
- Never hallucinate any facts"""


def run_orchestrator(user_input, research_result, policy_result):
    logger = get_logger("OrchestratorAgent")
    logger.info("Starting orchestrator synthesis")

    messages = [{
        "role": "user",
        "content": (
            f"Original request: {user_input}\n\n"
            f"Research Agent results:\n{research_result['research_summary']}\n\n"
            f"Policy Agent results:\n{policy_result['policy_summary']}\n\n"
            f"Create the complete travel plan using this data."
        )
    }]

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "system": ORCHESTRATOR_SYSTEM_PROMPT,
        "messages": messages
    })

    response = bedrock_runtime.invoke_model(
        modelId=MODEL_ID,
        body=body,
        contentType="application/json"
    )
    raw = json.loads(response["body"].read())
    final = next(
        (b["text"] for b in raw.get("content", [])
         if b.get("type") == "text"),
        "No response generated"
    )

    logger.info("Orchestrator complete")
    return final


# ─────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────

def run_multi_agent(user_input, verbose=True):
    logger = get_logger("MultiAgent")
    logger.info(f"{'='*60}")
    logger.info(f"NEW REQUEST: {user_input[:100]}")
    logger.info(f"{'='*60}")

    # Known international destinations
    international_destinations = [
        "india", "chennai", "mumbai", "delhi", "bangalore",
        "hyderabad", "kolkata", "pune",
        "japan", "tokyo", "osaka",
        "uk", "united kingdom", "london", "england",
        "france", "paris",
        "germany", "frankfurt", "berlin",
        "australia", "sydney", "melbourne",
        "singapore",
        "dubai", "uae", "united arab emirates",
        "canada", "toronto", "vancouver",
        "mexico", "mexico city",
        "china", "beijing", "shanghai",
        "south korea", "seoul",
        "thailand", "bangkok",
        "brazil", "sao paulo",
        "ireland", "dublin",
        "netherlands", "amsterdam",
        "spain", "madrid", "barcelona",
        "italy", "rome", "milan",
        "switzerland", "zurich",
        "sweden", "stockholm",
        "norway", "oslo",
        "denmark", "copenhagen",
        "new zealand", "auckland",
        "south africa", "johannesburg",
        "kenya", "nairobi",
        "indonesia", "jakarta",
        "malaysia", "kuala lumpur",
        "philippines", "manila",
        # Airport codes for international cities
        "maa", "bom", "del", "blr",
        "nrt", "hnd", "lhr", "cdg",
        "fra", "sin", "dxb", "yyz",
        "mex", "pek", "pvg", "icn",
        "bkk", "gru", "dub", "ams",
        "mad", "fco", "zrh", "hkg"
    ]

    # Known domestic US destinations
    domestic_destinations = [
        # City names
        "los angeles", "chicago", "new york",
        "new york city", "nyc", "san francisco",
        "dallas", "miami", "seattle", "boston",
        "atlanta", "denver", "houston", "phoenix",
        "portland", "las vegas", "orlando",
        "washington dc", "washington d.c",
        "philadelphia", "minneapolis",
        "detroit", "nashville", "austin",
        "san diego", "sacramento",
        "illinois", "california", "texas",
        "florida", "nevada", "oregon",
        "washington", "colorado", "arizona",
        "new york state", "hawaii", "honolulu",
        # US airport codes
        "ord", "lax", "jfk", "ewr", "lga",
        "sfo", "dfw", "atl", "mia", "sea",
        "bos", "den", "pdx", "las", "mco",
        "iad", "dca", "bwi", "hou", "mdw",
        "phx", "msp", "dtw", "bna", "aus",
        "san", "smf", "hnl", "phl"
    ]

    input_lower = user_input.lower()

    # Step 1: Check if any international destination is mentioned
    is_international = any(
        dest in input_lower
        for dest in international_destinations
    )

    # Step 2: If no international destination found
    # check if it is clearly domestic
    if not is_international:
        has_domestic = any(
            dest in input_lower
            for dest in domestic_destinations
        )
        # If no domestic destination found either
        # default to international to be safe
        is_international = not has_domestic

    trip_context = {
        "raw_input": user_input,
        "is_international": is_international
    }

    logger.info(
        f"Trip detected as: "
        f"{'international' if is_international else 'domestic'}"
    )

    # PHASE 1 — Research Agent gathers all data
    logger.info("PHASE 1: Research Agent starting")
    research_result = run_research_agent(user_input, trip_context)
    logger.info(
        f"PHASE 1 complete. "
        f"Tools called: {len(research_result['tool_log'])}"
    )

    # PHASE 2 — Policy Agent validates all decisions
    logger.info("PHASE 2: Policy Agent starting")
    policy_result = run_policy_agent(
        research_result["research_summary"],
        trip_context
    )
    logger.info(
        f"PHASE 2 complete. "
        f"Tools called: {len(policy_result['tool_log'])}"
    )

    # PHASE 3 — Orchestrator synthesizes final plan
    logger.info("PHASE 3: Orchestrator synthesizing")
    final_plan = run_orchestrator(
        user_input,
        research_result,
        policy_result
    )
    logger.info("PHASE 3 complete")

    # Combine tool logs from all agents
    all_tool_logs = (
        research_result["tool_log"] +
        policy_result["tool_log"]
    )

    logger.info(
        f"COMPLETE. Total tools called: {len(all_tool_logs)}"
    )

    return {
        "status": "success",
        "result": final_plan,
        "tool_log": all_tool_logs,
        "steps": 3
    }


if __name__ == "__main__":
    result = run_multi_agent(
        "Book a business trip for 2 people from ORD to Chennai "
        "on November 15 2026 for 5 days with a budget of $6000"
    )
    print(result["result"])