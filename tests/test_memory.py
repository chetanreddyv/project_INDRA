import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from memory import memorygate

async def main():
    print("--- 1. Initialization ---")
    await memorygate.initialize()
    print("✓ MemoryGate & Zvec Initialized")
    
    print("\n--- 2. Manually Inserting Context ---")
    # Simulate extraction of memories from past conversations
    # In a real app, the LLM sets these. For this test, we skip LLM generation
    # and shove facts directly into Zvec using the `apply_updates` function
    from memory import ExtractedMemory
    
    dummy_mem = ExtractedMemory(
        preferences=["Prefers concise answers.", "Uses Python for scripting."],
        facts=["User's name is Chetan.", "Works on a project called INDRA.", "Lives in Seattle."],
        corrections=[],
        obsolete_items=[],
        important=True
    )
    
    await memorygate.store.apply_updates(dummy_mem)
    print("✓ Inserted 5 distinct memory facts into SQLite + Zvec index.")
    
    print("\n--- 3. Testing Semantic Retrieval (Cosine Similarity) ---")
    
    # Query 1: Should match "User's name is Chetan."
    q1 = "What is my name?"
    res1 = await memorygate.store.get_relevant_context(q1, top_k=2)
    print(f"QUERY: '{q1}'")
    print(f"RESULT:\n{res1}\n")
    
    # Query 2: Should match Python & INDRA
    q2 = "What project am I building and what language should I use?"
    res2 = await memorygate.store.get_relevant_context(q2, top_k=2)
    print(f"QUERY: '{q2}'")
    print(f"RESULT:\n{res2}\n")

    print("\n--- 4. Testing End-to-End Extraction (Requires Gemini API Key) ---")
    if not os.environ.get("GOOGLE_API_KEY"):
         print("⚠ Skipping E2E test. GOOGLE_API_KEY not found in .env.")
    else:
        print("Feeding new conversation turn to MemoryGate. Gemini will extract facts.")
        await memorygate.process(
            thread_id="test_thread_99",
            user_input="I just adopted a new golden retriever named Max!",
            agent_response="That's wonderful! Golden retrievers are great dogs."
        )
        print("✓ MemoryGate async extraction trigger returned.")
        
        # Let's immediately query to see if the LLM caught the golden retriever fact.
        # Note: In a real app we might need to wait a tiny bit for the async extraction to complete
        # if `process` was truly decoupled, but memorygate.process() awaits the agent run currently.
        
        print("\nQuerying for dog fact...")
        res3 = await memorygate.store.get_relevant_context("Do I have any pets?", top_k=1)
        print(f"RESULT:\n{res3}\n")
        
    print("\n--- Tests Complete ---")

if __name__ == "__main__":
    asyncio.run(main())
