from fastapi import APIRouter, Depends, Header, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional
import os
import hashlib
from datetime import datetime, timezone

from dependencies import get_db
from database.database import IngestedMessage
from service.models.schemas import IngestBatch
from service.training.agl_training import start_training_for_customer

router = APIRouter()


def _require_api_key(x_api_key: Optional[str]):
    expected = os.getenv("INGEST_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid API key")


@router.post("/training/ingest-chat-batch")
def ingest_chat_batch(
    payload: IngestBatch,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
):
    _require_api_key(x_api_key)

    created = 0
    duplicates = 0
    errors = []

    for item in payload.items:
        try:
            content_hash = hashlib.sha256(
                f"{payload.source}|{item.external_message_id}|{item.role}|{item.content}".encode("utf-8")
            ).hexdigest()

            # Try insert; rely on unique constraint (source, external_message_id)
            row = IngestedMessage(
                source=payload.source,
                external_message_id=item.external_message_id,
                external_thread_id=item.external_thread_id,
                customer_id=payload.customer_id,
                role=item.role,
                content=item.content,
                timestamp=datetime.fromisoformat(item.timestamp.replace("Z", "+00:00")) if item.timestamp else None,
                rating=item.rating,
                content_hash=content_hash,
                created_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.commit()
            created += 1
        except IntegrityError as e:
            db.rollback()
            duplicates += 1
        except Exception as e:
            db.rollback()
            errors.append({"external_message_id": item.external_message_id, "error": str(e)})

    status_code = 201 if created > 0 and not errors else 207 if errors else 200
    return {
        "status": "ok" if not errors else "partial",
        "created": created,
        "duplicates": duplicates,
        "errors": errors,
    }


@router.post("/training/start")
def trigger_training(
    customer_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
    x_llm_provider: Optional[str] = Header(default=None, alias="X-LLM-Provider"),
    x_llm_api_key: Optional[str] = Header(default=None, alias="X-LLM-API-Key"),
):
    _require_api_key(x_api_key)

    # Run training asynchronously
    background_tasks.add_task(start_training_for_customer, customer_id, x_llm_provider, x_llm_api_key)
    return {
        "status": "accepted",
        "message": f"Training started for customer {customer_id}",
        "provider": x_llm_provider or "(default)",
    }
