"""
phase3/app.py
Streamlit UI — works locally (http) and in production (AgentCore ARN).
"""
import os, json, requests
import streamlit as st
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

# Local dev: call agent.py running on port 8080
# Production: call AgentCore endpoint
LOCAL_URL    = "http://127.0.0.1:8080/invocations"
AGENT_ARN    = os.getenv("AGENTCORE_AGENT_ARN", "")
USE_LOCAL    = not bool(AGENT_ARN)

st.set_page_config(
    page_title="Macrohard Travel Planner",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Macrohard Corporate Travel Planner")
st.caption(
    "Phase 3 — Bedrock AgentCore + LangGraph | "
    + ("🟡 Local mode" if USE_LOCAL else "🟢 Cloud mode")
)

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Session")
    st.code(st.session_state.session_id[:16] + "...")
    if st.button("🔄 New Session"):
        st.session_state.session_id = str(uuid4())
        st.session_state.messages = []
        st.rerun()
    st.divider()
    st.markdown("**Policy (HR-TRAV-001 v4.1)**")
    st.markdown("- 🏨 Domestic: $175/night")
    st.markdown("- 🌐 International: $250/night")
    st.markdown("- ✈️ Insurance mandatory intl")
    st.divider()
    st.markdown("**Infrastructure**")
    st.markdown("- Runtime: AgentCore")
    st.markdown("- Memory: AgentCore")
    st.markdown("- RAG: Bedrock KB")
    st.markdown("- Model: Claude Haiku 4.5")

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
if query := st.chat_input("Plan a trip (e.g. Chicago to Chennai Nov 15, 5 days, $6000)"):
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Planning your trip..."):
            try:
                payload = {
                    "prompt": query,
                    "session_id": st.session_state.session_id
                }

                if USE_LOCAL:
                    # Local: call agent.py directly
                    resp = requests.post(
                        LOCAL_URL,
                        json=payload,
                        timeout=120
                    )
                    result = resp.json()
                    answer = result.get("response", "No response")

                else:
                    # Production: call AgentCore cloud endpoint
                    import boto3
                    client = boto3.client(
                        "bedrock-agentcore",
                        region_name=os.getenv("AWS_REGION", "us-east-2")
                    )
                    resp = client.invoke_agent_runtime(
                        agentRuntimeArn=AGENT_ARN,
                        sessionId=st.session_state.session_id,
                        payload=json.dumps(payload)
                    )
                    result = json.loads(resp["body"].read())
                    answer = result.get("response", "No response")

                st.markdown(answer)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer
                })

            except Exception as e:
                st.error(f"Error: {str(e)}")