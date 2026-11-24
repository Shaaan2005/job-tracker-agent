# Evaluation Results

- **Model**: `llama3`
- **Dataset**: `synthetic`
- **Evaluated Postings**: 13
- **Macro-averaged Precision**: 0.9130
- **Macro-averaged Recall**: 0.9808
- **Average Agent Steps**: 4.0
- **Average JSON Retries**: 0.15
- **Average Latency**: 21.17s

## Per-Posting Performance

| File | Status | Precision | Recall | Steps | Retries | Time (s) | False Negatives (Missed) | False Positives (Extra) |
|------|--------|-----------|--------|-------|---------|----------|--------------------------|-------------------------|
| elip_posting.txt | SUCCESS | 0.71 | 1.00 | 4 | 0 | 39.96 | None | asyncio, pydantic |
| posting_01.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 14.9 | None | None |
| posting_02.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 14.27 | None | None |
| posting_03.txt | SUCCESS | 0.75 | 0.75 | 4 | 0 | 14.02 | javascript | modern javascript |
| posting_04.txt | SUCCESS | 1.00 | 1.00 | 4 | 1 | 27.89 | None | None |
| posting_05.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 11.31 | None | None |
| posting_06.txt | SUCCESS | 1.00 | 1.00 | 4 | 1 | 26.39 | None | None |
| posting_07.txt | SUCCESS | 0.83 | 1.00 | 4 | 0 | 18.09 | None | shell scripting |
| posting_08.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 20.07 | None | None |
| posting_09.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 19.34 | None | None |
| posting_10.txt | SUCCESS | 0.57 | 1.00 | 4 | 0 | 30.99 | None | ec2, iam, s3 |
| posting_11.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 27.57 | None | None |
| posting_12.txt | SUCCESS | 1.00 | 1.00 | 4 | 0 | 10.45 | None | None |

## Tool-Call Sequence Distribution

Shows whether the agent follows a fixed sequence or dynamically adapts:

| Tool Sequence | Count |
|---|---|
| `extract_posting_fields -> match_skills -> save_application -> finish` | 13 |
