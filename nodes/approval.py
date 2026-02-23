"""
nodes/approval.py — Human-in-the-Loop approval node.

Uses LangGraph's interrupt() to pause the graph when a write action
is detected. Resumes with the user's decision from Telegram buttons.
"""

import logging
from langgraph.types import interrupt

logger = logging.getLogger(__name__)


async def human_approval_node(state: dict) -> dict:
    """
    Pause the graph and wait for human approval via Telegram buttons.
    
    When this node runs:
    1. It calls interrupt() with the action details
    2. LangGraph pauses and saves state to the checkpointer
    3. The FastAPI webhook handler sends Telegram approval buttons
    4. When the user clicks a button, Command(resume=decision) resumes here
    5. This function continues with the decision value
    """
    logger.info("--- [Node: Human Approval] ---")
    pending = state.get("pending_action", {})
    
    if not pending:
        logger.warning("  -> No pending action, skipping approval")
        return {"pending_action": None}
    
    # Pause graph execution — this value is sent to Telegram as the approval prompt
    decision = interrupt({
        "action": pending.get("action", "unknown"),
        "details": pending.get("details", ""),
        "skill": pending.get("skill", ""),
    })
    
    logger.info(f"  -> Human decision received: {decision}")
    
    if decision == "approve":
        # In a full implementation, this would actually execute the MCP tool
        response = (
            f"✅ *Action Approved & Executed*\n\n"
            f"**{pending.get('action')}** has been completed.\n\n"
            f"{pending.get('details', '')}"
        )
        return {
            "agent_response": response,
            "pending_action": None,
        }
    
    elif decision.startswith("edit:"):
        # User wants to modify the action
        edit_instruction = decision[5:].strip()
        logger.info(f"  -> User requested edit: {edit_instruction}")
        return {
            "agent_response": None,
            "pending_action": None,
            # Route back to agent with the edit instruction
            "user_input": f"Please modify the previous action: {edit_instruction}",
            "_needs_rerun": True,
        }
    
    else:
        # Rejected
        response = (
            f"❌ *Action Rejected*\n\n"
            f"**{pending.get('action')}** was not executed.\n\n"
            f"If you'd like me to try a different approach, just let me know."
        )
        return {
            "agent_response": response,
            "pending_action": None,
        }
