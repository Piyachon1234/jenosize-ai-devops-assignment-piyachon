import hashlib
import os
import time
from pathlib import Path
from typing import List

import numpy as np
import psycopg2

DB_DSN = os.getenv("DATABASE_URL", "postgresql://jenie:jenie_local_pw@postgres:5432/jeniedb")
DATA_DIR = os.getenv("DATA_DIR", "/data")
EMBED_DIM = 64

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


def run_indexer():
    md_files = sorted(Path(DATA_DIR).glob("*.md"))
    if not md_files:
        raise RuntimeError(f"No markdown files found in {DATA_DIR}")

    for attempt in range(1, 15):
        try:
            with psycopg2.connect(DB_DSN) as conn:
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
                    indexed = 0
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
            print(f"[Worker] Indexed {indexed} markdown documents into pgvector.", flush=True)
            return
        except Exception as exc:
            print(f"[Worker] Waiting for PostgreSQL readiness (attempt {attempt}/15): {exc}", flush=True)
            time.sleep(2)
    raise RuntimeError("Worker failed to index documents after 15 attempts")


if __name__ == "__main__":
    run_indexer()