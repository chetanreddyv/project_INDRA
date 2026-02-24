import asyncio
import logging
from collections import defaultdict
from typing import Callable, Coroutine, Any, Dict

logger = logging.getLogger("core.lane_manager")

class LaneManager:
    """
    Manages asynchronous task queues per session/thread ID.
    
    Ensures that incoming messages and HITL callbacks for a specific user
    are processed sequentially, preventing race conditions where multiple
    concurrent LangGraph executions might corrupt the SQLite checkpointer
    state or duplicate memory writes.
    """
    def __init__(self):
        self.lanes: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.workers: Dict[str, asyncio.Task] = {}

    async def submit(
        self, 
        session_id: str, 
        func: Callable[..., Coroutine[Any, Any, Any]], 
        *args, 
        **kwargs
    ) -> asyncio.Future:
        """
        Enqueue an async function parameter execution for a specific session.
        Returns a Future that will resolve with the function's result.
        
        Args:
            session_id: The unique identifier for the user's thread/chat.
            func: The async function to execute (e.g., _run_graph).
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        # Enqueue the task
        await self.lanes[session_id].put((func, args, kwargs, future))
        
        # Start a worker for this session if one isn't currently running
        if session_id not in self.workers or self.workers[session_id].done():
            self.workers[session_id] = asyncio.create_task(self._process(session_id))
            
        return future

    async def _process(self, session_id: str):
        """
        Background worker that consumes the queue for a given session.
        Exits when the queue is empty.
        """
        logger.debug(f"🚦 Started LaneManager worker for session: {session_id}")
        
        try:
            while not self.lanes[session_id].empty():
                func, args, kwargs, future = await self.lanes[session_id].get()
                
                try:
                    logger.debug(f"🟢 LaneManager executing task for session: {session_id}")
                    result = await func(*args, **kwargs)
                    if not future.done():
                        future.set_result(result)
                except Exception as e:
                    logger.error(f"❌ LaneManager task error for session {session_id}: {e}", exc_info=True)
                    if not future.done():
                        future.set_exception(e)
                finally:
                    self.lanes[session_id].task_done()
                    
        except asyncio.CancelledError:
            logger.warning(f"⚠️ LaneManager worker cancelled for session: {session_id}")
        finally:
            logger.debug(f"🛑 Stopped LaneManager worker for session: {session_id}")
            # Clean up the worker tracking reference
            if session_id in self.workers:
                del self.workers[session_id]
            # Optionally, we could clean up empty queues to save memory,
            # but defaultdict handles it safely if accessed again.
            if self.lanes[session_id].empty():
                del self.lanes[session_id]

# Singleton instance
lane_manager = LaneManager()
