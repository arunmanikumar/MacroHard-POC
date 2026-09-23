#!/bin/bash
# infrastructure/deploy_lambdas.sh

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="${AWS_REGION:-us-east-2}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAMBDA_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/travel-agent-lambda-role"
LAYER_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:layer:travel-agent-shared:1"
WORK_DIR=$(mktemp -d)

echo "Account : $ACCOUNT_ID"
echo "Region  : $REGION"
echo ""

# ── Check required env vars ───────────────────────────────────────────────────
if [ -z "$OPENWEATHER_API_KEY" ]; then
  echo "❌ OPENWEATHER_API_KEY is not set."
  exit 1
fi
if [ -z "$EXCHANGE_API_KEY" ]; then
  echo "❌ EXCHANGE_API_KEY is not set."
  exit 1
fi
if [ -z "$KNOWLEDGE_BASE_ID" ]; then
  echo "❌ KNOWLEDGE_BASE_ID is not set."
  exit 1
fi

echo "✅ All env vars present"
echo ""

# ── Deploy single Lambda ──────────────────────────────────────────────────────
deploy_lambda() {
  FN_NAME=$1
  HANDLER=$2

  echo "Deploying $FN_NAME..."
  zip -j "$WORK_DIR/${HANDLER}.zip" "$REPO_ROOT/tools/${HANDLER}.py" > /dev/null

  EXISTS=$(aws lambda get-function \
    --function-name "$FN_NAME" \
    --region "$REGION" 2>/dev/null && echo "yes" || echo "no")

  if [ "$EXISTS" = "yes" ]; then
    aws lambda update-function-code \
      --function-name "$FN_NAME" \
      --zip-file "fileb://$WORK_DIR/${HANDLER}.zip" \
      --region "$REGION" > /dev/null
  else
    aws lambda create-function \
      --function-name "$FN_NAME" \
      --runtime python3.12 \
      --role "$LAMBDA_ROLE" \
      --handler "${HANDLER}.lambda_handler" \
      --zip-file "fileb://$WORK_DIR/${HANDLER}.zip" \
      --layers "$LAYER_ARN" \
      --timeout 30 \
      --memory-size 512 \
      --environment "Variables={KNOWLEDGE_BASE_ID=$KNOWLEDGE_BASE_ID,OPENWEATHER_API_KEY=$OPENWEATHER_API_KEY,EXCHANGE_API_KEY=$EXCHANGE_API_KEY}" \
      --region "$REGION" > /dev/null
  fi

  echo "  ✅ $FN_NAME"
}

# ── Deploy all 6 ─────────────────────────────────────────────────────────────
deploy_lambda "travel-agent-get-weather"         "get_weather"
deploy_lambda "travel-agent-search-flights"       "search_flights"
deploy_lambda "travel-agent-get-country-info"     "get_country_info"
deploy_lambda "travel-agent-convert-currency"     "convert_currency"
deploy_lambda "travel-agent-find-hotels"          "find_hotels"
deploy_lambda "travel-agent-check-travel-policy"  "check_travel_policy"

rm -rf "$WORK_DIR"
echo ""
echo "✅ All 6 Lambdas deployed"
