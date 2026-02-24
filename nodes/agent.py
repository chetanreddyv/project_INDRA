"""
nodes/agent.py — Core Pydantic AI executor node.

Loads the relevant skill prompt, attaches MCP tools dynamically,
and executes the agent. Handles tool failure self-correction.

HITL Security Model
-------------------
Approval is NOT decided by the LLM. Instead, every tool whose name
appears in the ``write_actions`` list of mcp_config.json is wrapped
by a Python interceptor.  When the LLM tries to *call* such a tool
the interceptor raises ``WriteActionRequiresApproval`` before any
side-effect occurs.  The agent node catches that exception, stores
the pending action, and routes the graph to the human_approval node.
The LLM never has the ability to bypass this gate.
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


# ==========================================================
# Write-Action Gate
# ==========================================================

class WriteActionRequiresApproval(Exception):
    """
    Raised inside a write-action tool wrapper to abort the current
    agent run and route to the human_approval node.

    Attributes
    ----------
    action : str
        The tool/action name that was intercepted (e.g. ``send_email``).
    tool_args : dict
        The arguments the LLM passed to the tool.
    skill : str
        The skill/server the action belongs to.
    """
    def __init__(self, action: str, tool_args: dict, skill: str):
        self.action = action
        self.tool_args = tool_args
        self.skill = skill
        super().__init__(f"Write action intercepted by Python gate: {action}")


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


def _get_write_action_set() -> set[str]:
    """
    Return the flat set of write/destructive action names defined
    across ALL skills in mcp_config.json.

    This is the single source of truth — the LLM has no say in
    whether a given tool name requires approval.
    """
    config = _load_mcp_config()
    write_actions: set[str] = set()
    for skill_config in config.values():
        if isinstance(skill_config, dict):
            write_actions.update(skill_config.get("write_actions", []))
    return write_actions


def _make_write_action_tool(action_name: str, skill_name: str):
    """
    Return a Pydantic AI–compatible async tool function that
    *intercepts* the call and raises ``WriteActionRequiresApproval``
    before any real side-effect runs.

    The ``action_name`` is embedded in the closure so each generated
    wrapper is specific to that action.
    """
    async def _interceptor(**kwargs) -> str:   # noqa: ANN202
        logger.warning(
            f"  -> [GATE] Write action intercepted by Python: {action_name}"
        )
        raise WriteActionRequiresApproval(
            action=action_name,
            tool_args=kwargs,
            skill=skill_name,
        )

    # Give the function a meaningful name so Pydantic AI can register it
    _interceptor.__name__ = action_name
    _interceptor.__doc__ = (
        f"Tool '{action_name}' has been intercepted by the Python approval gate. "
        "This function will never execute a side-effect — it raises "
        "WriteActionRequiresApproval so the graph pauses for human approval."
    )
    return _interceptor


async def agent_node(state: dict) -> dict:
    """
    Execute the Pydantic AI agent with dynamically loaded skills + tools.

    Flow
    ----
    1. Build full system prompt (identity → memory → skill).
    2. Register write-action tools as Python interceptors.
    3. Run the agent.
    4. If the LLM calls a write tool → Python raises
       ``WriteActionRequiresApproval`` → set ``pending_action`` for HITL.
    5. On other tool failure → increment failure count and retry (up to 3×).
    """
    logger.info("--- [Node: Agent] ---")

    user_input = state.get("user_input", "")
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
        prompt_parts.append(f"## User Context (from long-term memory)\n{memory_context}")
    prompt_parts.append(skill_prompts)
    full_system_prompt = "\n\n---\n\n".join(prompt_parts)

    # ── Build Python write-action interceptors ──────────────────────
    # These are registered as tools on the agent so the LLM can
    # "call" them — but Python immediately raises an exception
    # before any real side-effect occurs.
    write_actions = _get_write_action_set()
    config = _load_mcp_config()

    # Build a map of action → skill name for clear logging
    action_skill_map: dict[str, str] = {}
    for skill_name, skill_cfg in config.items():
        if isinstance(skill_cfg, dict):
            for action in skill_cfg.get("write_actions", []):
                action_skill_map[action] = skill_name

    interceptor_tools = [
        _make_write_action_tool(action, action_skill_map.get(action, "unknown"))
        for action in write_actions
    ]

    # ── Create agent ────────────────────────────────────────────────
    agent = Agent(
        "google-gla:gemini-2.5-flash",
        system_prompt=full_system_prompt,
        output_type=AgentResponse,
        tools=interceptor_tools,
    )

    try:
        result = await agent.run(user_input)
        response_text = result.output.response

        logger.info(f"  -> Agent response generated ({len(response_text)} chars)")
        return {
            "agent_response": response_text,
            "pending_action": None,
            "tool_failure_count": 0,
        }

    except WriteActionRequiresApproval as wa:
        # ── Python gate fired — route to HITL ──────────────────────
        logger.info(
            f"  -> [GATE] Routing to HITL: action={wa.action}, "
            f"skill={wa.skill}, args={wa.tool_args}"
        )
        # Build a human-readable summary of what the LLM wanted to do
        args_summary = "\n".join(
            f"  **{k}**: {v}" for k, v in wa.tool_args.items()
        )
        pending_action = {
            "action": wa.action,
            "skill": wa.skill,
            "tool_args": wa.tool_args,
            "details": (
                f"The assistant wants to call **{wa.action}** with:\n{args_summary}"
                if wa.tool_args
                else f"The assistant wants to call **{wa.action}**."
            ),
        }
        return {
            "pending_action": pending_action,
            "agent_response": None,
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
