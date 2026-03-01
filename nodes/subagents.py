import logging
from typing import Optional
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage

from nodes.graph import AgentState
from nodes.tools import execute_tools_node
from nodes.agent import _get_enabled_tools_and_write_actions
from mcp_servers import GLOBAL_TOOL_REGISTRY

logger = logging.getLogger(__name__)

async def custom_research_agent_node(state: AgentState) -> dict:
    logger.info("--- [Node: Research Agent] ---")
    
    messages = state.get("messages", [])
    user_input = state.get("user_input", "")
    
    tool_failure_count = state.get("tool_failure_count", 0)

    # 1. Researcher Identity
    full_system_prompt = (
        "You are an autonomous Research Subagent.\n"
        "Your task is to thoroughly investigate the given query using your tools, "
        "and produce a comprehensive final report.\n"
        "Do not stop until you have gathered sufficient information.\n"
        "When you are finished, output your final report directly. Do NOT use any tools that require human approval."
    )

    # 2. Build Tools (Only safe/read-only tools)
    enabled_tool_names, write_actions, _ = _get_enabled_tools_and_write_actions()
    
    safe_tools = []
    for action_name in enabled_tool_names:
        if action_name in write_actions:
            continue # Skip dangerous tools
            
        real_func = GLOBAL_TOOL_REGISTRY.get(action_name)
        if real_func:
            safe_tools.append(real_func)

    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    llm_with_tools = llm.bind_tools(safe_tools) if safe_tools else llm

    try:
        invoke_messages = [SystemMessage(content=full_system_prompt)]
        invoke_messages.extend(messages)
        
        if user_input:
            human_msg = HumanMessage(content=user_input)
            invoke_messages.append(human_msg)

        result = await llm_with_tools.ainvoke(invoke_messages)
        
        new_messages = [human_msg, result] if user_input else [result]
        
        return {
            "messages": new_messages, 
            "tool_failure_count": 0, 
            "agent_response": result.content,
            "user_input": "" 
        }

    except Exception as e:
        tool_failure_count += 1
        logger.error(f"  -> Research Agent error: {e}", exc_info=True)
        if tool_failure_count >= 3:
            return {
                "messages": [AIMessage(content=f"Research failed due to repeated errors: {str(e)}")],
                "tool_failure_count": tool_failure_count,
            }
        return {
            "tool_failure_count": tool_failure_count,
            "_retry": True,
        }

def route_research(state: AgentState) -> str:
    if state.get("tool_failure_count", 0) >= 3:
        return END

    if state.get("_retry"):
        return "research_agent"

    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]
    
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return END

    # All tools are safe, so just execute them
    return "execute_safe_tools"

def build_researcher_graph():
    builder = StateGraph(AgentState)
    builder.add_node("research_agent", custom_research_agent_node) 
    builder.add_node("execute_safe_tools", execute_tools_node)
    
    builder.add_edge(START, "research_agent")
    
    builder.add_conditional_edges(
        "research_agent",
        route_research,
        ["execute_safe_tools", "research_agent", END],
    )
    
    builder.add_edge("execute_safe_tools", "research_agent")
    
    return builder.compile()
