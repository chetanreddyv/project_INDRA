"""
nodes/agent.py — Core Pydantic AI executor node.

Loads the relevant skill prompt, attaches MCP tools dynamically,
and executes the agent. Handles tool failure self-correction.
"""

import os
import json
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_ai import Agent

logger = logging.getLogger(__name__)

# Pydantic structured output for Telegram to avoid Markdown errors
class AgentResponse(BaseModel):
    response: str = Field(
        description="The final message to send to the user. MUST be formatted using standard Markdown (so you can use *, _, `, ```, lists, etc). Do NOT use HTML tags."
    )

# Paths
SKILLS_DIR = Path(__file__).parent.parent / "skills"
MCP_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp_config.json"
IDENTITY_FILE = Path(__file__).parent.parent / "identity.md"





def _load_identity_prompt() -> str:
    """Load the core identity prompt from identity.md."""
    if IDENTITY_FILE.exists():
        return IDENTITY_FILE.read_text()
    return ""


def _load_mcp_config() -> dict:
    """Load MCP tool configuration."""
    if MCP_CONFIG_PATH.exists():
        return json.loads(MCP_CONFIG_PATH.read_text())
    return {}


def _get_all_write_actions() -> list[str]:
    """Get the list of write/destructive actions across all configured skills."""
    config = _load_mcp_config()
    write_actions = []
    for skill_config in config.values():
        if isinstance(skill_config, dict):
            write_actions.extend(skill_config.get("write_actions", []))
    return list(set(write_actions))


async def agent_node(state: dict) -> dict:
    """
    Execute the Pydantic AI agent with dynamically loaded skills + tools.
    
    Flow:
    1. Load all skill prompts to give agent full context
    2. Run agent with user input + conversation context
    3. If agent wants to execute a write action → set pending_action for HITL
    4. On tool failure → increment failure count and retry (up to 3x)
    """
    logger.info("--- [Node: Agent] ---")
    
    user_input = state.get("user_input", "")
    tool_failure_count = state.get("tool_failure_count", 0)
    

    
    # Load core identity
    identity_prompt = _load_identity_prompt()
    
    # Fetch long-term memory context and dynamic skill context
    memory_context = ""
    skill_prompts = "You are a helpful personal assistant. Be concise and accurate."
    thread_id = state.get("chat_id", "default_thread")
    try:
        from memory import memorygate
        memory_context = await memorygate.get_context(thread_id=thread_id)
        if memory_context != "No established context.":
            logger.info(f"  -> Successfully retrieved memory context ({len(memory_context)} chars)")
            
        skill_prompts = await memorygate.get_relevant_skills(user_input)
    except Exception as e:
        logger.warning(f"  -> Context/Skill retrieval skipped/failed: {e}")
    
    # Construct full system prompt: Identity -> Memory -> Skill
    prompt_parts = []
    if identity_prompt:
        prompt_parts.append(identity_prompt)
    if memory_context:
        prompt_parts.append(f"## User Context (from long-term memory)\n{memory_context}")
    prompt_parts.append(skill_prompts)
    
    full_system_prompt = "\n\n---\n\n".join(prompt_parts)
    
    # Create the agent with Gemini & enforce structured output
    agent = Agent(
        "google-gla:gemini-2.5-flash",
        system_prompt=full_system_prompt,
        output_type=AgentResponse,
    )
    
    try:
        result = await agent.run(user_input)
        response_text = result.output.response
        
        # Check if the response indicates a write action was requested
        # (In a full implementation, this would use MCP tool calls and
        # intercept them. For now, we detect intent from the response.)
        write_actions = _get_all_write_actions()
        
        # Simple heuristic: if the skill has write tools and the user
        # is asking to do something (not just read), flag for approval
        action_keywords = {
            "send_email": ["send", "email", "mail", "draft and send"],
            "create_event": ["create event", "schedule", "book"],
            "create_meeting": ["create meeting", "set up meeting", "schedule meeting"],
        }
        
        pending_action = None
        user_lower = user_input.lower()
        for action, keywords in action_keywords.items():
            if action in write_actions and any(kw in user_lower for kw in keywords):
                pending_action = {
                    "action": action,
                    "details": response_text,
                    "skill": "all",
                }
                logger.info(f"  -> Write action detected: {action}, routing to HITL")
                break
        
        if pending_action:
            return {
                "pending_action": pending_action,
                "agent_response": None,
                "tool_failure_count": 0,
            }
        
        logger.info(f"  -> Agent response generated ({len(response_text)} chars)")
        return {
            "agent_response": response_text,
            "pending_action": None,
            "tool_failure_count": 0,
        }
        
    except Exception as e:
        tool_failure_count += 1
        logger.error(f"  -> Agent error (attempt {tool_failure_count}/3): {e}")
        
        if tool_failure_count >= 3:
            logger.error("  -> Max failures reached, returning fallback response")
            return {
                "agent_response": (
                    "I'm sorry, I encountered repeated errors trying to process your request. "
                    f"Error: {str(e)}\n\nPlease try again or rephrase your request."
                ),
                "pending_action": None,
                "tool_failure_count": tool_failure_count,
            }
        
        # Self-correction: retry with error context
        return {
            "agent_response": None,
            "pending_action": None,
            "tool_failure_count": tool_failure_count,
            "_retry": True,
        }
