---
name: kb-ingest
description: Add a document, webpage, PDF, or pasted text to the local Knowledge Base at ~/.springo/kb/. Trigger phrases — "add this to KB", "save to knowledge base", "ingest this", "加到知识库", "存入KB", "把这个文档加进知识库", "将这份资料整理成笔记".
triggers: [add to kb, ingest, save to knowledge base, 加到知识库, 存入kb, 整理成笔记, 知识库, 加到 kb]
---

# Add to Knowledge Base

Use this skill whenever the user wants to file new material into their local KB. The KB lives at `~/.springo/kb/` and follows the schema in `~/.springo/kb/CLAUDE.md` (read it first if you haven't this session — it defines the contract).

## The flow at a glance

```
material the user just gave you
        │
        ▼
1. classify the source (text? file? PDF? URL?)
        │
        ▼
2. ingest into raw/ via the right tool
        │
        ▼
3. read the raw content end-to-end (already returned for kb_ingest_pdf)
        │
        ▼
4. decide: update existing wiki page(s) or create new one(s)
        │   prefer updating; only create if topic is genuinely orthogonal
        ▼
5. write the wiki page(s) via kb_write_page
        │
        ▼
6. confirm to user with: pages affected + raw_path + brief summary
```

## Step 1 — Classify the source

| User said | Tool to call |
|----------|--------------|
| Pastes text inline ("here's an article: …") | `kb_ingest_text` |
| Gives a file path (`./report.pdf`, `~/Downloads/x.md`) | `kb_ingest_file`, or `kb_ingest_pdf` if `.pdf` |
| Gives a URL | First fetch with `web_fetch`, then `kb_ingest_text` |
| Says "save this conversation" | Refuse — that's the memory store's job, not KB |

## Step 2 — Always check existing pages BEFORE creating new ones

Call `kb_list` (or `kb_search` for the topic) to see what already exists. If a page covers the topic, update it (read with `kb_read_page`, edit body, write back with `kb_write_page`). Only create a brand-new page when the material is genuinely orthogonal to everything in the wiki.

This is THE most common failure mode: the AI creates 5 new pages from one PDF that should have updated 2 existing pages and created 1 new one.

## Step 3 — Schema is non-negotiable

Every wiki page MUST start with this frontmatter:

```yaml
---
title: <Human-friendly title>
slug: <kebab-case, matches filename>
tags: [tag1, tag2]
sources:
  - type: pdf | webpage | transcript | code | conversation | other
    storage: full | digest-only | external
    file: raw/...               # required if storage=full
    url: ...                    # if applicable
    sha256: ...
    size_bytes: 12345           # never omit
created_at: YYYY-MM-DD
last_updated: YYYY-MM-DD
---
```

And these body sections:
```
## Summary
2–6 sentences plain language.

## Key claims
- Each fact ends with a source pointer. (raw/foo.pdf#p12)

## Open questions
- Things you couldn't resolve.

## See also
- [[other-slug]]
```

**Every claim must end with a source pointer.** No source = remove the claim. This is enforced by lint.

## Step 4 — Storage tier reminder

The store decides tier by file size, not your judgment:

- `< 50 MB`: `kb_ingest_file` will copy automatically
- `50 MB – 1 GB`: tool returns `needs_user_confirmation: true` with a plan; surface to user verbatim, await yes/no, then call again
- `> 1 GB`: tool refuses. Either extract a transcript (with whatever you have available) and call `kb_ingest_text`, OR tell the user this file should live elsewhere and offer `kb_ingest_external` (registers a stub pointing to the external path)

## Step 5 — Confirm to the user

Always end with a short, factual report:

```
Added to KB:
- raw/2026-05-22-fde-report.pdf (4.2 MB, full)
- updated wiki page [[fde-overview]] (+3 claims)
- created wiki page [[fde-compensation-data]]

3 orphan link(s) need targets — run kb_lint to see them.
```

## Examples

### Pasted article

```
User: "Here's an article on FDEs: <pastes 1500 words>. Save it."

You: kb_ingest_text(title="FDE article", content=...)
     → raw/2026-05-22-fde-article.md
     kb_search("FDE")  → existing pages: fde-overview
     kb_read_page("fde-overview")
     kb_write_page("fde-overview", <updated body with new claims>)
     kb_write_page("fde-compensation-data", <new page>) if comp data was orthogonal
```

### PDF on disk

```
User: "Add /Users/me/docs/q3-roadmap.pdf to KB."

You: kb_ingest_pdf(source_path="/Users/me/docs/q3-roadmap.pdf")
     → raw_path + page_count + text_excerpt (already extracted)
     If text_truncated: read_file(raw_path) to get the rest
     kb_search("roadmap")
     kb_write_page(...) ← one or more
```

### Large video (≥ 1 GB)

```
User: "Save this hour-long meeting recording (~ 2 GB) to KB."

You: First, get a transcript (lark-minutes / lark-vc / a Whisper run / etc.)
     Then: kb_ingest_text(title="...meeting transcript", content=transcript,
                          source_url=<original file path or URL>)
     Then write wiki pages from the transcript.

     Don't try kb_ingest_file on the 2 GB video — the tool will refuse.
```

## What NOT to do

- ❌ Create a new wiki page for every chunk of a multi-topic document
- ❌ Skip frontmatter on a wiki page
- ❌ Write a claim without a source pointer
- ❌ Edit anything under `raw/` (only add new files)
- ❌ Try to use embeddings or vector search — KB is plain markdown by design (see CLAUDE.md "Storage substrate")
- ❌ Save a chat session to KB — that's what memory is for
