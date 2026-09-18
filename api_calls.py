# api_calls.py
import os
import json
import requests
import boto3
from dotenv import load_dotenv

load_dotenv()
# Bedrock agent runtime for RAG
bedrock_agent_runtime = boto3.client(
    service_name="bedrock-agent-runtime",
    region_name="us-east-2"
)

# Your Knowledge Base ID
KNOWLEDGE_BASE_ID = os.getenv("KNOWLEDGE_BASE_ID")  # paste your KB ID here

# Model to use for RAG responses
RAG_MODEL_ARN = "arn:aws:bedrock:us-east-2:126606499815:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0"

# ─────────────────────────────────────────
# HEALTH CHECK - runs on startup
# ─────────────────────────────────────────

def check_required_keys():
    required = [
        "OPENWEATHER_API_KEY",
        "EXCHANGE_API_KEY"
    ]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise EnvironmentError(
            f"Missing required API keys: {', '.join(missing)}"
        )
    print("Health check passed - all required keys present")

# ─────────────────────────────────────────
# MOCK DATA
# ─────────────────────────────────────────

COUNTRY_DATA = {
    "india": {
        "currency": "INR",
        "currency_name": "Indian Rupee",
        "language": "Hindi, English",
        "timezone": "IST (GMT+5:30)",
        "emergency": "112",
        "capital": "New Delhi",
        "visa_required": True
    },
    "japan": {
        "currency": "JPY",
        "currency_name": "Japanese Yen",
        "language": "Japanese",
        "timezone": "JST (GMT+9)",
        "emergency": "110 (police) 119 (ambulance)",
        "capital": "Tokyo",
        "visa_required": False
    },
    "united kingdom": {
        "currency": "GBP",
        "currency_name": "British Pound",
        "language": "English",
        "timezone": "GMT/BST",
        "emergency": "999",
        "capital": "London",
        "visa_required": False
    },
    "mexico": {
        "currency": "MXN",
        "currency_name": "Mexican Peso",
        "language": "Spanish",
        "timezone": "CST (GMT-6)",
        "emergency": "911",
        "capital": "Mexico City",
        "visa_required": False
    },
    "united states": {
        "currency": "USD",
        "currency_name": "US Dollar",
        "language": "English",
        "timezone": "Multiple zones",
        "emergency": "911",
        "capital": "Washington DC",
        "visa_required": False
    },
    "france": {
        "currency": "EUR",
        "currency_name": "Euro",
        "language": "French",
        "timezone": "CET (GMT+1)",
        "emergency": "112",
        "capital": "Paris",
        "visa_required": False
    },
    "australia": {
        "currency": "AUD",
        "currency_name": "Australian Dollar",
        "language": "English",
        "timezone": "AEST (GMT+10)",
        "emergency": "000",
        "capital": "Canberra",
        "visa_required": True
    },
    "canada": {
        "currency": "CAD",
        "currency_name": "Canadian Dollar",
        "language": "English, French",
        "timezone": "Multiple zones",
        "emergency": "911",
        "capital": "Ottawa",
        "visa_required": False
    }
}

HOTEL_DATA = {
    "chennai": [
        {"name": "Courtyard by Marriott Chennai",
         "price_per_night_usd": 150, "rating": 4.2},
        {"name": "Holiday Inn Chennai",
         "price_per_night_usd": 210, "rating": 4.0},
        {"name": "Taj Coromandel",
         "price_per_night_usd": 195, "rating": 4.5}
    ],
    "los angeles": [
        {"name": "Courtyard by Marriott LA Downtown",
         "price_per_night_usd": 165, "rating": 4.1},
        {"name": "Hilton Checkers Los Angeles",
         "price_per_night_usd": 210, "rating": 4.3},
        {"name": "The Westin Bonaventure",
         "price_per_night_usd": 195, "rating": 4.2}
    ],
    "tokyo": [
        {"name": "Shinjuku Granbell Hotel",
         "price_per_night_usd": 185, "rating": 4.3},
        {"name": "Park Hyatt Tokyo",
         "price_per_night_usd": 450, "rating": 4.8},
        {"name": "Keio Plaza Hotel",
         "price_per_night_usd": 200, "rating": 4.2}
    ],
    "london": [
        {"name": "Premier Inn London City",
         "price_per_night_usd": 180, "rating": 4.0},
        {"name": "Hilton London Bankside",
         "price_per_night_usd": 245, "rating": 4.4},
        {"name": "citizenM London Shoreditch",
         "price_per_night_usd": 165, "rating": 4.3}
    ],
    "new york": [
        {"name": "Holiday Inn Manhattan",
         "price_per_night_usd": 220, "rating": 4.0},
        {"name": "Courtyard New York Manhattan",
         "price_per_night_usd": 265, "rating": 4.2},
        {"name": "Hampton Inn Manhattan",
         "price_per_night_usd": 195, "rating": 4.1}
    ],
    "mexico city": [
        {"name": "Camino Real Polanco",
         "price_per_night_usd": 145, "rating": 4.3},
        {"name": "Hilton Mexico City Reforma",
         "price_per_night_usd": 165, "rating": 4.2},
        {"name": "JW Marriott Mexico City",
         "price_per_night_usd": 195, "rating": 4.5}
    ]
}

FLIGHT_DATA = {
    ("chicago", "chennai"): [
        {"airline": "United Airlines", "flight_number": "UA 8875",
         "stops": 1, "duration_hours": 20,
         "price_per_person_usd": 800, "class": "Economy"},
        {"airline": "Air India", "flight_number": "AI 127",
         "stops": 0, "duration_hours": 22,
         "price_per_person_usd": 650, "class": "Economy"}
    ],
    ("chicago", "los angeles"): [
        {"airline": "United Airlines", "flight_number": "UA 123",
         "stops": 0, "duration_hours": 4,
         "price_per_person_usd": 250, "class": "Economy"},
        {"airline": "American Airlines", "flight_number": "AA 456",
         "stops": 0, "duration_hours": 4,
         "price_per_person_usd": 200, "class": "Economy"}
    ],
    ("chicago", "new york"): [
        {"airline": "Delta Airlines", "flight_number": "DL 789",
         "stops": 0, "duration_hours": 2,
         "price_per_person_usd": 180, "class": "Economy"},
        {"airline": "United Airlines", "flight_number": "UA 321",
         "stops": 0, "duration_hours": 2,
         "price_per_person_usd": 150, "class": "Economy"}
    ],
    ("new york", "london"): [
        {"airline": "British Airways", "flight_number": "BA 178",
         "stops": 0, "duration_hours": 7,
         "price_per_person_usd": 900, "class": "Economy"},
        {"airline": "Virgin Atlantic", "flight_number": "VS 003",
         "stops": 0, "duration_hours": 7,
         "price_per_person_usd": 850, "class": "Economy"}
    ],
    ("chicago", "mexico city"): [
        {"airline": "Aeromexico", "flight_number": "AM 702",
         "stops": 0, "duration_hours": 4,
         "price_per_person_usd": 350, "class": "Economy"},
        {"airline": "United Airlines", "flight_number": "UA 890",
         "stops": 0, "duration_hours": 4,
         "price_per_person_usd": 380, "class": "Economy"}
    ],
    ("india", "united kingdom"): [
        {"airline": "British Airways", "flight_number": "BA 118",
         "stops": 0, "duration_hours": 9,
         "price_per_person_usd": 750, "class": "Economy"},
        {"airline": "Air India", "flight_number": "AI 111",
         "stops": 0, "duration_hours": 9,
         "price_per_person_usd": 680, "class": "Economy"}
    ]
}

# ─────────────────────────────────────────
# FUNCTION 1 - WEATHER (Real API)
# ─────────────────────────────────────────

def get_weather(city, country_code, travel_date):
    try:
        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {
            "q": f"{city},{country_code}",
            "appid": os.getenv("OPENWEATHER_API_KEY"),
            "units": "metric",
            "cnt": 8
        }
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 404:
            return {
                "status": "city_not_found",
                "message": f"City '{city}' not found. Please check the spelling.",
                "data": None
            }

        if response.status_code != 200:
            return {
                "status": "unavailable",
                "message": "Weather data temporarily unavailable.",
                "packing_advice": "Check local weather before departure.",
                "data": None
            }

        data = response.json()
        temps = [item["main"]["temp"] for item in data["list"][:8]]
        min_temp = round(min(temps), 1)
        max_temp = round(max(temps), 1)
        conditions = data["list"][0]["weather"][0]["description"]

        if min_temp < 10:
            packing = "Heavy jacket, warm layers, gloves recommended"
        elif min_temp < 18:
            packing = "Light jacket and layers recommended"
        elif min_temp < 25:
            packing = "Light clothing, business casuals comfortable"
        else:
            packing = "Light clothing, stay hydrated, sunscreen advised"

        return {
            "status": "success",
            "city": city,
            "travel_date": travel_date,
            "min_temp_celsius": min_temp,
            "max_temp_celsius": max_temp,
            "conditions": conditions.title(),
            "packing_advice": packing
        }

    except requests.exceptions.Timeout:
        return {
            "status": "unavailable",
            "message": "Weather service timed out.",
            "packing_advice": "Check local weather before departure.",
            "data": None
        }
    except Exception as e:
        return {
            "status": "unavailable",
            "message": "Weather data temporarily unavailable.",
            "packing_advice": "Check local weather before departure.",
            "data": None
        }

# ─────────────────────────────────────────
# FUNCTION 2 - FLIGHTS (Mock Data)
# ─────────────────────────────────────────

def search_flights(origin_city, destination_city,
                   departure_date, passengers, trip_type):
    try:
        origin_key = origin_city.lower().strip()
        dest_key = destination_city.lower().strip()

        # normalize common city variations
        city_map = {
            "illinois": "chicago",
            "chicago, il": "chicago",
            "new york city": "new york",
            "nyc": "new york",
            "la": "los angeles",
            "uk": "united kingdom",
            "usa": "united states"
        }

        origin_key = city_map.get(origin_key, origin_key)
        dest_key = city_map.get(dest_key, dest_key)

        flights = FLIGHT_DATA.get(
            (origin_key, dest_key),
            FLIGHT_DATA.get((dest_key, origin_key), None)
        )

        if not flights:
            # generic fallback if route not in mock data
            flights = [
                {
                    "airline": "United Airlines",
                    "flight_number": "UA 0000",
                    "stops": 1,
                    "duration_hours": 8,
                    "price_per_person_usd": 500,
                    "class": "Economy"
                }
            ]

        result = []
        for f in flights:
            result.append({
                **f,
                "passengers": passengers,
                "total_usd": f["price_per_person_usd"] * passengers,
                "departure_date": departure_date,
                "trip_type": trip_type,
                "source": "mock_data"
            })

        return {
            "status": "success",
            "origin": origin_city,
            "destination": destination_city,
            "flights": result,
            "cheapest_usd": min(f["total_usd"] for f in result)
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": "Flight search failed. Please try again.",
            "data": None
        }

# ─────────────────────────────────────────
# FUNCTION 3 - COUNTRY INFO (Mock Data)
# ─────────────────────────────────────────

def get_country_info(country_name, is_international):
    try:
        if not is_international:
            return {
                "status": "success",
                "note": "Domestic trip - no country info required",
                "currency": "USD",
                "language": "English",
                "emergency": "911"
            }

        key = country_name.lower().strip()
        data = COUNTRY_DATA.get(key)

        if not data:
            return {
                "status": "not_found",
                "message": (
                    f"Country data not available for {country_name}. "
                    f"Please verify the destination."
                ),
                "data": None
            }

        return {
            "status": "success",
            "country": country_name,
            **data
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": "Country information unavailable. Please try again.",
            "data": None
        }

# ─────────────────────────────────────────
# FUNCTION 4 - CURRENCY CONVERSION (Real API)
# ─────────────────────────────────────────

def convert_currency(amount, from_currency, to_currency):
    try:
        if from_currency.upper() == to_currency.upper():
            return {
                "status": "success",
                "original_amount": amount,
                "converted_amount": amount,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "exchange_rate": 1.0,
                "note": "Same currency - no conversion needed"
            }

        key = os.getenv("EXCHANGE_API_KEY")
        url = (
            f"https://v6.exchangerate-api.com/v6/{key}"
            f"/pair/{from_currency}/{to_currency}/{amount}"
        )
        response = requests.get(url, timeout=10)

        if response.status_code != 200:
            return {
                "status": "failed",
                "message": "Currency conversion failed. Please try again.",
                "data": None
            }

        data = response.json()
        return {
            "status": "success",
            "original_amount": amount,
            "from_currency": from_currency.upper(),
            "to_currency": to_currency.upper(),
            "converted_amount": round(data["conversion_result"], 2),
            "exchange_rate": round(data["conversion_rate"], 4)
        }

    except requests.exceptions.Timeout:
        return {
            "status": "failed",
            "message": "Currency service timed out. Please try again.",
            "data": None
        }
    except Exception as e:
        return {
            "status": "failed",
            "message": "Currency conversion unavailable. Please try again.",
            "data": None
        }

# ─────────────────────────────────────────
# FUNCTION 5 - HOTELS (Mock Data)
# ─────────────────────────────────────────

def find_hotels(city, check_in_date, nights):
    try:
        key = city.lower().strip()

        city_map = {
            "chennai, india": "chennai",
            "los angeles, ca": "los angeles",
            "new york city": "new york",
            "nyc": "new york",
            "la": "los angeles"
        }
        key = city_map.get(key, key)

        hotels = HOTEL_DATA.get(key)

        if not hotels:
            return {
                "status": "not_found",
                "message": (
                    f"Hotel data not available for {city}. "
                    f"Please contact travel desk directly."
                ),
                "hotels": []
            }

        result = []
        for h in hotels:
            result.append({
                **h,
                "nights": nights,
                "total_usd": h["price_per_night_usd"] * nights,
                "check_in": check_in_date,
                "source": "mock_data"
            })

        return {
            "status": "success",
            "city": city,
            "nights": nights,
            "hotels": result,
            "cheapest_per_night": min(
                h["price_per_night_usd"] for h in hotels
            )
        }

    except Exception as e:
        return {
            "status": "failed",
            "message": "Hotel search failed. Please try again.",
            "hotels": []
        }

# ─────────────────────────────────────────
# FUNCTION 6 - POLICY CHECK (Rule-based now, RAG on Day 2)
# ─────────────────────────────────────────

# Policy caps - these will come from RAG document on Day 2


def check_travel_policy(item_type, amount_usd,
                        city, is_international, details=""):
    try:
        if item_type == "total_trip":
            # Build specific query for the policy document
            query = (
                f"According to Section 2 of the Macrohard corporate "
                f"travel policy, what is the manager approval threshold "
                f"for total trip costs? "
                f"Does a trip costing ${amount_usd} USD require "
                f"manager or director approval? "
                f"Details: {details}"
            )
        else:
            # Build specific query for the policy document
            query = (
                f"According to the Macrohard corporate travel policy "
                f"Section 4 for flights and Section 5 for hotels, "
                f"what is the maximum allowed {item_type} cost? "
                f"For hotels check the per night rate cap for {city}. "
                f"For flights check the per person fare cap for international routes to India. "
                f"The proposed {item_type} cost is ${amount_usd} USD. "
                f"Additional context: {details}. "
                f"State clearly PASS or FAIL with the exact policy cap amount."
            )


        response = bedrock_agent_runtime.retrieve_and_generate(
            input={"text": query},
            retrieveAndGenerateConfiguration={
                "type": "KNOWLEDGE_BASE",
                "knowledgeBaseConfiguration": {
                    "knowledgeBaseId": KNOWLEDGE_BASE_ID,
                    "modelArn": RAG_MODEL_ARN,
                    "retrievalConfiguration": {
                        "vectorSearchConfiguration": {
                            "numberOfResults": 3
                        }
                    }
                }
            }
        )

        policy_text = response["output"]["text"]

        # Determine compliance from RAG response
        fail_keywords = [
            "exceeds", "above the cap", "not within",
            "over the limit", "violates", "fails",
            "higher than allowed", "non-compliant",
            "above policy", "does not comply",
            "fail", "not compliant", "not allowed",
            "over the cap", "above the maximum",
            "exceeds the cap", "exceeds the limit"
        ]

        pass_keywords = [
            "within policy", "within the policy",
            "within the cap", "within the limit",
            "complies", "acceptable", "meets policy",
            "compliant", "passes", "pass",
            "below the cap", "below the maximum",
            "below the limit", "within the allowed",
            "does not exceed", "is within",
            "under the cap", "under the limit",
            "under the maximum", "within budget"
        ]

        policy_lower = policy_text.lower()
        is_fail = any(kw in policy_lower for kw in fail_keywords)
        is_pass = any(kw in policy_lower for kw in pass_keywords)

        if is_fail and not is_pass:
            status = "FAIL"
        elif is_pass:
            status = "PASS"
        else:
            # Keyword matching was ambiguous
            # Fall back to numeric comparison
            import re
            amounts = re.findall(r'\$[\d,]+', policy_text)
            dollar_amounts = []
            for a in amounts:
                try:
                    dollar_amounts.append(
                        float(a.replace('$', '').replace(',', ''))
                    )
                except:
                    pass

            if dollar_amounts:
                if item_type == "total_trip":
                    # For total trip the cap is the largest amount
                    # mentioned — the approval threshold
                    cap = max(dollar_amounts)
                    status = "PASS" if amount_usd <= cap else "FAIL"
                else:
                    # For hotel and flight the cap is the smallest
                    # relevant amount — the policy limit
                    relevant = [a for a in dollar_amounts
                     if a > 100 and a != amount_usd]
                    if relevant:
                        cap = min(relevant)
                        status = "PASS" if amount_usd <= cap else "FAIL"
                    else:
                        status = "REVIEW_NEEDED"
            else:
                status = "REVIEW_NEEDED"

        # After keyword check add this numeric fallback
        if status == "REVIEW_NEEDED":
            # Try to extract cap from guidance and compare numerically
            import re
            amounts = re.findall(r'\$[\d,]+', policy_text)
            if amounts:
                # Get all dollar amounts mentioned
                dollar_amounts = []
                for a in amounts:
                    try:
                        dollar_amounts.append(
                            float(a.replace('$', '').replace(',', ''))
                        )
                    except:
                        pass

                if dollar_amounts:
                    # Find the cap amount (usually the first or smallest amount mentioned)
                    cap = min(dollar_amounts)
                    if cap > 100:  # ignore small amounts like $20 differences
                        if amount_usd <= cap:
                            status = "PASS"
                        else:
                            status = "FAIL"

        result = {
            "item_type": item_type,
            "amount_usd": amount_usd,
            "city": city,
            "status": status,
            "policy_guidance": policy_text,
            "policy_source": "Macrohard Travel Policy v4.1",
            "details": details
        }

        # Always add insurance note for international
        if is_international:
            result["insurance_required"] = True
            result["insurance_note"] = (
                "Travel insurance mandatory for all "
                "international trips per Section 9.1"
            )

        return result

    except Exception as e:
        print(f"Policy RAG error: {str(e)}")
        return {
            "status": "POLICY_CHECK_UNAVAILABLE",
            "policy_guidance": "Policy validation temporarily unavailable.",
            "message": (
                "Policy validation temporarily unavailable. "
                "Please try again later."
            ),
            "item_type": item_type,
            "amount_usd": amount_usd,
            "city": city
        }

# ─────────────────────────────────────────
# TOOL EXECUTOR - called by agent loop
# ─────────────────────────────────────────

def execute_tool(tool_name, tool_input):
    if tool_name == "get_weather":
        return get_weather(**tool_input)
    elif tool_name == "search_flights":
        return search_flights(**tool_input)
    elif tool_name == "get_country_info":
        return get_country_info(**tool_input)
    elif tool_name == "convert_currency":
        return convert_currency(**tool_input)
    elif tool_name == "find_hotels":
        return find_hotels(**tool_input)
    elif tool_name == "check_travel_policy":
        return check_travel_policy(**tool_input)
    else:
        return {
            "status": "error",
            "message": f"Unknown tool: {tool_name}"
        }