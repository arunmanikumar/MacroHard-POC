# tools_lc.py
# ─────────────────────────────────────────────────────────────────────────────
# LANGCHAIN TOOL WRAPPERS
#
# WHAT THIS REPLACES:
#   Phase 1 had two separate files doing the same job:
#     tools.py      → 6 hand-written JSON dicts describing each tool
#     api_calls.py  → execute_tool() dispatcher that called the right function
#
#   The problem: schema and implementation were in two different files.
#   If you changed a parameter name in api_calls.py but forgot to update
#   tools.py, Claude would call a tool with a parameter that didn't exist.
#
# WHAT THIS FILE DOES:
#   The @tool decorator reads the function signature and docstring and
#   auto-generates the JSON schema Claude needs. One function = one source
#   of truth for both the schema and the implementation.
#
# HOW LANGCHAIN USES THIS:
#   Instead of:
#     execute_tool("get_weather", {"city": "Chennai", ...})
#   LangGraph's ToolNode calls:
#     get_weather.invoke({"city": "Chennai", ...})
#   The result is the same — your api_calls.py function runs — but
#   LangChain handles the dispatch, error catching, and result formatting.
#
# YOUR api_calls.py IS NOT MODIFIED:
#   Every function here ends with:
#     return api_calls.some_function(**params)
#   The real logic stays where it is. This file is just a typed front door.
# ─────────────────────────────────────────────────────────────────────────────

from langchain_core.tools import tool
import api_calls  # your Phase 1 implementations — completely unchanged


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 1 — WEATHER
# Research Agent uses this
# Real API: OpenWeatherMap
# ─────────────────────────────────────────────────────────────────────────────

@tool
def get_weather(city: str, country_code: str, travel_date: str) -> dict:
    """
    Get weather forecast for a destination city on specific travel dates.

    Returns temperature range, conditions, and packing advice.
    Always call this for every trip request.
    If this fails continue without weather data.

    Args:
        city:         Destination city name e.g. Chennai
        country_code: 2-letter ISO country code e.g. IN for India, US for USA
        travel_date:  Travel start date in YYYY-MM-DD format
    """
    # Delegate directly to your Phase 1 implementation.
    # No logic here — just pass the typed params through.
    return api_calls.get_weather(
        city=city,
        country_code=country_code,
        travel_date=travel_date
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 2 — FLIGHTS
# Research Agent uses this
# Mock data: Amadeus decommissioned July 2026
# ─────────────────────────────────────────────────────────────────────────────

@tool
def search_flights(
    origin_city: str,
    destination_city: str,
    departure_date: str,
    passengers: int,
    trip_type: str
) -> dict:
    """
    Search available flights between origin and destination airports.

    Returns flight options sorted by price.
    Always call this for every trip request.
    If this fails the entire trip plan cannot proceed.
    trip_type must be either 'business' or 'leisure'.

    Args:
        origin_city:      Departure city name e.g. Chicago
        destination_city: Arrival city name e.g. Chennai
        departure_date:   Departure date in YYYY-MM-DD format
        passengers:       Number of travelers
        trip_type:        Type of trip — 'business' or 'leisure'
    """
    return api_calls.search_flights(
        origin_city=origin_city,
        destination_city=destination_city,
        departure_date=departure_date,
        passengers=passengers,
        trip_type=trip_type
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 3 — COUNTRY INFO
# Research Agent uses this for international trips only
# Mock data: 8 countries hardcoded in api_calls.py
# ─────────────────────────────────────────────────────────────────────────────

@tool
def get_country_info(country_name: str, is_international: bool) -> dict:
    """
    Get destination country information including currency, language,
    timezone, and emergency contacts.

    Always call this for international trips.
    Skip for domestic US trips.
    If this fails the trip plan cannot proceed for international destinations.

    Args:
        country_name:     Full country name e.g. India, Japan, United Kingdom
        is_international: True if destination is outside the USA
    """
    return api_calls.get_country_info(
        country_name=country_name,
        is_international=is_international
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 4 — CURRENCY CONVERSION
# Research Agent uses this — only when currencies differ
# Real API: ExchangeRate-API
# ─────────────────────────────────────────────────────────────────────────────

@tool
def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str
) -> dict:
    """
    Convert an amount from one currency to another.

    ONLY call this tool when from_currency and to_currency are DIFFERENT.
    If budget is already in USD do NOT call this tool.
    If destination currency equals source currency do NOT call this tool.
    Only call when conversion is actually needed: INR to USD, GBP to USD, etc.

    Args:
        amount:        Amount to convert
        from_currency: Source currency code e.g. USD, INR, GBP
        to_currency:   Target currency code e.g. USD, INR, GBP
    """
    return api_calls.convert_currency(
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 5 — HOTELS
# Research Agent uses this
# Mock data: Geoapify had issues, using hardcoded data
# ─────────────────────────────────────────────────────────────────────────────

@tool
def find_hotels(city: str, check_in_date: str, nights: int) -> dict:
    """
    Find hotel options in the destination city.

    Returns 3 options at different price points.
    Always call this for every trip request.
    If this fails the trip plan cannot proceed.

    Args:
        city:          Destination city name e.g. Chennai
        check_in_date: Check-in date in YYYY-MM-DD format
        nights:        Number of nights
    """
    return api_calls.find_hotels(
        city=city,
        check_in_date=check_in_date,
        nights=nights
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL 6 — POLICY CHECK
# Policy Agent uses this — RAG via Bedrock Knowledge Base
# ─────────────────────────────────────────────────────────────────────────────

@tool
def check_travel_policy(
    item_type: str,
    amount_usd: float,
    city: str,
    is_international: bool,
    details: str = ""
) -> dict:
    """
    Check if a travel expense complies with company travel policy.

    ALWAYS call this before confirming any flight cost or hotel price.
    Call once for flights and once for each hotel option.
    Returns PASS or FAIL with the relevant policy section.
    item_type must be one of: flight, hotel, meal, transport, total_trip.

    IMPORTANT RULES:
    - For hotel checks pass the per night rate NOT the total stay cost
    - For flight checks pass the per person cost NOT the total for all passengers
    - If policy check returns POLICY_CHECK_UNAVAILABLE note it and continue

    Args:
        item_type:        Type of expense — flight, hotel, meal, transport, total_trip
        amount_usd:       Cost in USD (per night for hotels, per person for flights)
        city:             City where expense occurs
        is_international: True if this is an international trip
        details:          Additional context e.g. hotel name, airline, duration
    """
    return api_calls.check_travel_policy(
        item_type=item_type,
        amount_usd=amount_usd,
        city=city,
        is_international=is_international,
        details=details
    )


# ─────────────────────────────────────────────────────────────────────────────
# TOOL LISTS — which agent gets which tools
#
# WHY SEPARATE LISTS:
#   In Phase 1, agents.py filtered TOOLS by name:
#     RESEARCH_TOOLS = [t for t in TOOLS if t["name"] in [...]]
#   Same concept here — each agent only sees its own tools.
#   This prevents the Policy Agent from accidentally calling get_weather,
#   and prevents the Research Agent from calling check_travel_policy early.
#
# HOW GRAPH.PY USES THESE:
#   research_node = create_react_agent(llm, RESEARCH_TOOLS)
#   policy_node   = create_react_agent(llm, POLICY_TOOLS)
# ─────────────────────────────────────────────────────────────────────────────

# Research Agent tools — data gathering only, no policy
RESEARCH_TOOLS = [
    get_weather,        # OpenWeatherMap real API
    search_flights,     # Mock data
    get_country_info,   # Mock data — 8 countries
    convert_currency,   # ExchangeRate-API real API
    find_hotels         # Mock data
]

# Policy Agent tools — validation only, no data gathering
POLICY_TOOLS = [
    check_travel_policy  # Bedrock Knowledge Base RAG
]

# All tools combined — used for schema inspection and testing
ALL_TOOLS = RESEARCH_TOOLS + POLICY_TOOLS


# ─────────────────────────────────────────────────────────────────────────────
# TOOL NAME MAP — for the Streamlit UI tool trace display
#
# WHY THIS EXISTS:
#   app_v2.py shows each tool call with an icon and label.
#   This dict maps tool function names to display metadata.
#   In Phase 1 this was hardcoded if/elif in app.py.
#   Centralizing it here means one place to update when tools change.
# ─────────────────────────────────────────────────────────────────────────────

TOOL_DISPLAY = {
    "get_weather":        {"icon": "🌤️", "label": "Weather Lookup"},
    "search_flights":     {"icon": "✈️",  "label": "Flight Search"},
    "get_country_info":   {"icon": "🌍", "label": "Country Info"},
    "convert_currency":   {"icon": "💱", "label": "Currency Conversion"},
    "find_hotels":        {"icon": "🏨", "label": "Hotel Search"},
    "check_travel_policy":{"icon": "🔍", "label": "Policy Validation"},
}