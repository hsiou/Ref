# pubmed-cli Cookbook

## Baseline Setup

```bash
export NCBI_API_KEY="your-key"
```

## Search -> Fetch -> RIS Pipeline

```bash
pubmed search "fragile x syndrome" --limit 5 --json > search.json
jq -r '.ids[]' search.json | xargs pubmed fetch --json > articles.json
jq -r '.[].pmid' articles.json | tr '\n' ',' | sed 's/,$//' | xargs -I{} pubmed fetch "{}" --ris refs.ris --json > /dev/null
```

## Citation Expansion With RIS

```bash
pubmed cited-by 38000001 --limit 10 --ris cited-by.ris --json > cited-by.json
pubmed references 38000001 --limit 10 --ris references.ris --json > references.json
pubmed related 38000001 --limit 10 --ris related.ris --human > related.txt
```

## MeSH-Assisted Querying

```bash
pubmed mesh "depression" --json > mesh.json
pubmed search '"depressive disorder"[MeSH Terms] AND treatment' --limit 20 --json > depression-search.json
```

## Reference Verification Pipeline (refcheck)

Verify a manuscript's reference list against PubMed and detect fabricated
citations. Requires `docx-review` on PATH (`brew install drpedapati/tools/docx-review`).

```bash
DOC=manuscript.docx
OUT=/tmp/refcheck-$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"

# 1. Quick interactive scan — color-coded verification statuses for the human
pubmed refcheck "$DOC" --human

# 2. Full audit including in-text citation cross-check, JSON for tooling
pubmed refcheck "$DOC" --audit-text --json > "$OUT/report.json"

# 3. Records bundle: the JSON report + a CSV summary + clean RIS of verified refs
pubmed refcheck "$DOC" --audit-text \
  --json \
  --csv-out "$OUT/report.csv" \
  --ris-out "$OUT/verified.ris" \
  > "$OUT/report.json"

# 4. Pull just the references that look fabricated for follow-up
jq '.references[] | select(.status == "POSSIBLY_FABRICATED")' "$OUT/report.json" \
  > "$OUT/fabricated.json"

# 5. Pull the references that PubMed verified but with metadata corrections
jq '.references[] | select(.status == "VERIFIED_WITH_CORRECTION")
  | {original: .raw, corrected: .pubmed_record}' "$OUT/report.json" \
  > "$OUT/corrections.json"
```

Status values to expect in the JSON:

| Status | Meaning |
|---|---|
| `VERIFIED_EXACT` | matches PubMed record exactly |
| `VERIFIED_WITH_CORRECTION` | matched but metadata differs (wrong DOI, year, pages) |
| `VERIFIED_BY_TITLE` | matched on title only, lower confidence |
| `NOT_IN_PUBMED` | no record found |
| `POSSIBLY_FABRICATED` | hallucination signals detected (known author, no matching paper) |

`--audit-text` adds two flags to the report: orphan refs (in the bibliography
but never cited in the body) and orphan in-text citations (cited in the body
but missing from the bibliography). Both appear under `audit.text_audit` in
the JSON.

## Validation Checks (Expected Failures)

```bash
pubmed related 38000001 --limit -1
pubmed search autism --sort newest
pubmed search autism --year 2025-2020
pubmed fetch abc123
pubmed search autism --ris /tmp/search.ris
pubmed mesh depression --ris /tmp/mesh.ris
```

## UX Bundle Pattern (/tmp)

```bash
OUT="/tmp/pubmed-cli-ux-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
go build -o "$OUT/pubmed" ./cmd/pubmed

"$OUT/pubmed" fetch "38000001,38000002" --ris "$OUT/fetch.ris" --json > "$OUT/fetch.json"
"$OUT/pubmed" related 38000001 --limit 5 --ris "$OUT/related.ris" --human > "$OUT/related.txt"
"$OUT/pubmed" cited-by 38000001 --limit 5 --ris "$OUT/cited-by.ris" --json > "$OUT/cited-by.json"

open "$OUT"
```
