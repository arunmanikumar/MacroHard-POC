"""
phase3/agent.py
LangGraph wrapped in AgentCore Runtime.
Memory uses boto3 bedrock-agentcore directly (not MemoryClient SDK).
"""
from bedrock_agentcore.runtime import BedrockAgentCoreApp
import boto3, sys, os, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'phase2'))
from graph import build_graph
from state import create_initial_state

MEMORY_ID = os.getenv("AGENTCORE_MEMORY_ID", "")
ACTOR_ID  = os.getenv("AGENTCORE_ACTOR_ID", "travel-agent")
REGION    = os.getenv("AWS_REGION", "us-east-2")

# Build graph once at startup
print("Building graph...")
graph = build_graph()

# Memory client via boto3 directly
memory_client = boto3.client("bedrock-agentcore", region_name=REGION) if MEMORY_ID else None

if memory_client:
    print(f"✅ Memory ready (memory_id={MEMORY_ID})")
else:
    print("⚠️  No AGENTCORE_MEMORY_ID — running without memory")

print("✅ Graph ready — starting AgentCore server...")

app = BedrockAgentCoreApp()

def load_history(session_id):
    """Load conversation history from AgentCore Memory via boto3."""
    if not memory_client:
        return [], None
    try:
        resp = memory_client.list_events(
            memoryId=MEMORY_ID,
            actorId=ACTOR_ID,
            sessionId=session_id,
            includePayloads=True
        )
        history = []
        for event in resp.get("events", []):
            for p in event.get("payload", []):
                ch = p.get("conversationHistory", {})
                role    = ch.get("role", "user")
                content = ch.get("content", [])
                text    = content[0].get("text", "") if content else ""
                if text:
                    history.append({"role": role, "content": text})

        prev_context = None
        for e in reversed(history):
            if e["role"] == "assistant" and len(e["content"]) > 100:
                prev_context = {"last_response": e["content"][:500]}
                break
        return history, prev_context
    except Exception as ex:
        print(f"Memory load warning: {ex}")
        return [], None

def save_history(session_id, user_msg, assistant_msg):
    """Save turn to AgentCore Memory via boto3."""
    if not memory_client:
        return
    try:
        memory_client.create_event(
            memoryId=MEMORY_ID,
            actorId=ACTOR_ID,
            sessionId=session_id,
            payload=[{
                "conversationHistory": {
                    "role": "user",
                    "content": [{"text": user_msg}]
                }
            }, {
                "conversationHistory": {
                    "role": "assistant",
                    "content": [{"text": assistant_msg}]
                }
            }]
        )
    except Exception as ex:
        print(f"Memory save warning: {ex}")

@app.entrypoint
async def handler(payload):
    prompt     = payload.get("prompt", "")
    session_id = payload.get("session_id", "default")

    # Load history
    history, prev_context = load_history(session_id)

    # Detect international
    intl_kw = ["india","london","uk","japan","france","australia",
                "canada","mexico","chennai","tokyo","paris"]
    is_intl = any(k in prompt.lower() for k in intl_kw)
    if not is_intl and history:
        hist_text = " ".join(e["content"] for e in history).lower()
        is_intl = any(k in hist_text for k in intl_kw)

    # Enrich prompt for refinements
    refine_kw = ["change","update","modify","instead","switch","make it","same trip"]
    if any(k in prompt.lower() for k in refine_kw) and history:
        for e in reversed(history):
            if e["role"] == "user" and len(e["content"]) > 30:
                prompt = f"Previous request: {e['content']}\n\nModification: {payload.get('prompt','')}"
                break

    # Run LangGraph
    state = create_initial_state(
        user_input=prompt,
        session_id=session_id,
        is_international=is_intl,
        conversation_history=history,
        previous_trip_context=prev_context
    )
    result = graph.invoke(state)

    # Best response
    error      = result.get("error")
    final_plan = result.get("final_plan", "").strip()
    research   = result.get("research_summary", "").strip()
    policy     = result.get("policy_summary", "").strip()

    if error:
        response_text = f"Error: {error}"
    elif final_plan:
        response_text = final_plan
    elif research or policy:
        response_text = ""
        if research: response_text += f"**Research:**\n{research}\n\n"
        if policy:   response_text += f"**Policy:**\n{policy}"
    else:
        response_text = "No travel plan generated. Please try again."

    # Save to memory
    save_history(session_id, payload.get("prompt", ""), response_text)

    return {"response": response_text}

if __name__ == "__main__":
    app.run()