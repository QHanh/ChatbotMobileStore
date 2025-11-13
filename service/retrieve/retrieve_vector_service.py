import asyncio
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from database.database import SessionLocal, DocumentVector
import os
from google import genai
from google.genai import types
import math

async def retrieve_documents(
    query: str,
    customer_id: str,
    top_k: int = 10,
    alpha: float = 0.7,
) -> List[Dict[str, Any]]:
    """
    Truy xuất tài liệu trong Postgres theo customer_id, dùng Google Embedding để tính tương đồng cosine.
    """
    def _cosine_sim(a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        if len(a) != len(b):
            return 0.0
        dot = 0.0
        na = 0.0
        nb = 0.0
        for x, y in zip(a, b):
            dot += (x or 0.0) * (y or 0.0)
            na += (x or 0.0) ** 2
            nb += (y or 0.0) ** 2
        denom = math.sqrt(na) * math.sqrt(nb)
        return (dot / denom) if denom else 0.0

    try:
        # 1) Tạo embedding cho truy vấn
        query_vector: List[float] = []
        try:
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            gclient = genai.Client(api_key=api_key) if api_key else genai.Client()
            embed_resp = await gclient.aio.models.embed_content(
                model="gemini-embedding-001",
                contents=query,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
            )
            if getattr(embed_resp, "embeddings", None):
                emb0 = embed_resp.embeddings[0]
                query_vector = getattr(emb0, "values", None) or getattr(emb0, "embedding", None) or []
        except Exception as e:
            print(f"[EMBED] Lỗi tạo embedding cho query: {e}")
            query_vector = []

        # 2) Truy vấn trực tiếp trong Postgres bằng pgvector
        db: Session = SessionLocal()
        try:
            if query_vector:
                q = (
                    db.query(DocumentVector.text, DocumentVector.source)
                    .filter(DocumentVector.customer_id == customer_id)
                    .filter(DocumentVector.embedding != None)  # noqa: E711
                    .order_by(DocumentVector.embedding.cosine_distance(query_vector))
                    .limit(max(1, top_k))
                )
                rows = q.all()
                formatted_results = [
                    {"content": r[0], "source": r[1]} for r in rows
                ]
            else:
                # Fallback khi không tạo được embedding truy vấn
                q = (
                    db.query(DocumentVector.text, DocumentVector.source)
                    .filter(DocumentVector.customer_id == customer_id)
                    .order_by(DocumentVector.id.desc())
                    .limit(max(1, top_k))
                )
                rows = q.all()
                formatted_results = [
                    {"content": r[0], "source": r[1]} for r in rows
                ]
        finally:
            db.close()

        if not formatted_results:
            return [{"message": f"Chưa có dữ liệu vector cho khách hàng '{customer_id}'."}]
        print(f"Truy xuất Postgres được {len(formatted_results)} tài liệu cho customer '{customer_id}'.")
        return formatted_results
    except Exception as e:
        print(f"Lỗi khi truy xuất tài liệu từ Postgres: {e}")
        return [{"error": f"Lỗi truy xuất: {e}"}]
