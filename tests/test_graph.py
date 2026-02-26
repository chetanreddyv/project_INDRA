import asyncio
import logging
from dotenv import load_dotenv
load_dotenv()
from langgraph.checkpoint.memory import MemorySaver

import sys
import os

# Ensure the root directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from nodes.graph import build_graph

logging.basicConfig(level=logging.INFO)

async def run_test():
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    
    from memory import memorygate
    await memorygate.initialize()
    
    config = {"configurable": {"thread_id": "test_123"}}
    
    print("\n--- Test 1: Simple Message ---")
    async for event in graph.astream(
        {"chat_id": "test_123", "user_input": "Hi!"},
        config=config,
        stream_mode="updates"
    ):
        print("Event:", event)
        
    state = await graph.aget_state(config)
    print("\nFinal State Values:", state.values.get("messages"))

    print("\n--- Test 2: Write Action ---")
    async for event in graph.astream(
        {"chat_id": "test_123", "user_input": "Schedule a meeting with john for tomorrow at 2pm about project alpha"},
        config=config,
        stream_mode="updates"
    ):
        print("Event:", event)

    state = await graph.aget_state(config)
    print("\nFinal State Values:", state.values.get("messages"))

if __name__ == "__main__":
    asyncio.run(run_test())
