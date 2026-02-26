"""
nodes/agent.py — Core LangChain executor node.

Loads the relevant skill prompt, attaches tools dynamically,
and executes the agent via LangChain. 
"""

import json
import logging
from pathlib import Path
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage

logger = logging.getLogger(__name__)

# Paths
SKILLS_DIR = Path(__file__).parent.parent / "skills"
MCP_CONFIG_PATH = Path(__file__).parent.parent / "config" / "mcp_config.json"
IDENTITY_FILE = Path(__file__).parent.parent / "skills" / "identity" / "skill.md"

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

def _get_enabled_tools_and_write_actions() -> tuple[list[str], set[str], dict[str, str]]:
    """
    Return enabled tools, write actions, and action-to-skill mapping based on mcp_config.json.
    """
    config = _load_mcp_config()
    enabled_tools = []
    write_actions = set()
    action_skill_map = {}
    
    for skill_name, skill_cfg in config.items():
        if isinstance(skill_cfg, dict) and skill_cfg.get("enabled", True):
            skill_tools = skill_cfg.get("tools", [])
            skill_write_actions = skill_cfg.get("write_actions", [])
            
            enabled_tools.extend(skill_tools)
            write_actions.update(skill_write_actions)
            
            for action in skill_tools:
                action_skill_map[action] = skill_name
                
    return enabled_tools, write_actions, action_skill_map

async def agent_node(state: dict) -> dict:
    """
    Execute the LangChain agent with dynamically loaded skills + tools.
    """
    logger.info("--- [Node: Agent] ---")
    
    messages = state.get("messages", [])
    user_input = state.get("user_input", "")
    
    if not messages and not user_input:
        logger.debug("  -> Empty state and no user input, skipping agent loop.")
        return {}
    tool_failure_count = state.get("tool_failure_count", 0)

    # ── Load core identity ──────────────────────────────────────────
    identity_prompt = _load_identity_prompt()

    # ── Fetch long-term memory context and dynamic skill context ────
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

    # ── Construct full system prompt: Identity → Memory → Skill ────
    prompt_parts = []
    if identity_prompt:
        prompt_parts.append(identity_prompt)
    if memory_context:
        prompt_parts.append(f"## User Context (from long-term memory)\\n{memory_context}")
    prompt_parts.append(skill_prompts)
    
    # We append extra formatting rules if we want
    full_system_prompt = "\\n\\n---\\n\\n".join(prompt_parts) + "\\n\\nALWAYS format your output using standard Markdown (use *, _, `, ```, lists). Do NOT use HTML tags. Respond directly to the user."

    # ── Build LangChain Tools ─────────────────────────────────────
    enabled_tool_names, _, _ = _get_enabled_tools_and_write_actions()
    
    from mcp_servers import GLOBAL_TOOL_REGISTRY
    
    all_tools = []
    for action_name in enabled_tool_names:
        real_func = GLOBAL_TOOL_REGISTRY.get(action_name)
        if not real_func:
            logger.warning(f"  -> Tool {action_name} enabled but missing.")
            continue
        # In LangChain, tools can be raw functions. `bind_tools` converts them.
        all_tools.append(real_func)

    # ── Create agent LLM ────────────────────────────────────────────────
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    
    # Bind tools
    llm_with_tools = llm.bind_tools(all_tools) if all_tools else llm

    try:
        # Prepend the system message
        invoke_messages = [SystemMessage(content=full_system_prompt)]
        
        # Then append the persistent history
        invoke_messages.extend(messages)
        
        # Then append the current user input as a HumanMessage
        if user_input:
            human_msg = HumanMessage(content=user_input)
            invoke_messages.append(human_msg)

        result = await llm_with_tools.ainvoke(invoke_messages)
        logger.info(f"  -> Agent response generated ({len(str(result.content))} chars)")
        
        # Return both the human message (so it saves to state) and the AI response
        new_messages = [human_msg, result] if user_input else [result]
        
        return {
            "messages": new_messages, 
            "tool_failure_count": 0, 
            "agent_response": result.content,
            "user_input": "" # Clear user input so we don't duplicate it on loopbacks
        }

    except Exception as e:
        tool_failure_count += 1
        logger.error(f"  -> Agent error (attempt {tool_failure_count}/3): {e}", exc_info=True)

        if tool_failure_count >= 3:
            logger.error("  -> Max failures reached, returning fallback response")
            return {
                "messages": [AIMessage(content=f"I'm sorry, I encountered repeated errors trying to process your request. Error: {str(e)}\\n\\nPlease try again.")],
                "tool_failure_count": tool_failure_count,
            }

        return {
            "tool_failure_count": tool_failure_count,
            "_retry": True,
        }
