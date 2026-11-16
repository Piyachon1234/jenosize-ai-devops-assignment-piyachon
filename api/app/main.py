import hashlib
import json
import logging
import os
import signal
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

import numpy as np
import psycopg2
import redis
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": "jenie-api",
            "message": record.getMessage(),
        }
        if hasattr(record, "extra_fields"):
            payload.update(record.extra_fields)
        return json.dumps(payload)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("jenie-api")
logger.setLevel(logging.INFO)
logger.handlers = [handler]

DB_DSN = os.getenv("DATABASE_URL", "postgresql://jenie:jenie_local_pw@postgres:5432/jeniedb")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATA_DIR = os.getenv("DATA_DIR", "/data")
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "60"))
LLM_PROVIDER_FLAG = os.getenv("LLM_PROVIDER_FLAG", "mock-jenie-v1")
COST_PER_1K_TOKENS_USD = float(os.getenv("COST_PER_1K_TOKENS_USD", "0.002"))
EMBED_DIM = 64

HTTP_REQUESTS_TOTAL = Counter(
    "jenie_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
HTTP_ERRORS_TOTAL = Counter(
    "jenie_http_errors_total",
    "Total HTTP 4xx/5xx errors",
    ["endpoint", "status"],
)
HTTP_REQUEST_DURATION = Histogram(
    "jenie_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
RAG_RETRIEVAL_DURATION = Histogram(
    "jenie_rag_retrieval_duration_seconds",
    "Vector DB retrieval latency in seconds",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)
RAG_ANSWER_DURATION = Histogram(
    "jenie_rag_answer_duration_seconds",
    "LLM synthesis latency in seconds",
    ["provider"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
)
LLM_TOKENS_TOTAL = Counter(
    "jenie_llm_tokens_total",
    "Total LLM tokens processed",
    ["provider", "token_type"],
)
LLM_COST_USD_TOTAL = Counter(
    "jenie_llm_estimated_cost_usd_total",
    "Estimated LLM cost in USD",
    ["provider"],
)

KEYWORDS = [
    "vpn", "wireguard", "tunnel", "remote", "network",
    "sso", "mfa", "okta", "password", "login", "auth",
    "incident", "sla", "sev1", "sev2", "mttr", "oncall", "pager",
    "cicd", "github", "trivy", "canary", "rollback", "deploy", "pipeline",
    "rag", "vector", "pgvector", "embedding", "chunk", "retrieval",
    "finops", "cost", "budget", "gpu", "spot", "token", "aws",
    "backup", "dr", "rpo", "rto", "snapshot", "restore", "postgres",
    "kubernetes", "pod", "crashloopbackoff", "oomkilled", "probe", "hpa",
    "secret", "kms", "rotation", "iam", "rbac", "security",
    "ratelimit", "quota", "throttle", "waf", "redis", "cache",
]


def compute_embedding(text: str) -> List[float]:
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    tokens = [t.strip(".,?:!()[]\"'").lower() for t in text.split()]
    for tok in tokens:
        if not tok:
            continue
        for idx, kw in enumerate(KEYWORDS[:EMBED_DIM]):
            if kw in tok or tok in kw:
                vec[idx] += 3.0
        h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % EMBED_DIM] += 0.5
    norm = float(np.linalg.norm(vec))
    vec = vec / norm if norm > 0 else np.eye(1, EMBED_DIM, dtype=np.float32)[0]
    return [round(float(x), 6) for x in vec]


def get_db_conn():
    return psycopg2.connect(DB_DSN)


def get_redis_client():
    return redis.from_url(REDIS_URL, decode_responses=True)


def init_db():
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(72401);")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS kb_documents (
                        id SERIAL PRIMARY KEY,
                        title TEXT UNIQUE NOT NULL,
                        content TEXT NOT NULL,
                        embedding vector({EMBED_DIM}),
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            conn.commit()
    except Exception as exc:
        logger.warning(f"Database initialization deferred: {exc}")


is_shutting_down = False


def handle_sigterm(*args):
    global is_shutting_down
    is_shutting_down = True
    logger.info("SIGTERM received: draining in-flight requests")


signal.signal(signal.SIGTERM, handle_sigterm)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Jenie Helpdesk AI API", extra={"extra_fields": {"provider": LLM_PROVIDER_FLAG}})
    init_db()
    yield
    logger.info("Graceful shutdown complete")


app = FastAPI(title="Jenie Helpdesk AI", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def observability_and_ratelimit_middleware(request: Request, call_next):
    start_time = time.perf_counter()
    path = request.url.path

    if path in ("/ask", "/ingest"):
        try:
            r = get_redis_client()
            client_ip = request.client.host if request.client else "unknown"
            key = f"rl:{client_ip}:{int(time.time() // 60)}"
            current_count = r.incr(key)
            if current_count == 1:
                r.expire(key, 60)
            if current_count > RATE_LIMIT_PER_MIN:
                HTTP_ERRORS_TOTAL.labels(endpoint=path, status="429").inc()
                HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=path, status="429").inc()
                return Response(
                    content=json.dumps({"detail": "Rate limit exceeded"}),
                    status_code=429,
                    media_type="application/json",
                )
        except Exception as exc:
            logger.warning(f"Redis rate-limit check bypassed: {exc}")

    response = await call_next(request)
    duration = time.perf_counter() - start_time
    status_str = str(response.status_code)

    HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=path, status=status_str).inc()
    HTTP_REQUEST_DURATION.labels(endpoint=path).observe(duration)
    if response.status_code >= 400:
        HTTP_ERRORS_TOTAL.labels(endpoint=path, status=status_str).inc()

    logger.info(
        "HTTP request processed",
        extra={
            "extra_fields": {
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "latency_ms": round(duration * 1000, 2),
            }
        },
    )
    return response


class AskRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)


class SourceItem(BaseModel):
    title: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceItem]
    latency_ms: int


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    if is_shutting_down:
        raise HTTPException(status_code=503, detail="shutting down")
    return "ok"


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ingest")
def ingest_docs():
    init_db()
    md_files = sorted(Path(DATA_DIR).glob("*.md"))
    if not md_files:
        raise HTTPException(status_code=404, detail=f"No markdown files found in {DATA_DIR}")

    indexed = 0
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            for file_path in md_files:
                content = file_path.read_text(encoding="utf-8").strip()
                title = file_path.stem
                vec_str = "[" + ",".join(map(str, compute_embedding(title + " " + content))) + "]"
                cur.execute(
                    """
                    INSERT INTO kb_documents (title, content, embedding, updated_at)
                    VALUES (%s, %s, %s::vector, CURRENT_TIMESTAMP)
                    ON CONFLICT (title) DO UPDATE
                    SET content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        updated_at = CURRENT_TIMESTAMP;
                    """,
                    (title, content, vec_str),
                )
                indexed += 1
        conn.commit()

    logger.info("Indexed knowledge base documents", extra={"extra_fields": {"indexed_count": indexed}})
    return {"status": "indexed", "documents_indexed": indexed}


@app.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest):
    total_start = time.perf_counter()
    query_text = payload.query.strip()

    cache_key = "ask_cache:" + hashlib.sha256(f"{LLM_PROVIDER_FLAG}:{query_text.lower()}".encode()).hexdigest()
    try:
        r = get_redis_client()
        cached = r.get(cache_key)
        if cached:
            data = json.loads(cached)
            data["latency_ms"] = max(1, int((time.perf_counter() - total_start) * 1000))
            return data
    except Exception:
        pass

    retr_start = time.perf_counter()
    q_vec_str = "[" + ",".join(map(str, compute_embedding(query_text))) + "]"
    try:
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT title, content, 1 - (embedding <=> %s::vector) AS score
                    FROM kb_documents
                    ORDER BY embedding <=> %s::vector
                    LIMIT 3;
                    """,
                    (q_vec_str, q_vec_str),
                )
                rows = cur.fetchall()
    except Exception as exc:
        logger.error(f"Vector search failed: {exc}")
        raise HTTPException(status_code=500, detail="Vector database query failed")
    retr_duration = time.perf_counter() - retr_start
    RAG_RETRIEVAL_DURATION.observe(retr_duration)

    if not rows:
        raise HTTPException(status_code=404, detail="Knowledge base is empty. Run POST /ingest first.")

    gen_start = time.perf_counter()
    top_title, top_content, _ = rows[0]
    sources = [{"title": r[0], "score": round(max(0.0, min(1.0, float(r[2]))), 2)} for r in rows]

    if LLM_PROVIDER_FLAG == "mock-fast-lite":
        time.sleep(0.015)
        answer = f"[FastLite-RAG] Based on {top_title}: {top_content[:260]}"
    else:
        time.sleep(0.035)
        answer = (
            f"According to Jenosize Helpdesk KB ({top_title}): {top_content} "
            f"(Retrieved {len(sources)} supporting runbooks)."
        )

    gen_duration = time.perf_counter() - gen_start
    RAG_ANSWER_DURATION.labels(provider=LLM_PROVIDER_FLAG).observe(gen_duration)

    prompt_tokens = len(query_text.split()) + sum(len(r[1].split()) for r in rows)
    completion_tokens = len(answer.split())
    total_tokens = prompt_tokens + completion_tokens
    estimated_cost = (total_tokens / 1000.0) * COST_PER_1K_TOKENS_USD

    LLM_TOKENS_TOTAL.labels(provider=LLM_PROVIDER_FLAG, token_type="prompt").inc(prompt_tokens)
    LLM_TOKENS_TOTAL.labels(provider=LLM_PROVIDER_FLAG, token_type="completion").inc(completion_tokens)
    LLM_COST_USD_TOTAL.labels(provider=LLM_PROVIDER_FLAG).inc(estimated_cost)

    total_latency_ms = max(1, int((time.perf_counter() - total_start) * 1000))
    result = {
        "answer": answer,
        "sources": sources,
        "latency_ms": total_latency_ms,
    }

    try:
        r = get_redis_client()
        r.setex(cache_key, 300, json.dumps(result))
    except Exception:
        pass

    logger.info(
        "RAG query answered",
        extra={
            "extra_fields": {
                "query": query_text,
                "top_source": top_title,
                "top_score": sources[0]["score"],
                "retrieval_ms": round(retr_duration * 1000, 2),
                "generation_ms": round(gen_duration * 1000, 2),
                "tokens_used": total_tokens,
                "estimated_cost_usd": round(estimated_cost, 6),
                "provider": LLM_PROVIDER_FLAG,
            }
        },
    )
    return result