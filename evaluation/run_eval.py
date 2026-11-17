"""Evaluation harness for job-tracker-agent against real/synthetic postings.

Supports:
  python evaluation/run_eval.py               # runs synthetic set by default
  python evaluation/run_eval.py --set real    # runs real postings set
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agent.agent import run_agent
from app.agent.llm import OllamaLLM
from app.config import settings
from app.db import queries
from app.db.database import Base
from app.services.skills_matcher import normalize_skill


def verify_ollama_reachable(host: str, model: str) -> None:
    """Verify that Ollama is online and responsive. Exits on failure."""
    print(f"Connecting to Ollama at {host}...")
    try:
        resp = httpx.get(f"{host.rstrip('/')}/api/tags", timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        available_models = [m.get("name", "") for m in data.get("models", [])]
        print(f"Ollama is reachable. Available models: {available_models}")
    except Exception as exc:
        print(
            f"\n[FATAL ERROR] Ollama is unreachable at {host}: {exc}\n"
            "Evaluation requires a live Ollama server with the model loaded.\n"
            "Ensure Ollama is running (`ollama serve`) and the model is pulled (`ollama pull <model>`).",
            file=sys.stderr,
        )
        sys.exit(1)


def compute_metrics(
    extracted_skills: list[str], ground_truth: list[str]
) -> tuple[float, float, list[str], list[str], list[str]]:
    """Compute precision, recall, false negatives, and false positives using canonical skill normalization."""
    normalized_extracted = set(normalize_skill(s) for s in extracted_skills)
    normalized_truth = set(normalize_skill(s) for s in ground_truth)

    matched = normalized_extracted.intersection(normalized_truth)
    false_positives = sorted(list(normalized_extracted - normalized_truth))
    false_negatives = sorted(list(normalized_truth - normalized_extracted))

    precision = len(matched) / len(normalized_extracted) if normalized_extracted else 0.0
    recall = len(matched) / len(normalized_truth) if normalized_truth else 0.0

    return (
        round(precision, 4),
        round(recall, 4),
        sorted(list(normalized_extracted)),
        false_negatives,
        false_positives,
    )


async def evaluate_set(dataset_name: str = "synthetic"):
    eval_dir = Path(__file__).resolve().parent

    if dataset_name == "real":
        postings_dir = eval_dir / "real_postings"
        labels_file = eval_dir / "real_labels.json"
        results_json_path = eval_dir / "results_real.json"
        results_md_path = eval_dir / "results_real.md"
        title = "Real Postings Evaluation Results"
    else:
        postings_dir = eval_dir / "postings"
        labels_file = eval_dir / "labels.json"
        results_json_path = eval_dir / "results.json"
        results_md_path = eval_dir / "results.md"
        title = "Evaluation Results"

    if not labels_file.exists():
        print(f"Error: {labels_file} does not exist.", file=sys.stderr)
        sys.exit(1)

    with open(labels_file, "r", encoding="utf-8") as f:
        labels_raw = json.load(f)

    if not labels_raw:
        print(
            f"Error: No postings found in {labels_file}. Please add postings first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 1. Check Ollama
    verify_ollama_reachable(settings.OLLAMA_HOST, settings.OLLAMA_MODEL)

    # 2. Setup isolated in-memory DB for evaluation
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed an evaluation profile with representative skills
    queries.upsert_profile(
        db,
        "Eval Candidate",
        ["python", "docker", "kubernetes", "react", "typescript", "linux", "git", "go"],
    )

    llm = OllamaLLM(model=settings.OLLAMA_MODEL, host=settings.OLLAMA_HOST)

    results_per_posting = []
    tool_sequences = []

    print(
        f"\nStarting evaluation of {len(labels_raw)} postings ({dataset_name} set) with model '{settings.OLLAMA_MODEL}'...\n"
    )

    for filename, raw_entry in labels_raw.items():
        filepath = postings_dir / filename
        if not filepath.exists():
            print(f"Warning: {filepath} missing, skipping.")
            continue

        if isinstance(raw_entry, dict):
            truth_skills = raw_entry.get("required", [])
            alternative_skills = raw_entry.get("alternative", [])
            preferred_skills = raw_entry.get("preferred", [])
            domain_tags = raw_entry.get("domain_tags", [])
        else:
            truth_skills = raw_entry
            alternative_skills = []
            preferred_skills = []
            domain_tags = []

        with open(filepath, "r", encoding="utf-8") as pf:
            content = pf.read()

        start_time = time.perf_counter()
        try:
            app_id, steps = await run_agent(llm=llm, db=db, posting_text=content)
            elapsed = time.perf_counter() - start_time
            app = queries.get_application(db, app_id)
            extracted_raw = app.required_skills if app else []

            # Retrieve persisted run details
            runs = queries.list_agent_runs(db, limit=1)
            json_retries = runs[0].json_retries if runs else 0

            status = "SUCCESS"
        except Exception as exc:
            elapsed = time.perf_counter() - start_time
            extracted_raw = []
            steps = []
            json_retries = 0
            status = f"ERROR: {exc}"

        prec, rec, norm_extracted, fn, fp = compute_metrics(extracted_raw, truth_skills)
        tool_sequence = [s.tool for s in steps]
        sequence_str = " -> ".join(tool_sequence) if tool_sequence else "FAILED"
        tool_sequences.append(sequence_str)

        record = {
            "file": filename,
            "status": status,
            "ground_truth_required": truth_skills,
            "alternative_skills": alternative_skills,
            "preferred_skills": preferred_skills,
            "domain_tags": domain_tags,
            "extracted_raw": extracted_raw,
            "extracted_normalized": norm_extracted,
            "false_negatives": fn,
            "false_positives": fp,
            "precision": prec,
            "recall": rec,
            "steps_count": len(steps),
            "tool_sequence": tool_sequence,
            "json_retries": json_retries,
            "wall_clock_seconds": round(elapsed, 2),
        }
        results_per_posting.append(record)
        print(
            f"[{filename}] Status: {status} | Prec: {prec:.2f} | Rec: {rec:.2f} | "
            f"Steps: {len(steps)} | Retries: {json_retries} | Time: {elapsed:.2f}s | "
            f"FN (missed): {fn} | FP (extra): {fp}"
        )

    # Compute macro-averages
    total_postings = len(results_per_posting)
    if total_postings == 0:
        print("No postings evaluated.")
        return

    macro_precision = sum(r["precision"] for r in results_per_posting) / total_postings
    macro_recall = sum(r["recall"] for r in results_per_posting) / total_postings
    avg_steps = sum(r["steps_count"] for r in results_per_posting) / total_postings
    avg_retries = sum(r["json_retries"] for r in results_per_posting) / total_postings
    avg_time = sum(r["wall_clock_seconds"] for r in results_per_posting) / total_postings

    sequence_distribution = Counter(tool_sequences)

    summary_data = {
        "model": settings.OLLAMA_MODEL,
        "dataset": dataset_name,
        "total_postings": total_postings,
        "macro_precision": round(macro_precision, 4),
        "macro_recall": round(macro_recall, 4),
        "avg_agent_steps": round(avg_steps, 2),
        "avg_json_retries": round(avg_retries, 2),
        "avg_wall_clock_seconds": round(avg_time, 2),
        "tool_sequence_distribution": dict(sequence_distribution),
        "results": results_per_posting,
    }

    # Write results JSON
    with open(results_json_path, "w", encoding="utf-8") as jf:
        json.dump(summary_data, jf, indent=2)
    print(f"\nWrote results to {results_json_path}")

    # Write results Markdown
    md_content = generate_markdown_report(summary_data, title=title)
    with open(results_md_path, "w", encoding="utf-8") as mf:
        mf.write(md_content)
    print(f"Wrote markdown report to {results_md_path}\n")

    # Print summary table
    print("=" * 80)
    print(f"{title.upper()} ({settings.OLLAMA_MODEL})")
    print("=" * 80)
    print(f"Macro Precision : {macro_precision:.4f}")
    print(f"Macro Recall    : {macro_recall:.4f}")
    print(f"Avg Steps       : {avg_steps:.2f}")
    print(f"Avg Retries     : {avg_retries:.2f}")
    print(f"Avg Latency     : {avg_time:.2f}s")
    print("\nTool-Call Sequence Distribution:")
    for seq, count in sequence_distribution.items():
        print(f"  [{count}x] {seq}")
    print("=" * 80)


def generate_markdown_report(data: dict, title: str = "Evaluation Results") -> str:
    """Generate Markdown evaluation report."""
    md = f"""# {title}

- **Model**: `{data['model']}`
- **Dataset**: `{data['dataset']}`
- **Evaluated Postings**: {data['total_postings']}
- **Macro-averaged Precision**: {data['macro_precision']:.4f}
- **Macro-averaged Recall**: {data['macro_recall']:.4f}
- **Average Agent Steps**: {data['avg_agent_steps']}
- **Average JSON Retries**: {data['avg_json_retries']}
- **Average Latency**: {data['avg_wall_clock_seconds']}s

## Per-Posting Performance

| File | Status | Precision | Recall | Steps | Retries | Time (s) | False Negatives (Missed) | False Positives (Extra) |
|------|--------|-----------|--------|-------|---------|----------|--------------------------|-------------------------|
"""
    for r in data["results"]:
        fn_str = ", ".join(r.get("false_negatives", [])) or "None"
        fp_str = ", ".join(r.get("false_positives", [])) or "None"
        md += f"| {r['file']} | {r['status']} | {r['precision']:.2f} | {r['recall']:.2f} | {r['steps_count']} | {r['json_retries']} | {r['wall_clock_seconds']} | {fn_str} | {fp_str} |\n"

    md += "\n## Tool-Call Sequence Distribution\n\n"
    md += "Shows whether the agent follows a fixed sequence or dynamically adapts:\n\n"
    md += "| Tool Sequence | Count |\n|---|---|\n"
    for seq, count in data["tool_sequence_distribution"].items():
        md += f"| `{seq}` | {count} |\n"

    return md


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate job-tracker-agent")
    parser.add_argument(
        "--set",
        choices=["synthetic", "real"],
        default="synthetic",
        help="Evaluation dataset to run (default: synthetic)",
    )
    args = parser.parse_args()
    asyncio.run(evaluate_set(dataset_name=args.set))
