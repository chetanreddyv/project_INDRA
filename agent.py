import asyncio
from typing import TypedDict, Optional, Any
from pydantic import BaseModel

from fastapi import FastAPI, BackgroundTasks
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt, Command

from pydantic_ai import Agent

# ==========================================================
# 1. State & Agents
# ==========================================================

class State(TypedDict):
    chat_id: str
    user_input: str
    skill_selected: Optional[str]
    pending_tool_call: Optional[dict]
    agent_response: Optional[str]

# ==========================================================
# 2. Nodes
# ==========================================================

async def router_node(state: State):
    print("\n--- [Node: Router] ---")
    user_input = state.get("user_input", "").lower()
    
    skill = "general_chat"
    if "email" in user_input or "calendar" in user_input:
        skill = "google_workspace"
        
    print(f"  -> Selected Skill: {skill}")
    return {"skill_selected": skill}

async def memorygate_node(state: State):
    print("\n--- [Node: MemoryGate (Background Task)] ---")
    # Simulate a decoupled process taking some time
    await asyncio.sleep(0.5)
    print(f"  -> Extracted preferences from: '{state.get('user_input')}'")
    print(f"  -> Upserting to Vector DB...")
    return {}

async def agent_node(state: State):
    print("\n--- [Node: Agent] ---")
    user_input = state.get("user_input", "").lower()
    
    # Simulate an agent hitting a tool that needs approval (e.g. via MCP)
    if "email" in user_input:
        print("  -> Agent decided to call 'send_email' tool...")
        return {
            "pending_tool_call": {
                "action": "send_email",
                "details": "To: boss@corp.com\nSubject: Update\nBody: Requesting approval for the draft..."
            }
        }
        
    # Otherwise normal response
    print("  -> Agent provides normal response...")
    return {
        "pending_tool_call": None,
        "agent_response": f"I can help with that! (Skill: {state.get('skill_selected')})"
    }

async def human_approval_node(state: State):
    print("\n--- [Node: Human Approval] ---")
    tool_call = state.get("pending_tool_call")
    
    # We use LangGraph's interrupt to pause the graph
    # This value is what the webserver will see as the interrupt payload
    decision = interrupt({
        "action": tool_call["action"],
        "details": tool_call["details"]
    })
    
    # After resume, this code executes with `decision` = user's choice
    print(f"  -> Human Decision Received: {decision}")
    
    if decision == "Approved":
        response = f"Successfully executed {tool_call['action']}!"
    else:
        response = f"Action {tool_call['action']} was rejected. Reason: {decision}"
        
    return {
        "agent_response": response,
        "pending_tool_call": None
    }

# ==========================================================
# 3. LangGraph Routing
# ==========================================================

def route_after_agent(state: State):
    if state.get("pending_tool_call"):
        return "human_approval"
    return END

builder = StateGraph(State)

builder.add_node("router", router_node)
builder.add_node("memorygate", memorygate_node)
builder.add_node("agent", agent_node)
builder.add_node("human_approval", human_approval_node)

builder.add_edge(START, "router")
# Fork the graph: it will run memorygate and agent in parallel
builder.add_edge("router", "memorygate")
builder.add_edge("router", "agent")

builder.add_edge("memorygate", END)
builder.add_conditional_edges("agent", route_after_agent, ["human_approval", END])
builder.add_edge("human_approval", END)

memory_saver = MemorySaver()
graph = builder.compile(checkpointer=memory_saver)

# ==========================================================
# 4. FastAPI Setup
# ==========================================================

app = FastAPI(title="Agentic App")

class WebhookPayload(BaseModel):
    chat_id: str
    text: str

class ActionPayload(BaseModel):
    chat_id: str
    action_decision: str

@app.post("/webhook")
async def receive_webhook(payload: WebhookPayload, background_tasks: BackgroundTasks):
    """
    Receives incoming chat message.
    """
    chat_id = payload.chat_id
    text = payload.text
    print(f"\n[Webhook] Msg from {chat_id}: {text}")

    config = {"configurable": {"thread_id": chat_id}}
    
    # Start graph in background. Webhook acks instantly.
    background_tasks.add_task(run_graph_and_respond, {"chat_id": chat_id, "user_input": text}, config)
    return {"status": "processing"}

async def run_graph_and_respond(inputs: dict, config: dict):
    # stream_mode="updates" ignores internal states
    async for event in graph.astream(inputs, config=config, stream_mode="updates"):
        pass
    
    state = graph.get_state(config)
    pending = state.next
    
    if pending:
        # We are paused on an interrupt
        interrupted_val = state.tasks[0].interrupts[0].value
        print(f"\n💬 [Telegram Bot] Please approve this action:")
        print(f"Action: {interrupted_val['action']}\n{interrupted_val['details']}")
        print(f"Buttons: [Approve] [Reject]")
    else:
        # Run finished
        print(f"\n💬 [Telegram Bot] Response:")
        print(state.values.get("agent_response"))


@app.post("/webhook/action")
async def receive_action(payload: ActionPayload, background_tasks: BackgroundTasks):
    """
    Receives an action decision (Approve/Reject) from inline buttons.
    """
    chat_id = payload.chat_id
    decision = payload.action_decision
    print(f"\n[Webhook Action] User {chat_id} clicked: {decision}")
    
    config = {"configurable": {"thread_id": chat_id}}
    
    # Resume the graph
    background_tasks.add_task(resume_graph, config, decision)
    return {"status": "resuming"}
    
async def resume_graph(config: dict, decision: str):
    # We pass Command(resume=decision) inside astream to resume
    async for event in graph.astream(Command(resume=decision), config=config, stream_mode="updates"):
        pass
        
    state = graph.get_state(config)
    if not state.next:
        print(f"\n💬 [Telegram Bot] Response:")
        print(state.values.get("agent_response"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("personal_assistant:app", host="0.0.0.0", port=8000, reload=True)
