import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from database.database import Document
from database.database import GraphRAGArtifact
from service.utils.helpers import sanitize_for_weaviate
import pandas as pd
import yaml


def workspaces_root() -> Path:
    root = os.getenv("GRAPHRAG_WORKSPACES_ROOT", os.path.join("data", "graphrag"))
    return Path(root)


def workspace_path_for_customer(customer_id: str) -> Path:
    tenant = sanitize_for_weaviate(customer_id) or customer_id
    return workspaces_root() / tenant


def ensure_workspace_initialized(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    env_path = root / ".env"
    settings_path = root / "settings.yaml"
    if not env_path.exists() or not settings_path.exists():
        subprocess.run([sys.executable, "-m", "graphrag", "init", "--root", str(root)], check=True)


def ensure_workspace_initialized(root: Path, force: bool = False):
    """Ensure workspace has .env and settings.yaml. If force, re-init with --force."""
    root.mkdir(parents=True, exist_ok=True)
    if force:
        subprocess.run([sys.executable, "-m", "graphrag", "init", "--root", str(root), "--force"], check=True)
        return
    env_path = root / ".env"
    settings_path = root / "settings.yaml"
    if not env_path.exists() or not settings_path.exists():
        subprocess.run([sys.executable, "-m", "graphrag", "init", "--root", str(root)], check=True)


def upsert_env_api_key(root: Path, api_key: str, env_key: str = "GRAPHRAG_API_KEY"):
    env_path = root / ".env"
    lines = []
    if env_path.exists():
        with env_path.open("r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    found = False
    for i, l in enumerate(lines):
        if l.startswith(f"{env_key}="):
            lines[i] = f"{env_key}={api_key}"
            found = True
            break
    if not found:
        lines.append(f"{env_key}={api_key}")
    with env_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def configure_models_gemini(root: Path, chat_model: str = "gemini-2.5-flash-lite", embedding_model: str = "gemini-embedding-001"):
    """Modify settings.yaml to use LiteLLM with Gemini for chat and embeddings."""
    settings_path = root / "settings.yaml"
    if not settings_path.exists():
        return
    with settings_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    models = data.get("models", {})
    models["default_chat_model"] = {
        "type": "chat",
        "auth_type": "api_key",
        "api_key": "${GEMINI_API_KEY}",
        "model_provider": "gemini",
        "model": chat_model,
    }
    models["default_embedding_model"] = {
        "type": "embedding",
        "auth_type": "api_key",
        "api_key": "${GEMINI_API_KEY}",
        "model_provider": "gemini",
        "model": embedding_model,
    }
    data["models"] = models

    with settings_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def export_documents(db: Session, customer_id: str, root: Path) -> int:
    input_dir = root / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    docs = db.query(Document).filter(Document.customer_id == customer_id).all()
    items: List[Dict] = []
    for d in docs:
        text = d.full_content or ""
        if not text and d.file_content and d.content_type and d.content_type.startswith("text"):
            try:
                text = d.file_content.decode("utf-8", errors="ignore")
            except Exception:
                text = ""
        if not text:
            continue
        doc_id = hashlib.sha256(text.encode("utf-8")).hexdigest()
        title = d.source_name or d.file_name or "Untitled"
        created = d.created_at.isoformat() if getattr(d, "created_at", None) else datetime.now(timezone.utc).isoformat()
        metadata = {}
        if d.file_name:
            metadata["file_name"] = d.file_name
        if d.content_type:
            metadata["content_type"] = d.content_type
        items.append({
            "id": doc_id,
            "text": text,
            "title": title,
            "creation_date": created,
            "metadata": metadata,
        })
    out_path = input_dir / "documents.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    return len(items)


def run_index(root: Path, method: str = "fast"):
    cmd = [sys.executable, "-m", "graphrag", "index", "--root", str(root)]
    if method and method.lower() == "fast":
        cmd += ["--method", "fast"]
    subprocess.run(cmd, check=True)


def _list_parquet_files(output_root: Path) -> List[Path]:
    if not output_root.exists():
        return []
    return [p for p in output_root.rglob("*.parquet") if p.is_file()]


def persist_output_to_db(db: Session, customer_id: str, root: Path, overwrite: bool = True, commit_batch: int = 1000) -> int:
    """Scan workspace/output for parquet artifacts and persist rows to DB.

    Returns number of rows persisted.
    """
    output_dir = root / "output"

    if overwrite:
        db.query(GraphRAGArtifact).filter(GraphRAGArtifact.customer_id == customer_id).delete(synchronize_session=False)
        db.commit()

    total_rows = 0
    parquet_files = _list_parquet_files(output_dir)
    for pf in parquet_files:
        try:
            df = pd.read_parquet(pf)
        except Exception:
            continue
        artifact_type = pf.stem
        recs = df.to_dict(orient="records")
        batch = []
        for r in recs:
            row_id = str(r.get("id") or r.get("_id") or r.get("node_id") or "")
            payload = json.dumps(r, ensure_ascii=False, default=str)
            art = GraphRAGArtifact(
                customer_id=customer_id,
                artifact_type=artifact_type,
                row_id=row_id,
                payload=payload,
            )
            batch.append(art)
            if len(batch) >= commit_batch:
                db.add_all(batch)
                db.commit()
                total_rows += len(batch)
                batch.clear()
        if batch:
            db.add_all(batch)
            db.commit()
            total_rows += len(batch)

    return total_rows
