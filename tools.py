# tools.py
# Tool schemas that tell Claude what each sub-agent can do

TOOLS = [
    {
        "name": "get_weather",
        "description": (
            "Get weather forecast for a destination city on specific travel dates. "
            "Returns temperature range, conditions, and packing advice. "
            "Always call this for every trip request. "
            "If this fails continue without weather data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Destination city name e.g. Chennai"
                },
                "country_code": {
                    "type": "string",
                    "description": "2-letter ISO country code e.g. IN for India, US for USA"
                },
                "travel_date": {
                    "type": "string",
                    "description": "Travel start date in YYYY-MM-DD format"
                }
            },
            "required": ["city", "country_code", "travel_date"]
        }
    },
    {
        "name": "search_flights",
        "description": (
            "Search available flights between origin and destination airports. "
            "Returns flight options sorted by price. "
            "Always call this for every trip request. "
            "If this fails the entire trip plan cannot proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin_city": {
                    "type": "string",
                    "description": "Departure city name e.g. Chicago"
                },
                "destination_city": {
                    "type": "string",
                    "description": "Arrival city name e.g. Chennai"
                },
                "departure_date": {
                    "type": "string",
                    "description": "Departure date in YYYY-MM-DD format"
                },
                "passengers": {
                    "type": "integer",
                    "description": "Number of travelers"
                },
                "trip_type": {
                    "type": "string",
                    "enum": ["business", "leisure"],
                    "description": "Type of trip"
                }
            },
            "required": [
                "origin_city",
                "destination_city", 
                "departure_date",
                "passengers",
                "trip_type"
            ]
        }
    },
    {
        "name": "get_country_info",
        "description": (
            "Get destination country information including currency, language, "
            "timezone, and emergency contacts. "
            "Always call this for international trips. "
            "Skip for domestic US trips. "
            "If this fails the trip plan cannot proceed for international destinations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "country_name": {
                    "type": "string",
                    "description": "Full country name e.g. India, Japan, United Kingdom"
                },
                "is_international": {
                    "type": "boolean",
                    "description": "True if destination is outside the USA"
                }
            },
            "required": ["country_name", "is_international"]
        }
    },
    {
        "name": "convert_currency",
        "description": (
            "Convert an amount from one currency to another. "
            "ONLY call this tool when the from_currency and "
            "to_currency are DIFFERENT. "
            "If budget is already in USD do NOT call this tool. "
            "If destination currency equals source currency "
            "do NOT call this tool. "
            "Only call when conversion is actually needed: "
            "INR to USD, GBP to USD, EUR to USD etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount to convert in USD"
                },
                "from_currency": {
                    "type": "string",
                    "description": "Source currency code e.g. USD"
                },
                "to_currency": {
                    "type": "string",
                    "description": "Target currency code e.g. INR"
                }
            },
            "required": ["amount", "from_currency", "to_currency"]
        }
    },
    {
        "name": "find_hotels",
        "description": (
            "Find hotel options in the destination city. "
            "Returns 3 options at different price points. "
            "Always call this for every trip request. "
            "If this fails the trip plan cannot proceed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Destination city name e.g. Chennai"
                },
                "check_in_date": {
                    "type": "string",
                    "description": "Check-in date in YYYY-MM-DD format"
                },
                "nights": {
                    "type": "integer",
                    "description": "Number of nights"
                }
            },
            "required": ["city", "check_in_date", "nights"]
        }
    },
    {
        "name": "check_travel_policy",
        "description": (
            "Check if a travel expense complies with company travel policy. "
            "ALWAYS call this before confirming any flight cost or hotel price. "
            "Call once for flights and once for each hotel option. "
            "Returns PASS or FAIL with the relevant policy section. "
            "If this fails entirely tell user to try again later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_type": {
                    "type": "string",
                    "enum": [
                        "flight",
                        "hotel",
                        "meal",
                        "transport",
                        "total_trip"
                    ],
                    "description": "Type of expense being validated"
                },
                "amount_usd": {
                    "type": "number",
                    "description": "Cost in USD"
                },
                "city": {
                    "type": "string",
                    "description": "City where expense occurs"
                },
                "details": {
                    "type": "string",
                    "description": "Additional context e.g. hotel name, airline, duration"
                },
                "is_international": {
                    "type": "boolean",
                    "description": "True if this is an international trip"
                }
            },
            "required": [
                "item_type",
                "amount_usd",
                "city",
                "is_international"
            ]
        }
    }
]