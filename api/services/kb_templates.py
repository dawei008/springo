"""
Bootstrap templates for ~/.springo/kb/.

These get written on the first ingest if missing. They are deliberately
verbose — they're the contract the AI reads every time it touches the KB.
Editing the on-disk copies is fine; we don't overwrite an existing file.
"""

CLAUDE_MD = """# Springo Local Knowledge Base

This file is the contract between you (the AI agent) and the user. Every
time the user asks you to ingest a document, answer a question from KB,
or maintain the wiki, follow these rules.

## Three layers, two write zones

```
~/.springo/kb/
  ├─ raw/        # original sources — you may READ, you may NOT edit
  ├─ wiki/       # your structured notes — you write, user audits
  ├─ index.md    # auto-maintained directory of wiki/ — you write
  ├─ log.md      # append-only event log — you write
  ├─ graph.json  # derived view of wiki/ for canvas — you regenerate
  ├─ CLAUDE.md   # this file — never modify
  └─ AGENTS.md   # ingest/query/lint prompt templates — never modify
```

You write to `wiki/`, `index.md`, `log.md`, and `graph.json`. You DO NOT
edit anything under `raw/`. You may add new files to `raw/` only via the
ingest flow described below.

## Storage tiers — by file size

Every source you ingest declares a storage tier. The tier is decided by
file size — not by user preference, not by your judgment.

| Size | Default tier | Behavior |
|------|--------------|----------|
| < 50 MB | `full` | Copy whole file into `raw/` |
| 50 MB – 1 GB | `full`, but ASK first | Show name + size; user confirms. If declined → `digest-only`. |
| > 1 GB | `digest-only` or `external` | NEVER copy original. Extract transcript/text only. |

Hard limits:
- File ≥ 1 GB and not extractable (encrypted binary, raw video without transcript) → REFUSE ingest, create only a stub
- `raw/` total > 5 GB → before next `full` copy, warn the user

Three tiers in detail:

- **`full`** — original file lives in `raw/`. For text + ≤100-page PDF +
  short markdown + small datasets.
- **`digest-only`** — only the extraction (transcript, text-pull) lives
  in `raw/`. Original file is referenced by path/URL but NOT copied.
  Use for audio/video, > 1 GB anything, or when user declines a 50 MB–1 GB copy.
- **`external`** — user explicitly designates an external location
  (NAS, S3, external drive). `raw/` only holds a stub with sha256 +
  external_path.

## Wiki page schema

Every file in `wiki/` is markdown with this exact frontmatter:

```markdown
---
title: <short human title>
slug: <kebab-case, matches filename basename>
tags: [topic1, topic2]
sources:
  - type: pdf | webpage | transcript | code | conversation | other
    storage: full | digest-only | external
    file: raw/...                # required if storage=full
    external_path: ...           # required if storage=external
    url: ...                     # if applicable
    sha256: ...                  # for full or external
    size_bytes: 4283904          # required, never omit
    page_range: 3-7              # optional
created_at: 2025-05-22
last_updated: 2025-05-22
---

## Summary
2–6 sentences. What is this page about. Plain language.

## Key claims
- Each fact ends with an inline source pointer. (raw/foo.pdf#p12)
- Another fact. (https://example.com/article)

## Open questions
- Things you couldn't resolve, or that the user asked but isn't in sources.

## See also
- [[other-page-slug]]
- [[another-page]]
```

Schema rules:
- Every claim in `## Key claims` MUST have a source pointer. No source = no claim.
- Source pointer format: `(raw/path#anchor)` or `(https://...)`. Anchors:
  PDF → `#p12` or `#p12-15`; markdown → `#heading-slug`; code → `#L42-58`.
- `## See also` uses `[[slug]]` Obsidian-style — no `.md` extension.
- If a fact would belong on two pages, write it on the more specific one
  and link from the more general one.

## Operations

### Ingest

1. Stat the source file. Decide tier (size rule, above).
2. For `full`: copy to `raw/<YYYY-MM-DD>-<slug>.<ext>` and record sha256.
   For `digest-only`: extract text/transcript and write that to `raw/`,
   with a `.meta.json` sibling holding original path / size / sha256.
   For `external`: write a stub `.stub.md`.
3. Read the material end-to-end.
4. Decide affected wiki pages:
   - **Prefer updating an existing page** over creating new ones.
   - Create a new page only if topic is genuinely orthogonal.
5. For each page: update per schema. Add new `sources:` entries (don't
   replace existing), append to `## Key claims`, update `## Summary`
   only if the gist changed.
6. Update `index.md`. Regenerate `graph.json`.
7. Append to `log.md`.

### Query

1. `grep` / read `index.md` and matching wiki pages.
2. Read relevant pages **in full** — do not chunk.
3. Cite inline: "X is true [[slug]]". When verifying a claim, follow the
   source pointer back to `raw/` and read that section.
4. If unanswerable from KB, say so. Do NOT invent.

### Lint

A periodic pass that mutates `wiki/` but never `raw/`:

1. **Orphan check** — wiki page with no inbound links → flag.
2. **Dead source check** — `storage: full` source whose file is missing
   → flag. `external` source whose sha256 no longer matches → flag.
3. **Schema drift** — wiki page missing required frontmatter → fix or flag.
4. **Duplicate detection** — pages with > 70 % claim overlap → propose
   merge. Don't auto-merge.
5. **Stale `last_updated`** — pages > 180 days old → verify claims still
   accurate.

Output goes to `log.md`.

## Storage substrate — markdown only

The KB is stored as plain markdown files in `wiki/`. Period.

- Do NOT introduce a graph database (Neo4j, SQLite graph schema, etc.) as
  source of truth. The user must be able to read every fact in a text
  editor.
- `graph.json` and any future index file are DERIVED from the markdown.
  They can be deleted and regenerated at any time. They never store
  anything authoritative that isn't already in a wiki page.
- If you find yourself wanting a database for performance, the answer is
  almost certainly to split a too-large wiki page or reduce total page
  count via lint — not to add infrastructure.
- Escape hatch: if grep + full-page reads become a real bottleneck,
  the next step is SQLite FTS as a *query cache*, not a graph DB.

## Hard rules

- Never edit `raw/` files. Only add new ones via ingest.
- Never delete a wiki page without user confirmation. Lint flags, doesn't delete.
- Every claim must cite a source. No source → remove the claim.
- Don't summarize away the source. The user must always be able to follow
  a source pointer back to the original material.
- Plain markdown only in `wiki/`. No proprietary formats, no binary blobs.
- One topic per page. If a page exceeds ~500 lines or covers multiple
  distinct topics, split it.

## What this is not

- Not a chat history. Sessions live elsewhere.
- Not a memory store. `~/.springo/memory/*.md` already handles personal
  preferences and project context. KB is for *external* documents and
  *researched* topics.
- Not RAG. We don't chunk, embed, or vector-index.
- Not version-controlled by the AI. `git` the kb/ directory yourself if
  you want history. The AI doesn't run git.
"""

AGENTS_MD = """# KB Agent Prompts

Templates for the three KB operations. Customize freely.

## Ingest prompt

```
A new source has just been added: {source_summary}

1. Decide tier (full / digest-only / external) based on size:
   - < 50 MB → full
   - 50 MB – 1 GB → ask user before copying
   - > 1 GB → digest-only or external; never copy original
2. Read the source end-to-end.
3. List existing wiki pages whose topic might overlap (search index.md).
4. Decide: update existing pages, create new pages, or both.
5. Apply changes. Append to log.md. Regenerate graph.json.
```

## Query prompt

```
The user asked: {question}

1. Grep `wiki/` for terms in the question.
2. Read every matching page in full.
3. Answer with inline `[[slug]]` citations.
4. If verifying a specific claim, follow source pointer to raw/.
5. If unanswered: say so. Offer to ingest something.
```

## Lint prompt

```
Run a maintenance pass:

1. Find orphan wiki pages (no inbound links).
2. Verify all storage:full sources still exist on disk.
3. Verify all required frontmatter fields are present.
4. Detect duplicate-claim pairs (>70% overlap).
5. List pages whose last_updated > 180 days.

Write findings to log.md. Do not auto-fix anything that requires user
judgment (delete, merge); flag those for review.
```
"""
