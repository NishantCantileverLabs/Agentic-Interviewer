# /prompts — versioned prompt files

File = source of truth, DB (`prompt_versions`) = runtime record. A sync script (T2)
mirrors these files into `prompt_versions` rows; every LLM call references a
`prompt_version_id` (invariant D7 — the audit trail).

```
conduct/    per-state system prompts for the live interviewer (Haiku-class)
evaluate/   evidence-extraction + scoring prompts (Opus-class, separate lineage)
brief/      decision-brief generation prompts
```

Never inline a prompt string in application code (CLAUDE.md invariant #2).
