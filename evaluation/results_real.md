# Real Postings Evaluation Results

- **Model**: `llama3`
- **Dataset**: `real`
- **Evaluated Postings**: 3
- **Macro-averaged Precision**: 1.0000
- **Macro-averaged Recall**: 1.0000
- **Average Agent Steps**: 4.0
- **Average JSON Retries**: 0.0
- **Average Latency**: 46.11s

## Per-Posting Performance

| File | Status | Precision | Recall | Steps | Retries | Time (s) | False Negatives (Missed) | False Positives (Extra) |
|------|--------|-----------|--------|-------|---------|----------|--------------------------|-------------------------|
| real_01.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 52.48 | None | None |
| real_02.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 48.33 | None | None |
| real_03.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 37.52 | None | None |

## Tool-Call Sequence Distribution

Shows whether the agent follows a fixed sequence or dynamically adapts:

| Tool Sequence | Count |
|---|---|
| `extract_posting_fields -> match_skills -> save_application -> finish` | 3 |
