import os
import json
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from database.database import Customer, IngestedMessage, PromptVersion, SessionLocal
from service.agents.agent_service import create_agent_executor
import dependencies

# Optional: import agentlightning if available
try:
    import agentlightning as agl
except Exception as e:
    agl = None


def _get_current_custom_prompt(db: Session, customer_id: str) -> str:
    c = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    return c.custom_prompt if c and c.custom_prompt else ""


def _save_new_prompt_version(db: Session, customer_id: str, template: str, algo: str, metrics: Dict):
    # Determine next version
    last = (
        db.query(PromptVersion)
        .filter(PromptVersion.customer_id == customer_id)
        .order_by(PromptVersion.version.desc())
        .first()
    )
    next_ver = 1 if not last else last.version + 1
    pv = PromptVersion(
        customer_id=customer_id,
        version=next_ver,
        template=template,
        algo=algo,
        metrics=json.dumps(metrics or {}),
    )
    db.add(pv)
    # Also update current customer.custom_prompt
    cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if cust:
        cust.custom_prompt = template
    db.commit()
    return pv


def build_dataset_from_ingest(db: Session, customer_id: str) -> List[Dict]:
    # Very simple dataset: Take latest N human messages with optional rating
    rows = (
        db.query(IngestedMessage)
        .filter(IngestedMessage.customer_id == customer_id)
        .order_by(IngestedMessage.timestamp.asc(), IngestedMessage.id.asc())
        .all()
    )
    dataset = []
    thread_histories: Dict[str, List[Dict]] = {}
    for r in rows:
        thread_histories.setdefault(r.external_thread_id, []).append(
            {
                "role": r.role,
                "message": r.content,
                "rating": r.rating,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            }
        )
    for thread_id, msgs in thread_histories.items():
        # Use last human message as a task example
        for i in range(len(msgs)):
            if msgs[i]["role"] == "human":
                history_for_context = [m for m in msgs[max(0, i - 4) : i]]
                dataset.append(
                    {
                        "thread_id": thread_id,
                        "input": msgs[i]["message"],
                        "history": history_for_context,
                        "rating": msgs[i].get("rating"),
                    }
                )
    return dataset


def start_training_for_customer(customer_id: str, llm_provider: Optional[str] = None, api_key: Optional[str] = None):
    db = SessionLocal()
    try:
        # Safety checks
        if agl is None:
            print("[TRAIN] agentlightning is not installed; skip training.")
            return {"status": "skipped", "reason": "agentlightning not installed"}

        # Resolve provider and API key (prefer user-provided over environment)
        resolved_provider = (llm_provider or os.getenv("TRAIN_LLM_PROVIDER") or "openai").strip()
        if resolved_provider == "openai":
            resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")
        elif resolved_provider == "google_genai":
            resolved_api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        else:
            resolved_api_key = api_key or os.getenv("OPENAI_API_KEY")

        if not resolved_api_key:
            print(f"[TRAIN] Missing API key for provider {resolved_provider}; skip training.")
            return {"status": "skipped", "reason": "LLM API key missing"}

        # Build dataset
        dataset = build_dataset_from_ingest(db, customer_id)
        if not dataset:
            print(f"[TRAIN] No ingest data for customer {customer_id}")
            return {"status": "skipped", "reason": "no data"}

        # Prepare initial resource (current prompt)
        current_prompt = _get_current_custom_prompt(db, customer_id)
        initial_resources = {
            "prompt_template": agl.PromptTemplate(template=current_prompt or "You are a helpful assistant.", engine="f-string")
        }

        # Define rollout using function-based API
        @agl.rollout
        def rollout_fn(task: Dict, prompt_template: agl.PromptTemplate) -> float:
            # Render new custom prompt
            new_custom_prompt = prompt_template.format()

            # Load minimal customer_config
            cust = db.query(Customer).filter(Customer.customer_id == customer_id).first()
            if not cust:
                return 0.0
            cust.custom_prompt = new_custom_prompt  # override for this rollout run

            # Build LLM provider from resolved values
            llm_provider_local = resolved_provider
            api_key_local = resolved_api_key

            # Create agent executor (get current ES client)
            agent_exec = create_agent_executor(
                es_client=dependencies.get_es_client(),
                db=db,
                customer_id=customer_id,
                customer_config=cust,
                thread_id=task.get("thread_id"),
                llm_provider=llm_provider_local,
                api_key=api_key_local,
            )

            # Prepare history override
            history_override = [
                {"role": h["role"], "message": h["message"]} for h in task.get("history", [])
            ]

            # Build inputs for async invoke (no DB writes, minimal context)
            from langchain_core.messages import HumanMessage, AIMessage
            chat_history = []
            for h in history_override:
                role = h.get("role")
                msg = h.get("message") or ""
                chat_history.append(HumanMessage(content=msg) if role == "human" else AIMessage(content=msg))

            # Prefer synchronous invoke to avoid event loop issues in background tasks
            result = agent_exec.invoke({
                "input": task.get("input"),
                "chat_history": chat_history,
                "faq_context": [],
                "thread_id": task.get("thread_id") or "train_thread",
            })

            # Simple reward from rating or heuristic length
            rating = task.get("rating")
            if rating is not None:
                return float(rating)
            output = (result or {}).get("output", "") if isinstance(result, dict) else str(result)
            return 1.0 if output and len(output) > 10 else 0.0

        # Configure algorithm (APO) and trainer
        algorithm = agl.algorithms.APO() if hasattr(agl, "algorithms") else agl.APO()
        adapter = agl.TraceToMessages() if hasattr(agl, "TraceToMessages") else None
        trainer = agl.Trainer(
            algorithm=algorithm,
            n_runners=int(os.getenv("TRAIN_N_RUNNERS", "4")),
            initial_resources=initial_resources,
            adapter=adapter,
        )

        # Build minimal datasets for dev/fit
        # For demo: use same dataset; in real use, split train/val
        dev_subset = dataset[: min(10, len(dataset))]

        print(f"[TRAIN] Dev on {len(dev_subset)} samples…")
        trainer.dev(agent=rollout_fn, dev_dataset=dev_subset)

        print(f"[TRAIN] Fit on {len(dataset)} samples…")
        trainer.fit(agent=rollout_fn, train_dataset=dataset)

        # Retrieve best resource and save as new version (stub: reuse initial for now)
        # In a real integration, query LightningStore for the best found prompt
        best_prompt = current_prompt or "You are a helpful assistant."
        metrics = {"note": "stub metrics; integrate real store fetch later"}
        pv = _save_new_prompt_version(db, customer_id, best_prompt, algo="APO", metrics=metrics)

        return {"status": "completed", "version": pv.version}
    finally:
        db.close()
