"""
nodes/router.py — Intent classification and skill routing.

Uses a fast Gemini call with structured output to determine which skill
and toolset to activate for the user's query.
"""

import logging
from typing import Literal
from pydantic import BaseModel
from pydantic_ai import Agent

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You are a fast intent classifier for a personal assistant.
Given a user message, determine which skill module should handle it.

Available skills:
- "google_workspace": Email, calendar, meetings, Drive — anything Google-related
- "code_assistant": Code debugging, file analysis, script generation, error analysis
- "data_analyst": SQL queries, database questions, data analysis
- "general_chat": General conversation, advice, knowledge questions, anything else

Respond with the single best skill match and your confidence level."""


class RouterDecision(BaseModel):
    """Structured output from the router."""

    skill: Literal["general_chat", "google_workspace", "code_assistant", "data_analyst"]
    confidence: float
    reasoning: str


# Lazy-init to avoid failing at import time when GOOGLE_API_KEY isn't set
_router_agent = None


def _get_router_agent() -> Agent:
    global _router_agent
    if _router_agent is None:
        _router_agent = Agent(
            "google-gla:gemini-2.5-flash",
            system_prompt=ROUTER_SYSTEM_PROMPT,
            output_type=RouterDecision,
        )
    return _router_agent


async def router_node(state: dict) -> dict:
    """
    Classify user intent and select the appropriate skill.
    Falls back to general_chat if confidence is low.
    """
    logger.info("--- [Node: Router] ---")
    user_input = state.get("user_input", "")

    try:
        agent = _get_router_agent()
        result = await agent.run(user_input)
        decision: RouterDecision = result.output

        if decision.confidence < 0.5:
            logger.info(f"  -> Low confidence ({decision.confidence}), falling back to general_chat")
            return {"skill_selected": "general_chat", "routing_reasoning": decision.reasoning}

        logger.info(f"  -> Skill: {decision.skill} (confidence: {decision.confidence})")
        return {"skill_selected": decision.skill, "routing_reasoning": decision.reasoning}

    except Exception as e:
        logger.error(f"  -> Router failed: {e}, falling back to general_chat")
        return {"skill_selected": "general_chat", "routing_reasoning": f"Router error: {e}"}
