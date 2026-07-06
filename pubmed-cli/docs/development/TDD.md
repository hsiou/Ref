# Technical Design Document: pubmed-cli (Main Branch)

Version: 1.1
Date: 2026-02-13

## 1. Scope

`main` is the non-AI production command surface for deterministic PubMed workflows.

Commands:
- `search`
- `fetch`
- `cited-by`
- `references`
- `related`
- `mesh`
- `refcheck`

Out of scope on `main`:
- AI synthesis and QA command paths (maintained separately on `ai-features`).

## 2. Architecture

- `cmd/pubmed`
- CLI wiring, flag validation, command handlers.

- `internal/ncbi`
- Shared HTTP base client.
- NCBI rate limiting.
- Common request parameters (`api_key`, `tool`, `email`).
- Retry/backoff for transient `429` responses.
- Response size limits.

- `internal/eutils`
- PubMed ESearch, EFetch, ELink adapters.

- `internal/mesh`
- MeSH lookup adapter.

- `internal/refcheck`
- Reference verification engine: parse, score, resolve, hallucinate, audit, and report modules.

- `internal/output`
- `json`, `human`, `csv`, and `ris` output paths.

## 3. Reliability Controls

- Context-aware request execution for cancellation.
- Rate-limited outbound calls with API-key-aware limits.
- Guardrails for malformed user input:
  - limit must be positive
  - sort must be valid
  - year format/range validation
  - PMID digit validation
  - RIS export command-scope validation (`fetch` + link commands only)
  - `refcheck` validates input file exists and `docx-review` binary is on PATH
- Tiered PubMed query strategy degrades gracefully through 5 tiers.
- UTF-8 safe truncation in human output mode.
- Defensive handling for empty link/article outputs.

## 4. Data Contracts

- `search --json` returns count, id list, translated query metadata.
- `fetch --json` returns article details including abstracts, authors, MeSH metadata.
- Link commands return source id plus linked pmids (+score for related when available).
- `mesh --json` returns UI, name, scope note, tree numbers, and entry terms.
- `--ris FILE` writes EndNote/Zotero-compatible citation records for `fetch`, `cited-by`, `references`, and `related`.
- `refcheck --json` returns a per-reference verification report with status, optional audit results, CSV and RIS export.

## 5. Testing Strategy

Current gates:
- `go test ./...`
- `go vet ./...`
- real-user command smoke testing before release

High-value tests include:
- concurrent rate-limit behavior
- transient `429` handling
- PMID normalization/validation
- UTF-8-safe human output truncation
- malformed flag rejection
- RIS file output generation and compatibility formatting
- `internal/refcheck` unit tests for parse, score, resolve, hallucinate, audit, and report modules using httptest mock servers

## 6. Operational Risks

- External dependency risk: NCBI availability and policy changes.
- Network variability may still cause user-visible transient failures despite retries.

## 7. Release Criteria

Release only when:
- code quality gates pass
- usability smoke tests pass without panic or silent coercion
- docs are synchronized with actual command behavior
