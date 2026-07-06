# Reference Workflow Handoff

## Completed

- Built `pubmed-cli` into `F:\GitHub\01_Projects\Ref\pubmed-cli\bin\pubmed.exe`.
- Wrote Zotero user environment variables for API, library ID, local mode, SQLite path, and Word DLL path.
- Enabled Zotero local API by setting `extensions.zotero.httpServer.localAPI.enabled=true`; original `prefs.js` was backed up with a `codex-backup` suffix.
- Added `ref_workflow.py`, a lightweight PubMed-to-Zotero workflow.
- Added unit tests covering identifier detection, DOI normalization, PubMed-to-Zotero mapping, DOI duplicate detection, Windows-safe JSON output, batch reference extraction, PubMed-only summaries, and PMID fallback duplicate detection.
- Added batch input support for UTF-8 Markdown/text files containing PubMed links or DOIs.
- Added `--pubmed-only` mode so reference authenticity can be checked before Zotero reads/writes.
- Fixed duplicate detection for no-DOI records: empty DOI no longer matches, and PMID is used as a fallback.
- Verified Zotero Web API read access and item template access.
- Verified PubMed DOI lookup and fetch with DOI `10.1038/nature12373`.
- Verified Web API write to Zotero and fixed duplicate detection after a test exposed a real problem.
- Verified Zotero local API now returns local library items.
- Verified `zotero-word-mcp` can insert native citation and bibliography fields into a temporary Word document.
- Verified Zotero Word Refresh resolves placeholders into real citation and bibliography text after local API was enabled.
- Verified the provided manual-reference manuscript copy has 54 Zotero-native fields recognized by the official Word integration DLL.
- Verified the provided no-Zotero-field manuscript copy starts with 0 recognized fields.
- Inserted a Zotero citation and bibliography into a manuscript copy with `zotero-word-mcp`; Zotero Refresh resolved both placeholders.
- Exported the tested manuscript copy to PDF through Word and confirmed the inserted citation text and DOI appear in the visible output.
- Configured `endnote-mcp` with the provided EndNote XML export and PDF directory.
- Indexed 3,568 EndNote references in metadata-only mode; 1,454 records have PDF attachments available for optional full-text indexing.
- Fixed `endnote-mcp` config read/write to use UTF-8 so Windows Chinese paths work.

## Current Known Test Artifacts

- Zotero test items were created with tags `_MCP-test-to-delete`, `codex-workflow-test`, and `codex-manuscript-test`.
- These can be found in Zotero by tag and moved to Trash after inspection.
- Temporary Word smoke-test documents were created under `artifacts/`; this folder is ignored by Git.
- Current manuscript test artifacts:
  - `F:\GitHub\01_Projects\Ref\reference-workflow\artifacts\word\no_refs_working_copy.docx`
  - `F:\GitHub\01_Projects\Ref\reference-workflow\artifacts\word\manual_refs_comparison_copy.docx`
  - `F:\GitHub\01_Projects\Ref\reference-workflow\artifacts\word\no_refs_working_copy.pdf`

## Remaining

- `endnote-mcp` metadata indexing works. PDF full-text indexing was intentionally skipped because the library has 1,486 PDFs and full extraction can take much longer.
- `S_neutrophils.md` contains 8 PubMed URLs that were all verified through PubMed. Two other list entries use PMC/Nature links rather than direct PubMed links, so they are not picked up by the current PubMed-link extractor.
- `zotero-word-mcp` commands should set `PYTHONIOENCODING=utf-8` on Windows; otherwise printing field payloads can fail on GBK console encoding.
- The dedicated DOCX renderer could not run because LibreOffice/`soffice` is not installed or not on PATH. Word's own PDF export was used for visible-output verification.
- EndNote XML contains duplicate DOI records. Use PubMed/Zotero as the authority when deciding what to insert, and treat EndNote as a supplemental search source.

## Useful Local Files

- Workflow repo: `F:\GitHub\01_Projects\Ref\reference-workflow`
- Source task file: `F:\我的坚果云\Writing\wiki\900｜material\Codex_Next.md`
- Test reference list: `F:\我的坚果云\Writing\wiki\200｜科研工作\202｜论文阅读与思考\S_neutrophils.md`
- EndNote XML export: `F:\Download\My_Library_20250814.xml`
- EndNote config: `C:\Users\Administrator\AppData\Roaming\endnote-mcp\config.yaml`
- EndNote database: `C:\Users\Administrator\AppData\Roaming\endnote-mcp\library.db`
- Zotero prefs backup: search for `prefs.js.codex-backup-*` in `C:\Users\Administrator\AppData\Roaming\Zotero\Zotero\Profiles\uza5zk8q.default`

## Latest Verified Commands

```powershell
& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' -m unittest discover -s tests -v

$env:PYTHONIOENCODING='utf-8'
& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' .\ref_workflow.py `
  --from-file 'F:\我的坚果云\Writing\wiki\200｜科研工作\202｜论文阅读与思考\S_neutrophils.md' `
  --pubmed-only --limit 8

& 'C:\ProgramData\anaconda3\envs\hsiou\Scripts\endnote-mcp.exe' status
```
