import os
import sys
import argparse
from pathlib import Path
from typing import Optional, List
from sqlalchemy.orm import Session

# Ensure project root is on sys.path so `database` package is importable regardless of CWD
CURRENT_FILE = Path(__file__).resolve()
PROJECT_ROOT = CURRENT_FILE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.database import SessionLocal, init_db, Document, DocumentVector
from google import genai
from google.genai import types


def _extract_text(doc: Document) -> str:
    if doc.full_content and doc.full_content.strip():
        return doc.full_content
    if doc.file_content and doc.content_type and str(doc.content_type).startswith("text"):
        try:
            return doc.file_content.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return ""


def _embed_text(client: genai.Client, text: str) -> List[float]:
    if not text:
        return []
    try:
        resp = client.models.embed_content(
            model="gemini-embedding-001",
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        if getattr(resp, "embeddings", None):
            emb0 = resp.embeddings[0]
            return getattr(emb0, "values", None) or getattr(emb0, "embedding", None) or []
    except Exception as e:
        print(f"[EMBED] Lỗi khi tạo embedding: {e}")
    return []


def migrate(customer_id: Optional[str] = None, overwrite: bool = False, batch_commit: int = 100) -> int:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key) if api_key else genai.Client()

    init_db()
    db: Session = SessionLocal()
    total = 0
    try:
        q = db.query(Document)
        if customer_id:
            q = q.filter(Document.customer_id == customer_id)
        docs = q.order_by(Document.id.asc()).all()

        if overwrite and customer_id:
            db.query(DocumentVector).filter(DocumentVector.customer_id == customer_id).delete(synchronize_session=False)
            db.commit()
        elif overwrite and not customer_id:
            db.query(DocumentVector).delete(synchronize_session=False)
            db.commit()

        existing_map = {}
        if customer_id:
            existing = (
                db.query(DocumentVector.document_id)
                .filter(DocumentVector.customer_id == customer_id)
                .all()
            )
        else:
            existing = db.query(DocumentVector.document_id).all()
        for (doc_id,) in existing:
            existing_map[doc_id] = True

        batch = []
        for d in docs:
            text = _extract_text(d)
            if not text:
                continue
            if not overwrite and d.id in existing_map:
                continue
            emb = _embed_text(client, text)
            vec = DocumentVector(
                customer_id=d.customer_id,
                document_id=d.id,
                source=d.source_name,
                text=text,
                embedding=emb,
            )
            batch.append(vec)
            if len(batch) >= batch_commit:
                db.add_all(batch)
                db.commit()
                total += len(batch)
                batch.clear()
                print(f"[MIGRATE] Đã chèn {total} vectors...")
        if batch:
            db.add_all(batch)
            db.commit()
            total += len(batch)
            print(f"[MIGRATE] Đã chèn {total} vectors (hoàn tất batch cuối).")
        return total
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Documents to DocumentVector with Google embeddings")
    parser.add_argument("--customer_id", type=str, default=None, help="Chỉ migrate cho 1 customer cụ thể")
    parser.add_argument("--overwrite", action="store_true", help="Xóa vector cũ và ghi lại")
    parser.add_argument("--batch", type=int, default=100, help="Số bản ghi commit mỗi batch")
    args = parser.parse_args()

    total = migrate(customer_id=args.customer_id, overwrite=args.overwrite, batch_commit=args.batch)
    print(f"[DONE] Tổng số vectors đã chèn/cập nhật: {total}")
