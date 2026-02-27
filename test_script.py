import asyncio
from httpx import AsyncClient

async def run():
    async with AsyncClient() as client:
        res = await client.post(
            "http://localhost:8000/api/v1/chat/1346735748",
            json={"user_input": "Hello Indra."}
        )
        print("Response:", res.json())

asyncio.run(run())
