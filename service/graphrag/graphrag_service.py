import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
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


def ensure_workspace_initialized(root: Path, force: bool = False):
    """Ensure workspace has .env and settings.yaml. If force, re-init with --force."""
    root.mkdir(parents=True, exist_ok=True)
    if force:
        subprocess.run([sys.executable, "-m", "graphrag", "init", "--root", str(root), "--force"], check=True)
        configure_models_gemini(root)
        return
    env_path = root / ".env"
    settings_path = root / "settings.yaml"
    did_init = False
    if not env_path.exists() or not settings_path.exists():
        subprocess.run([sys.executable, "-m", "graphrag", "init", "--root", str(root)], check=True)
        did_init = True
    if did_init:
        configure_models_gemini(root)


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
        "model_supports_json": True,
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


def configure_cache_short_base(root: Path):
    """Use a short absolute cache base_dir to avoid Windows MAX_PATH issues.

    Sets cache.base_dir to a short path under the user's home directory, e.g.
    <home>/.grc/<workspace_name>
    Also pre-creates the cache base and common subfolders used by GraphRAG.
    """
    settings_path = root / "settings.yaml"
    if not settings_path.exists():
        return
    with settings_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # Build short base dir
    base_dir = Path.home() / ".grc" / root.name
    # Use forward slashes to avoid YAML/backslash escape issues
    base_dir_str = base_dir.as_posix()

    cache_cfg = data.get("cache", {})
    cache_cfg["type"] = "file"
    cache_cfg["base_dir"] = base_dir_str
    data["cache"] = cache_cfg

    # Write settings first
    with settings_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    # Pre-create directories to avoid races
    try:
        (base_dir / "extract_noun_phrases").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

def configure_input_for_json(root: Path):
    """Ensure settings.yaml is configured to read JSON files from input/.

    Sets:
      input.storage.type = file
      input.storage.base_dir = "input"
      input.file_type = json
      input.file_pattern = ".*\\.json$"
    """
    settings_path = root / "settings.yaml"
    if not settings_path.exists():
        return
    with settings_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    input_cfg = data.get("input", {})
    storage = input_cfg.get("storage", {})
    storage["type"] = "file"
    storage["base_dir"] = "input"
    input_cfg["storage"] = storage
    input_cfg["file_type"] = "json"
    # Avoid trailing '$' which breaks Python string.Template used by GraphRAG config loader
    input_cfg["file_pattern"] = ".*\\.json"
    # Hint GraphRAG to interpret JSON as the fast 'documents' schema (id, text, title, creation_date, metadata)
    input_cfg["json_schema"] = "documents"
    data["input"] = input_cfg

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

    # Fallback: also export individual .txt files so pipelines configured for text can index
    # Filenames: doc_<seq>_<first8_of_hash>.txt
    for idx, it in enumerate(items):
        fn = f"doc_{idx+1:05d}_{it['id'][:8]}.txt"
        fp = input_dir / fn
        try:
            with fp.open("w", encoding="utf-8") as tf:
                # include title as header to give context
                title_line = it.get("title") or ""
                if title_line:
                    tf.write(f"{title_line}\n\n")
                tf.write(it.get("text", ""))
        except Exception:
            # ignore per-file write errors to keep export robust
            pass
    return len(items)


def run_index(root: Path, method: str = "fast") -> bool:
    cmd = [sys.executable, "-X", "utf8", "-m", "graphrag", "index", "--root", str(root)]
    if method:
        cmd += ["--method", method]
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    cli_log = logs_dir / "cli_index.log"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        with cli_log.open("a", encoding="utf-8") as f:
            f.write("\n==== graphrag index STDOUT ===="\
                    f"\n{proc.stdout}\n")
            f.write("\n==== graphrag index STDERR ===="\
                    f"\n{proc.stderr}\n")
        return True
    except subprocess.CalledProcessError as e:
        with cli_log.open("a", encoding="utf-8") as f:
            f.write("\n==== graphrag index FAILED ===="\
                    f"\nCommand: {' '.join(cmd)}\n"\
                    f"Return code: {e.returncode}\n"\
                    f"STDOUT:\n{e.stdout}\n"\
                    f"STDERR:\n{e.stderr}\n")
        return False


def run_query(
    root: Path,
    method: str,
    query: str,
    community_level: Optional[int] = None,
    response_type: Optional[str] = None,
    timeout_sec: int = 60,
) -> str:
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    cli_log = logs_dir / "cli_query.log"
    cmd = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "graphrag",
        "query",
        "--root",
        str(root),
        "--method",
        method,
        "--query",
        query,
    ]
    if community_level is not None:
        cmd += ["--community-level", str(community_level)]
    if response_type:
        cmd += ["--response-type", response_type]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout_sec,
        )
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        with cli_log.open("a", encoding="utf-8") as f:
            f.write("\n==== graphrag query STDOUT ====\n" + stdout_text + "\n")
            f.write("\n==== graphrag query STDERR ====\n" + stderr_text + "\n")
        return stdout_text.strip()
    except subprocess.TimeoutExpired as e:
        with cli_log.open("a", encoding="utf-8") as f:
            f.write("\n==== graphrag query TIMEOUT ====\n")
            f.write(f"Command: {' '.join(cmd)}\nTimeout: {timeout_sec}s\n")
            if e.output:
                f.write(f"STDOUT (partial):\n{e.output}\n")
            if e.stderr:
                f.write(f"STDERR (partial):\n{e.stderr}\n")
        return ""
    except subprocess.CalledProcessError as e:
        with cli_log.open("a", encoding="utf-8") as f:
            f.write("\n==== graphrag query FAILED ====\n")
            f.write(f"Command: {' '.join(cmd)}\nReturn code: {e.returncode}\n")
            f.write(f"STDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}\n")
        return ""


def _list_parquet_files(output_root: Path) -> List[Path]:
    if not output_root.exists():
        return []
    return [p for p in output_root.rglob("*.parquet") if p.is_file()]


def persist_output_to_db(db: Session, customer_id: str, root: Path, overwrite: bool = True, commit_batch: int = 1000) -> int:
    """Scan workspace/output for parquet artifacts and persist rows to DB.

    Returns number of rows persisted.
    """
    output_dir = root / "output"
    update_output_dir = root / "update_output"

    if overwrite:
        db.query(GraphRAGArtifact).filter(GraphRAGArtifact.customer_id == customer_id).delete(synchronize_session=False)
        db.commit()

    total_rows = 0
    parquet_files = _list_parquet_files(output_dir) + _list_parquet_files(update_output_dir)
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
