"""
memory.py — MemoryGate background worker with Zvec and SQLite.

Production Upgrades: Async I/O, context-aware deduplication,
fast SQLite WAL session storage, and semantic retrieval 
using Zvec (in-process vector DB).
"""

import json
import logging
import asyncio
import os
import uuid
import sqlite3
from typing import List, Dict, Any
from pathlib import Path
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
import zvec

logger = logging.getLogger(__name__)

# Paths
MEMORY_DIR = Path(__file__).parent / "data"
ZVEC_PATH = str(MEMORY_DIR / "zvec_index")
ZVEC_SKILLS_PATH = str(MEMORY_DIR / "zvec_skills")
SQLITE_PATH = str(MEMORY_DIR / "agent_session.db")
SKILLS_DIR = Path(__file__).parent / "skills"

MEMORY_DIR.mkdir(parents=True, exist_ok=True)


# ==========================================================
# 1. Extraction Schema & Agent (Gemini)
# ==========================================================

class ExtractedMemory(BaseModel):
    preferences: List[str] = Field(default_factory=list, description="Writing style, tone, format rules.")
    facts: List[str] = Field(default_factory=list, description="Hard facts: names, roles, constraints, locations.")
    corrections: List[str] = Field(default_factory=list, description="Explicit rules where user corrected the AI.")
    obsolete_items: List[str] = Field(default_factory=list, description="Existing memories that are no longer true.")
    important: bool = Field(default=False, description="True ONLY if new, actionable information was discovered.")


EXTRACTION_PROMPT = """You are an advanced memory extraction system. 
Analyze the conversation between the user and the AI.

Your task: Extract NEW, notable, and actionable information about the user.

**Existing Relevant Memory Context (DO NOT EXTRACT AGAIN):**
{existing_memory}

**Rules:**
1. DO NOT extract information that is already in the Existing Memory.
2. If the user contradicts an Existing Memory (e.g., they moved to a new city), extract the new fact AND list the old fact in `obsolete_items`.
3. If the conversation is casual, routine, or contains no new long-term value, set `important=false` and leave lists empty.
4. Keep entries to a single, concise sentence.
"""

memory_agent = Agent("google-gla:gemini-2.5-flash", output_type=ExtractedMemory)

@memory_agent.system_prompt
def build_extraction_prompt(ctx: RunContext[str]) -> str:
    existing_memory = ctx.deps if ctx.deps else "No existing memory."
    return EXTRACTION_PROMPT.format(existing_memory=existing_memory)


# ==========================================================
# 2. DatabaseClient (Fast SQLite WAL)
# ==========================================================

class DatabaseClient:
    """Handles fast, highly-concurrent SQLite storage for history and docs."""

    def __init__(self, db_path: str = SQLITE_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self.initialize()

    def get_fast_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA mmap_size = 3000000000;")
        return conn

    def initialize(self):
        """Create tables if they don't exist."""
        with self.get_fast_connection() as conn:
            # Table for chat history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS thread_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_id ON thread_history(thread_id)")

            # Table for explicit memories (Zvec document store text)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_docs (
                    doc_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_content ON memory_docs(content)")

    async def add_history(self, thread_id: str, role: str, content: str):
        async with self._lock:
            def _insert():
                with self.get_fast_connection() as conn:
                    conn.execute(
                        "INSERT INTO thread_history (thread_id, timestamp, role, content) VALUES (?, ?, ?, ?)",
                        (thread_id, datetime.now(timezone.utc).isoformat(), role, content[:1500])
                    )
            await asyncio.to_thread(_insert)

    async def get_recent_history(self, thread_id: str, limit: int = 10) -> List[Dict]:
        def _fetch():
            with self.get_fast_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT role, content FROM thread_history WHERE thread_id = ? ORDER BY timestamp DESC LIMIT ?",
                    (thread_id, limit)
                )
                rows = [dict(row) for row in cursor.fetchall()]
                return list(reversed(rows))
        return await asyncio.to_thread(_fetch)

    async def get_doc_by_content(self, content: str) -> str | None:
        def _fetch():
            with self.get_fast_connection() as conn:
                cursor = conn.execute("SELECT doc_id FROM memory_docs WHERE content = ?", (content,))
                row = cursor.fetchone()
                return row[0] if row else None
        return await asyncio.to_thread(_fetch)

    async def get_docs_by_ids(self, doc_ids: List[str]) -> List[str]:
        if not doc_ids:
            return []
        
        def _fetch():
            with self.get_fast_connection() as conn:
                placeholders = ",".join("?" * len(doc_ids))
                cursor = conn.execute(f"SELECT content FROM memory_docs WHERE doc_id IN ({placeholders})", doc_ids)
                return [row[0] for row in cursor.fetchall()]
        return await asyncio.to_thread(_fetch)

    async def remove_docs_by_content(self, contents: List[str]) -> List[str]:
        """Returns the doc_ids of the deleted documents."""
        if not contents:
            return []
        removed_ids = []
        async with self._lock:
            def _delete():
                with self.get_fast_connection() as conn:
                    placeholders = ",".join("?" * len(contents))
                    # First fetch the IDs before deleting so we can return them for Zvec
                    cursor = conn.execute(f"SELECT doc_id FROM memory_docs WHERE content IN ({placeholders})", contents)
                    ids = [row[0] for row in cursor.fetchall()]
                    if ids:
                        conn.execute(f"DELETE FROM memory_docs WHERE doc_id IN ({','.join('?' * len(ids))})", ids)
                    return ids
            removed_ids = await asyncio.to_thread(_delete)
        return removed_ids

    async def insert_docs(self, docs: List[Dict[str, str]]):
        if not docs:
            return
        async with self._lock:
            def _insert():
                with self.get_fast_connection() as conn:
                    values = [
                        (doc["doc_id"], doc["content"], datetime.now(timezone.utc).isoformat())
                        for doc in docs
                    ]
                    conn.executemany(
                        "INSERT OR IGNORE INTO memory_docs (doc_id, content, created_at) VALUES (?, ?, ?)",
                        values
                    )
            await asyncio.to_thread(_insert)


from fastembed import TextEmbedding
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

# ==========================================================
# 3. Zvec Vector Store
# ==========================================================

class ZvecMemoryStore:
    """In-process Semantic Memory DB backed by Zvec + SQLite doc store."""

    def __init__(self, db_client: DatabaseClient):
        self.db = db_client
        self.collection = None
        self._needs_rebuild = False  # set True when corruption forces a fresh index

        # FastEmbed Client (Lightweight local BGE model by default)
        self.embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        # bge-small-en-v1.5 embedding dimension is 384
        self.dim = 384

        self.skill_collection = None

    def _wipe_and_recreate(self, path: str, schema: zvec.CollectionSchema):
        """Delete a corrupt Zvec directory and return a fresh collection."""
        import shutil
        logger.warning(f"⚠️  Corrupt Zvec index at {path} — wiping and recreating...")
        shutil.rmtree(path, ignore_errors=True)
        return zvec.create_and_open(path=path, schema=schema)

    def initialize(self):
        """Must be called on startup to open the Zvec indexes."""
        mem_schema = zvec.CollectionSchema(
            name="agent_memory",
            vectors=zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, self.dim),
        )

        # --- Memory index ---
        try:
            self.collection = zvec.open(path=ZVEC_PATH)
            # Probe the collection with a dummy query to expose silent corruption
            self.collection.query(
                zvec.VectorQuery("embedding", vector=[0.0] * self.dim), topk=1
            )
        except Exception as e:
            logger.warning(f"⚠️  zvec_index open/probe failed ({e}), rebuilding from SQLite...")
            self.collection = self._wipe_and_recreate(ZVEC_PATH, mem_schema)
            self._needs_rebuild = True  # will re-embed from SQLite after init

        # --- Skill index ---
        skill_schema = zvec.CollectionSchema(
            name="skill_memory",
            vectors=zvec.VectorSchema("embedding", zvec.DataType.VECTOR_FP32, self.dim),
        )
        try:
            self.skill_collection = zvec.open(path=ZVEC_SKILLS_PATH)
        except Exception as e:
            logger.warning(f"⚠️  zvec_skills open failed ({e}), recreating...")
            self.skill_collection = self._wipe_and_recreate(ZVEC_SKILLS_PATH, skill_schema)

    async def _embed(self, texts: List[str]) -> List[List[float]]:
        """Generate local vector embeddings using FastEmbed."""
        if not texts:
            return []
        
        def _get_embeddings():
            try:
                # FastEmbed returns a generator of numpy arrays, convert to standard lists
                embeddings_generator = self.embedding_model.embed(texts)
                return [emb.tolist() for emb in embeddings_generator]
            except Exception as e:
                logger.error(f"FastEmbed failed: {e}")
                return []
                
        return await asyncio.to_thread(_get_embeddings)

    async def get_relevant_context(self, query: str, top_k: int = 5) -> str:
        """Search Zvec for memories semantically similar to the current query."""
        if not self.collection:
            return ""
            
        vector = (await self._embed([query]))[0]
        
        try:
            results = self.collection.query(
                zvec.VectorQuery("embedding", vector=vector),
                topk=top_k
            )
            
            # Extract doc_ids from Zvec results (results are `Doc` objects which likely have an `.id` property)
            doc_ids = [res.id for res in results]
            
            if not doc_ids:
                return ""
                
            # Retrieve actual text from SQLite
            relevant_texts = await self.db.get_docs_by_ids(doc_ids)
            return "\n".join(f"- {text}" for text in relevant_texts)
            
        except Exception as e:
            logger.error(f"Zvec query failed: {e}")
            return ""

    async def get_relevant_skills(self, query: str, top_k: int = 2) -> str:
        """Search Zvec for skills most relevant to the query to prevent prompt drift."""
        if not self.skill_collection:
            return ""
            
        vector = (await self._embed([query]))[0]
        
        try:
            results = self.skill_collection.query(
                zvec.VectorQuery("embedding", vector=vector),
                topk=top_k * 2 # get more chunks initially to find unique skills
            )
            
            # The .id here is "skill_name::chunk_index"
            # We want unique skill names
            skill_names = []
            for res in results:
                skill_id = res.id.rsplit("_", 1)[0]
                if skill_id not in skill_names:
                    skill_names.append(skill_id)
            
            # We only care about the top_k unique skills
            skill_names = skill_names[:top_k]
            
            if not skill_names:
                return "You are a helpful personal assistant. Be concise and accurate."
                
            prompts = []
            for skill_name in skill_names:
                skill_file = SKILLS_DIR / f"{skill_name}.md"
                if skill_file.exists():
                    content = skill_file.read_text()
                    prompts.append(f"## {skill_name.replace('_', ' ').title()}\n{content}")
                    logger.info(f"  -> Retrieving dynamic skill prompt: {skill_file.name}")
                    
            if not prompts:
                return "You are a helpful personal assistant. Be concise and accurate."
                
            return "\n\n".join(prompts)
            
        except Exception as e:
            logger.error(f"Zvec skills query failed: {e}")
            return "You are a helpful personal assistant. Be concise and accurate."

    async def apply_updates(self, memory: ExtractedMemory):
        """Safely sync SQLite and Zvec."""
        
        # 1. Obsolete Items
        if memory.obsolete_items:
            # Zvec currently operates strictly append-only or whole-collection in early versions, 
            # but if delete is supported, ideally we do it here. 
            # Given that we use SQLite as the text source of truth, removing it from
            # the SQLite DB is safe enough; Zvec will return a dangling ID, 
            # which SQLite get_docs_by_ids() handles safely by ignoring.
            await self.db.remove_docs_by_content(memory.obsolete_items)

        # 2. Ingest New Items
        new_items = memory.preferences + memory.facts + memory.corrections
        if new_items:
            # Dedup slightly via SQLite first
            to_insert = []
            for item in new_items:
                existing_id = await self.db.get_doc_by_content(item)
                if not existing_id:
                    to_insert.append(item)
                    
            if not to_insert:
                return
                
            embeddings = await self._embed(to_insert)
            
            docs_to_db = []
            docs_to_zvec = []
            
            for text, vector in zip(to_insert, embeddings):
                doc_id = f"mem_{uuid.uuid4().hex[:12]}"
                docs_to_db.append({"doc_id": doc_id, "content": text})
                docs_to_zvec.append(zvec.Doc(id=doc_id, vectors={"embedding": vector}))
            
            # Commit to SQLite
            await self.db.insert_docs(docs_to_db)
            
            # Insert into Zvec collection
            if self.collection:
                try:
                    self.collection.insert(docs_to_zvec)
                except Exception as e:
                    logger.error(f"Zvec insert failed: {e}")

    async def rebuild_from_sqlite(self):
        """
        Re-populate zvec_index from the durable SQLite memory_docs table.

        Called after corruption forces a fresh index so no user memory is lost.
        The text lives in SQLite; we just need to re-embed it.
        """
        logger.info("🔄 Rebuilding zvec_index from SQLite memory_docs...")

        def _fetch_all():
            with self.db.get_fast_connection() as conn:
                cursor = conn.execute("SELECT doc_id, content FROM memory_docs")
                return cursor.fetchall()

        rows = await asyncio.to_thread(_fetch_all)

        if not rows:
            logger.info("  -> No existing memory_docs found — fresh start.")
            self._needs_rebuild = False
            return

        doc_ids = [r[0] for r in rows]
        texts   = [r[1] for r in rows]

        embeddings = await self._embed(texts)
        docs_to_zvec = [
            zvec.Doc(id=doc_id, vectors={"embedding": vector})
            for doc_id, vector in zip(doc_ids, embeddings)
        ]

        try:
            self.collection.insert(docs_to_zvec)
            logger.info(f"✅ Rebuilt zvec_index with {len(docs_to_zvec)} memory docs from SQLite")
        except Exception as e:
            logger.error(f"Zvec rebuild insert failed: {e}")

        self._needs_rebuild = False

    async def initialize_skills(self):
        """Called on startup to embed skills/*.md so Zvec can retrieve them."""
        if not SKILLS_DIR.exists() or not self.skill_collection:
            return

        skills_to_embed = []
        skill_ids = []

        # Splitters
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)

        # Load all .md files
        for skill_file in SKILLS_DIR.glob("*.md"):
            skill_id = skill_file.stem  # e.g. "google_workspace"
            content = skill_file.read_text()

            # 1. Split by header
            md_docs = markdown_splitter.split_text(content)

            # 2. Split large chunks recursively
            final_chunks = text_splitter.split_documents(md_docs)

            for i, chunk in enumerate(final_chunks):
                skills_to_embed.append(chunk.page_content)
                skill_ids.append(f"{skill_id}_{i}")

        if not skills_to_embed:
            return

        embeddings = await self._embed(skills_to_embed)

        docs_to_zvec = []
        for s_id, vector in zip(skill_ids, embeddings):
            docs_to_zvec.append(zvec.Doc(id=s_id, vectors={"embedding": vector}))

        try:
            # We rewrite the collection on startup just in case the config changed
            self.skill_collection.insert(docs_to_zvec)
            logger.info(f"✅ Embedded {len(docs_to_zvec)} skills into dynamic Zvec memory")
        except Exception as e:
            logger.error(f"Zvec skills insert failed: {e}")


# ==========================================================
# 4. MemoryGate Interface
# ==========================================================

class MemoryGate:
    """Background semantic extraction and retrieval."""

    def __init__(self):
        self.db = DatabaseClient()
        self.store = ZvecMemoryStore(db_client=self.db)

    async def initialize(self):
        """Must be called at application startup."""
        self.db.initialize()
        self.store.initialize()
        # If corruption was detected, rebuild the vector index from durable SQLite
        if self.store._needs_rebuild:
            await self.store.rebuild_from_sqlite()
        await self.store.initialize_skills()

    async def process(self, thread_id: str, user_input: str, agent_response: str):
        """Background extraction triggered after a turn."""
        logger.info(f"--- [MemoryGate: Processing Thread {thread_id}] ---")
        
        # 1. Fast Wallet-Optimized History Write
        await self.db.add_history(thread_id, "user", user_input)
        await self.db.add_history(thread_id, "assistant", agent_response)

        conversation = f"User: {user_input}\nAssistant: {agent_response}"
        
        # 2. Fetch specific semantic memories related to this turn
        relevant_context = await self.store.get_relevant_context(conversation, top_k=10)

        # 3. Extract structured memories (passing current subset memory as context)
        try:
            result = await memory_agent.run(conversation, deps=relevant_context)
            memory: ExtractedMemory = result.output

            if memory.important:
                await self.store.apply_updates(memory)
                logger.info(f" -> Memory updated: +{len(memory.preferences)}P +{len(memory.facts)}F -{len(memory.obsolete_items)} Obs")
            else:
                logger.info(" -> No notable memory from this turn")

        except Exception as e:
            logger.error(f" -> Memory extraction failed: {e}", exc_info=True)

    async def get_context(self, thread_id: str) -> str:
        """Retrieve relevant context for the agent node before generation."""
        # 1. Fetch recent fast history
        recent_rows = await self.db.get_recent_history(thread_id, limit=6)
        
        parts = []
        if recent_rows:
            history_str = "\n".join(f"- **{row['role'].title()}**: {row['content']}" for row in recent_rows)
            # 2. Grab semantic context based on the user's latest message (or whole recent history)
            latest_user = next((row['content'] for row in reversed(recent_rows) if row['role'] == 'user'), "")
            
            semantic_context = ""
            if latest_user:
                semantic_context = await self.store.get_relevant_context(latest_user, top_k=10)
            
            if semantic_context:
                parts.append("## Semantic Memory Context")
                parts.append(semantic_context)
                
            parts.append("## Recent Conversation History")
            parts.append(history_str)
            
        return "\n".join(parts) if parts else "No established context."

    async def get_relevant_skills(self, user_input: str) -> str:
        """Fetch dynamic skill prompts to inject into system prompt."""
        return await self.store.get_relevant_skills(user_input, top_k=2)


# Singleton
memorygate = MemoryGate()
