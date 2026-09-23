"""
tools/find_hotels.py
Phase 2 signature: find_hotels(city, check_in_date, nights)
"""
import json, sys
sys.path.insert(0, '/opt/python')
from api_calls import find_hotels

def lambda_handler(event, context):
    try:
        props = event["requestBody"]["content"]["application/json"]["properties"]
        result = find_hotels(
            city=props["city"],
            check_in_date=props["check_in_date"],
            nights=int(props.get("nights", 1))
        )
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"status": "failed", "message": str(e)})}
