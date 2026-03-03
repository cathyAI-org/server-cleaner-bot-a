"""Memory/RAG service for event storage and retrieval."""
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

app = FastAPI(title="catcord-memory", version="1.0.0")

DB_PATH = Path("/state/db.sqlite3")


class IngestRequest(BaseModel):
    """Event ingest request."""
    source: str = Field(..., description="Event source (matrix, chainlit, bot)")
    external_user_id: str = Field(..., description="External user ID")
    person_id: Optional[str] = Field(None, description="Resolved person ID")
    room_id: Optional[str] = Field(None, description="Room/session ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    char_id: Optional[str] = Field(None, description="Character ID")
    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    ts: str = Field(..., description="ISO timestamp")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Extra metadata")


class IngestResponse(BaseModel):
    """Event ingest response."""
    event_id: int
    person_id: Optional[str]


class QueryRequest(BaseModel):
    """Memory query request."""
    person_id: Optional[str] = Field(None, description="Filter by person")
    char_id: Optional[str] = Field(None, description="Filter by character")
    query: Optional[str] = Field(None, description="Search query (future: vector)")
    k: int = Field(10, description="Number of results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters")


class QueryResponse(BaseModel):
    """Memory query response."""
    results: List[Dict[str, Any]]


def init_db():
    """Initialize memory database.
    
    :return: None
    :rtype: None
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            external_user_id TEXT NOT NULL,
            person_id TEXT,
            room_id TEXT,
            session_id TEXT,
            char_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            ts TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_person_id ON events(person_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_char_id ON events(char_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ts ON events(ts)
    """)
    conn.commit()
    conn.close()


@app.on_event("startup")
async def startup():
    """Initialize service on startup.
    
    :return: None
    :rtype: None
    """
    init_db()
    print("Memory service started")


@app.get("/health")
async def health():
    """Health check endpoint.
    
    :return: Health status
    :rtype: Dict[str, str]
    """
    return {"status": "ok"}


@app.post("/v1/events/ingest", response_model=IngestResponse)
async def ingest_event(req: IngestRequest):
    """Ingest event into memory store.
    
    :param req: Ingest request
    :type req: IngestRequest
    :return: Ingest response
    :rtype: IngestResponse
    """
    
    import json
    
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute("""
            INSERT INTO events
            (source, external_user_id, person_id, room_id, session_id, char_id,
             role, content, ts, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            req.source,
            req.external_user_id,
            req.person_id,
            req.room_id,
            req.session_id,
            req.char_id,
            req.role,
            req.content,
            req.ts,
            json.dumps(req.metadata) if req.metadata else None,
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        event_id = cursor.lastrowid
    finally:
        conn.close()
    
    return IngestResponse(event_id=event_id, person_id=req.person_id)


@app.post("/v1/memory/query", response_model=QueryResponse)
async def query_memory(req: QueryRequest):
    """Query memory store.
    
    :param req: Query request
    :type req: QueryRequest
    :return: Query response
    :rtype: QueryResponse
    """
    
    import json
    
    conn = sqlite3.connect(DB_PATH)
    try:
        where_clauses = []
        params = []
        
        if req.person_id:
            where_clauses.append("person_id = ?")
            params.append(req.person_id)
        
        if req.char_id:
            where_clauses.append("char_id = ?")
            params.append(req.char_id)
        
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        cursor = conn.execute(f"""
            SELECT id, source, external_user_id, person_id, room_id, session_id,
                   char_id, role, content, ts, metadata
            FROM events
            WHERE {where_sql}
            ORDER BY ts DESC
            LIMIT ?
        """, params + [req.k])
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "source": row[1],
                "external_user_id": row[2],
                "person_id": row[3],
                "room_id": row[4],
                "session_id": row[5],
                "char_id": row[6],
                "role": row[7],
                "content": row[8],
                "ts": row[9],
                "metadata": json.loads(row[10]) if row[10] else None,
            })
    finally:
        conn.close()
    
    return QueryResponse(results=results)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090)
