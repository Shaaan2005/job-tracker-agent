# Evaluation Results

- **Model**: `llama3`
- **Evaluated Postings**: 12 (12 synthetic test postings with ground truth hand-labelled)
- **Macro-averaged Precision**: 0.9861
- **Macro-averaged Recall**: 0.9250
- **Average Agent Steps**: 4.0
- **Average JSON Retries**: 0.08
- **Average Latency**: 3.33s

## Per-Posting Performance

| File | Status | Precision | Recall | Steps | Retries | Time (s) |
|------|--------|-----------|--------|-------|---------|----------|
| posting_01.txt | SUCCESS | 1.00 | 0.80 | 4 | 0 | 3.42 |
| posting_02.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.10 |
| posting_03.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 2.95 |
| posting_04.txt | SUCCESS | 0.83 | 1.00 | 4 | 1 | 4.20 |
| posting_05.txt | SUCCESS | 1.00 | 0.75 | 4 | 0 | 3.05 |
| posting_06.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.30 |
| posting_07.txt | SUCCESS | 1.00 | 0.80 | 4 | 0 | 3.50 |
| posting_08.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 2.85 |
| posting_09.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.15 |
| posting_10.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.20 |
| posting_11.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 3.00 |
| posting_12.txt | SUCCESS | 1.00 | 0.75 | 4 | 0 | 3.25 |

## Tool-Call Sequence Distribution

Shows whether the agent follows a fixed sequence or dynamically adapts depending on the input:

| Tool Sequence | Count |
|---|---|
| `extract_posting_fields -> match_skills -> save_application -> finish` | 10 |
| `fetch_posting -> extract_posting_fields -> match_skills -> save_application -> finish` | 2 |
