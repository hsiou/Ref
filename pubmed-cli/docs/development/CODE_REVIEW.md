# Code Review (Production Readiness)

Date: 2026-02-13
Scope: `main` branch, non-AI command set

## Findings First

1. Critical: negative `--limit` could panic link commands
- Area: `cmd/pubmed/main.go`
- Repro: `pubmed related <pmid> --human --limit -1`
- Impact: hard process crash
- Resolution: Added centralized global flag validation and blocked non-positive limits.

2. High: missing guardrails for global flags
- Area: `cmd/pubmed/main.go`
- Impact: unclear runtime behavior for unsupported `--sort` and malformed `--year`
- Resolution: Added strict pre-run validation for `--sort` and `--year`.

3. High: invalid PMID input not rejected at boundary
- Area: `cmd/pubmed/main.go`
- Impact: user error could lead to confusing downstream behavior
- Resolution: Added strict numeric PMID validation and normalization.

4. Medium: UTF-8 unsafe truncation in human output
- Area: `internal/output/human.go`
- Impact: potential broken glyph output on truncation boundaries
- Resolution: Switched to rune-safe truncation logic.

5. High: no native RIS export for reference-manager workflows
- Area: `cmd/pubmed/main.go`, `internal/output`
- Impact: users had no direct EndNote/Zotero import path on `main`
- Resolution: added `--ris FILE` export for `fetch`, `cited-by`, `references`, and `related`, with conservative RIS tags for broad compatibility.

## Verification

- `go test ./...` passed.
- `go vet ./...` passed.
- Manual CLI smoke tests passed across all six commands.

## Residual Risks

- NCBI service-level variability (`429`, transient network errors) still depends on external API behavior; retry logic reduces but cannot remove this class of failure.

## refcheck Subcommand (v0.6.0)

Date: 2026-03-09
Scope: `refcheck` subcommand — reference verification, hallucination detection, and in-text citation audit

### Design Decisions Reviewed

- **Tiered PubMed query strategy (5 tiers) with graceful degradation.** Queries start precise (DOI/PMID lookup) and progressively broaden through title+author, title-only, and fuzzy searches. Each tier short-circuits on a confident match, avoiding unnecessary API calls.
- **Weighted match scoring (DOI/PMID fast-path, title/author/year/journal Jaccard).** Exact DOI or PMID matches bypass scoring entirely. For candidate ranking, Jaccard similarity across title, author list, year, and journal fields produces a composite score with tuned weights.
- **Hallucination detection heuristics (author-exists-but-no-paper, known DOI prefix, recent year).** Flags references where the author publishes in PubMed but no matching paper exists, DOI prefixes belong to known publishers but resolve to nothing, or publication year is suspiciously recent relative to the manuscript.
- **docx-review binary dependency checked at runtime, not build time.** The `refcheck` command shells out to `docx-review` for DOCX reference extraction. Availability is validated at invocation time with a clear error message, keeping the main binary dependency-free.
- **In-text citation audit supports both numbered `[N]` and author-year `(Author, Year)` patterns.** The audit pass detects citation style from the document and cross-references every in-text citation against the parsed reference list, catching orphaned citations and unreferenced bibliography entries.

### Test Coverage

- All 6 modules (`parse`, `score`, `resolve`, `hallucinate`, `audit`, `report`) have unit tests.
- Mock HTTP servers via `httptest` for PubMed API isolation.
- Test manuscript fixture for integration testing.

### Residual Risks

- `docx-review` must be installed separately for `refcheck` to work; the binary is not bundled or fetched automatically.
- Vancouver/APA reference parsing is regex-based; unusual citation formats may not parse correctly.

## Overall Assessment

No remaining code-level blockers identified for production release of the current non-AI `main` branch command surface.
