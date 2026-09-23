#!/bin/bash
# infrastructure/deploy.sh
# Master deploy script — runs all steps in order
set -e

GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
log() { echo -e "${BLUE}[deploy]${NC} $1"; }
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }

export AWS_REGION="${AWS_REGION:-us-east-2}"
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

log "Starting full deployment from $REPO_ROOT"
log "Account: $ACCOUNT_ID | Region: $AWS_REGION"

# Step 1: IAM
log "Step 1/3 — Creating IAM roles..."
bash "$REPO_ROOT/infrastructure/iam_roles.sh"
ok "IAM roles ready"

# Step 2: Lambdas
log "Step 2/3 — Deploying Lambda functions..."
bash "$REPO_ROOT/infrastructure/deploy_lambdas.sh"
ok "Lambdas deployed"

# Step 3: AgentCore
log "Step 3/3 — Creating agent and registering tools..."
bash "$REPO_ROOT/infrastructure/register_tools.sh"
ok "AgentCore agent ready"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║  ✅ DEPLOYMENT COMPLETE              ║"
echo "║                                      ║"
echo "║  Next steps:                         ║"
echo "║  1. source .env                      ║"
echo "║  2. pytest tests/                    ║"
echo "║  3. streamlit run app/streamlit_app.py ║"
echo "╚══════════════════════════════════════╝"
