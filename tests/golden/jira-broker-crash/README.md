# Golden Capture: jira-broker-crash

Mission type: Jira ticket — Kafka broker crash
Trigger: Jira poller picking up ticket with `broker crash` in title/description

## Expected structure

```text
jira-broker-crash/
├── README.md              ← this file
├── prompts.json           ← [{agent: str, prompt_text: str}, ...]
├── tool_calls.json        ← [{agent: str, tool_name: str, params: dict, result: any}, ...]
├── audit.kafka_strimzi_expert.jsonl   ← one JSON object per line
├── audit.k8s_gcp_sre.jsonl
├── audit.prom_alerts_triage.jsonl
├── BRIEF.md               ← final mission report (text may vary across LLM runs)
└── kb_card.json           ← KB card produced for this incident
```

## Diff rules (check_regression.py)

| File | Diff type | Notes |
|------|-----------|-------|
| `prompts.json` | Structural (keys + types) | Exact structure, LLM text may vary |
| `tool_calls.json` | Structural (keys + types) | tool_name and params shape must match |
| `audit.*.jsonl` | Exact on non-LLM fields | Check: timestamp present, tool_name, mission_id |
| `kb_card.json` | Structural (keys + types) | Content may vary |
| `BRIEF.md` | Manual semantic diff | Text varies — human review required |

## How to capture

1. Start platform: `make dev`
2. Create or simulate a Jira ticket with title containing "broker crash"
3. Wait for the Jira poller to pick it up and complete the mission
4. Copy artifacts from `agent-outputs/<mission_id>/` to this directory
5. Copy `audit.*.jsonl` files from the mission output path
