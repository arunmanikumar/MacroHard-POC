"""
tools/get_weather.py
Phase 2 signature: get_weather(city, country_code, travel_date)
"""
import json, sys
sys.path.insert(0, '/opt/python')
from api_calls import get_weather

def lambda_handler(event, context):
    try:
        props = event["requestBody"]["content"]["application/json"]["properties"]
        result = get_weather(
            city=props["city"],
            country_code=props["country_code"],
            travel_date=props["travel_date"]
        )
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"status": "failed", "message": str(e)})}
