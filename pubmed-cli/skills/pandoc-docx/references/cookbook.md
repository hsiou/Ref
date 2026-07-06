# pandoc-docx cookbook

Copy-paste recipes. All assume the skill lives at `~/.codex/skills/pandoc-docx/` (set up by the IRL workspace template). Replace that path if invoking from elsewhere.

```bash
NIH_REF=~/.codex/skills/pandoc-docx/assets/nih-reference.docx
```

## 1. NIH Specific Aims page

```bash
cat > specific-aims.md <<'MD'
# Specific Aims

Fragile X Syndrome (FXS) is the most common inherited cause of intellectual
disability and autism, affecting ~1 in 4,000 males. Despite progress in
identifying the genetic basis (silencing of the *FMR1* gene), there are no
approved treatments and no validated objective biomarkers. The long-term
goal of this research program is to identify and validate
electrophysiological biomarkers that can serve as proxy outcomes in
clinical trials of disease-modifying therapies.

## Aim 1. Characterize EEG biomarkers in FXS

Hypothesis: Resting-state EEG in FXS shows elevated gamma-band power and
reduced alpha-band peak frequency relative to controls.

## Aim 2. Test target engagement of mGluR5 modulators

Hypothesis: Acute administration of mavoglurant normalizes the EEG
biomarker profile in adult males with FXS.

## Aim 3. Establish test-retest reliability

Hypothesis: The EEG biomarker profile shows ICC > 0.8 across two sessions
within a 30-day window.
MD

pandoc specific-aims.md --reference-doc="$NIH_REF" -o specific-aims.docx
```

## 2. Manuscript draft

```bash
pandoc manuscript.md \
  --reference-doc="$NIH_REF" \
  --toc \
  --number-sections \
  -o manuscript.docx
```

## 3. Manuscript with formatted bibliography (CSL JSON or BibTeX)

```bash
# Using BibTeX + AMA style
pandoc manuscript.md \
  --reference-doc="$NIH_REF" \
  --citeproc \
  --bibliography=refs.bib \
  --csl=american-medical-association.csl \
  -o manuscript.docx

# Using CSL JSON (e.g., exported from Zotero)
pandoc manuscript.md \
  --reference-doc="$NIH_REF" \
  --citeproc \
  --bibliography=refs.json \
  --csl=apa.csl \
  -o manuscript.docx
```

## 4. Abstract (single block, 250-word limit)

```bash
cat > abstract.md <<'MD'
# Abstract

Fragile X Syndrome (FXS) is associated with intellectual disability and
autism. We recorded resting-state EEG from 80 individuals with FXS and 80
matched controls. FXS participants showed significantly elevated gamma
power (40–80 Hz; p < 0.001) and reduced individual alpha peak frequency
(p = 0.003). Both metrics showed test-retest reliability (ICC > 0.8) over
30 days. These findings support the use of EEG metrics as objective,
reliable, mechanism-relevant biomarkers in FXS clinical trials.
MD

pandoc abstract.md --reference-doc="$NIH_REF" -o abstract.docx

# Verify word count is under the limit
wc -w abstract.md
```

## 5. Combine many markdown files into one .docx

```bash
pandoc \
  cover-page.md \
  abstract.md \
  specific-aims.md \
  research-strategy.md \
  bibliography.md \
  --reference-doc="$NIH_REF" \
  --toc \
  -o full-application.docx
```

## 6. Generate from a template-driven research output

```bash
# Output of cliproxy's research pipeline often emits a markdown file —
# convert it to NIH-formatted docx with one command:
pandoc research-output.md \
  --reference-doc="$NIH_REF" \
  -o research-output.docx
```

## 7. Override the template (journal-specific)

When a user explicitly passes a different `--reference-doc`, **do not** apply NIH on top:

```bash
# User wants Cell submission template:
pandoc manuscript.md \
  --reference-doc=cell-template.docx \
  -o manuscript.docx
```

## 8. Verify the template applied correctly

```bash
# Quick sanity check — first page header should be Arial.
unzip -p manuscript.docx word/styles.xml | \
  grep -oE 'w:val="(Arial|Calibri|Times New Roman)"' | \
  sort -u | head -3
# Expect: w:val="Arial"
```
