import asyncio
from dotenv import load_dotenv
load_dotenv()

from memory import memorygate

async def main():
    await memorygate.initialize()
    
    # Store some interaction
    await memorygate.process("test_123", "Remind me I love chocolate", "Got it, chocolate is your favorite.")

    # fetch context
    ctx = await memorygate.get_context("test_123")
    print("CONTEXT:")
    print(ctx)

if __name__ == "__main__":
    asyncio.run(main())
