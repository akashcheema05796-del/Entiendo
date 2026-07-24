# Chunk Ranker — tier2 LLM-judge rubric

Human-authored, AI-refined (SPEC.md §5.2). The AI may propose refinements; a
human owns the intent.

Score each ranking 1–5 on how well the returned chunks answer the query:

- **5** — the single most relevant chunk is ranked first; no irrelevant chunks returned.
- **3** — a relevant chunk is present but not ranked first, or one irrelevant chunk leaked in.
- **1** — no relevant chunk in the returned set.

Judge only the returned set against the query. Do not penalise for candidates
that were never retrieved — that is the vector store's concern, not the ranker's.
