"""
tools/search_flights.py
Phase 2 signature: search_flights(origin_city, destination_city, departure_date, passengers, trip_type)
"""
import json, sys
sys.path.insert(0, '/opt/python')
from api_calls import search_flights

def lambda_handler(event, context):
    try:
        props = event["requestBody"]["content"]["application/json"]["properties"]
        result = search_flights(
            origin_city=props["origin_city"],
            destination_city=props["destination_city"],
            departure_date=props["departure_date"],
            passengers=int(props.get("passengers", 1)),
            trip_type=props.get("trip_type", "one-way")
        )
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"status": "failed", "message": str(e)})}
