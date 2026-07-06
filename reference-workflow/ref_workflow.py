from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_PUBMED_BIN = Path(r"F:\GitHub\01_Projects\Ref\pubmed-cli\bin\pubmed.exe")
ZOTERO_API_BASE = "https://api.zotero.org"
PUBMED_LINK_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", re.IGNORECASE)
DOI_RE = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*)?(10\.\d{4,9}/[^\s\]\)\"<>]+)",
    re.IGNORECASE,
)


def normalize_doi(value: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^doi:\s*", "", text, flags=re.IGNORECASE)
    match = re.search(r"(10\.\d{4,9}/\S+)", text, flags=re.IGNORECASE)
    if not match:
        return text.lower()
    return match.group(1).rstrip(".,;").lower()


def detect_identifier(value: str) -> tuple[str, str]:
    text = (value or "").strip()
    if re.fullmatch(r"\d+", text):
        return "pmid", text
    doi = normalize_doi(text)
    if doi.startswith("10."):
        return "doi", doi
    return "query", text


def extract_identifiers_from_text(text: str) -> list[str]:
    seen = set()
    identifiers: list[str] = []

    def add(value: str) -> None:
        kind, normalized = detect_identifier(value)
        key = (kind, normalized)
        if normalized and key not in seen:
            seen.add(key)
            identifiers.append(normalized)

    for match in PUBMED_LINK_RE.finditer(text or ""):
        add(match.group(1))
    for match in DOI_RE.finditer(text or ""):
        add(match.group(1))
    return identifiers


def pubmed_article_summary(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "verified": True,
        "pmid": article.get("pmid") or "",
        "doi": normalize_doi(article.get("doi") or ""),
        "title": article.get("title") or "",
        "year": article.get("year") or "",
        "journal": article.get("journal") or "",
    }


def article_to_zotero_item(
    template: dict[str, Any],
    article: dict[str, Any],
    *,
    tags: list[str] | None = None,
    collection_keys: list[str] | None = None,
) -> dict[str, Any]:
    item = copy.deepcopy(template)
    item["itemType"] = "journalArticle"
    item["title"] = article.get("title") or ""
    item["abstractNote"] = article.get("abstract") or ""
    item["publicationTitle"] = article.get("journal") or ""
    item["volume"] = article.get("volume") or ""
    item["issue"] = article.get("issue") or ""
    item["pages"] = article.get("pages") or ""
    item["date"] = " ".join(p for p in [article.get("year"), article.get("month")] if p)
    item["DOI"] = normalize_doi(article.get("doi") or "")
    if article.get("pmid"):
        item["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{article['pmid']}/"

    creators = []
    for author in article.get("authors") or []:
        last_name = author.get("last_name") or author.get("lastName") or ""
        first_name = author.get("fore_name") or author.get("firstName") or author.get("initials") or ""
        if last_name or first_name:
            creators.append(
                {
                    "creatorType": "author",
                    "firstName": first_name,
                    "lastName": last_name,
                }
            )
    item["creators"] = creators

    extra_lines = []
    if article.get("pmid"):
        extra_lines.append(f"PMID: {article['pmid']}")
    if article.get("pmcid"):
        extra_lines.append(f"PMCID: {article['pmcid']}")
    item["extra"] = "\n".join(extra_lines)
    item["tags"] = [{"tag": tag} for tag in (tags or []) if tag]
    item["collections"] = collection_keys or []
    return item


def run_pubmed(args: list[str], pubmed_bin: Path = DEFAULT_PUBMED_BIN) -> Any:
    completed = subprocess.run(
        [str(pubmed_bin), *args, "--json"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def fetch_pubmed_article(identifier: str, pubmed_bin: Path = DEFAULT_PUBMED_BIN) -> dict[str, Any]:
    kind, value = detect_identifier(identifier)
    if kind == "pmid":
        articles = run_pubmed(["fetch", value], pubmed_bin)
    else:
        query = f"{value}[DOI]" if kind == "doi" else value
        search = run_pubmed(["search", query, "--limit", "1"], pubmed_bin)
        ids = search.get("ids") or []
        if not ids:
            raise RuntimeError(f"PubMed did not find a match for: {identifier}")
        articles = run_pubmed(["fetch", ids[0]], pubmed_bin)
    if not articles:
        raise RuntimeError(f"PubMed returned no article for: {identifier}")
    return articles[0]


def zotero_request(
    method: str,
    path: str,
    *,
    api_key: str,
    body: Any | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, str], Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        ZOTERO_API_BASE + path,
        data=data,
        method=method,
        headers={
            "Zotero-API-Key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw) if raw else None
            return response.status, dict(response.headers), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            payload = raw
        raise RuntimeError(f"Zotero API {method} {path} failed: HTTP {exc.code}: {payload}") from exc


def get_zotero_template(api_key: str) -> dict[str, Any]:
    _, _, payload = zotero_request("GET", "/items/new?itemType=journalArticle", api_key=api_key)
    return payload


def find_item_in_payload_by_doi(payload: list[dict[str, Any]], doi: str) -> dict[str, Any] | None:
    target = normalize_doi(doi)
    if not target:
        return None
    for item in payload or []:
        data = item.get("data", {})
        item_doi = normalize_doi(data.get("DOI", ""))
        if item_doi and item_doi == target:
            return item
    return None


def find_item_in_payload_by_pmid(payload: list[dict[str, Any]], pmid: str) -> dict[str, Any] | None:
    target = (pmid or "").strip()
    if not target:
        return None
    pattern = re.compile(rf"(^|\n)\s*PMID:\s*{re.escape(target)}\b", re.IGNORECASE)
    for item in payload or []:
        data = item.get("data", {})
        if str(data.get("PMID", "")).strip() == target:
            return item
        if pattern.search(str(data.get("extra", ""))):
            return item
    return None


def _find_existing_zotero_item(
    api_key: str,
    library_id: str,
    query_value: str,
    matcher,
) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"q": query_value, "qmode": "everything", "limit": "10", "format": "json"})
    _, _, payload = zotero_request("GET", f"/users/{library_id}/items?{query}", api_key=api_key)
    found = matcher(payload or [])
    if found:
        return found

    start = 0
    page_size = 100
    while True:
        page_query = urllib.parse.urlencode(
            {
                "sort": "dateAdded",
                "direction": "desc",
                "limit": str(page_size),
                "start": str(start),
                "format": "json",
            }
        )
        _, _, page = zotero_request("GET", f"/users/{library_id}/items?{page_query}", api_key=api_key)
        found = matcher(page or [])
        if found:
            return found
        if not page or len(page) < page_size:
            break
        start += page_size
    return None


def find_existing_zotero_item_by_doi(api_key: str, library_id: str, doi: str) -> dict[str, Any] | None:
    target = normalize_doi(doi)
    if not target:
        return None
    return _find_existing_zotero_item(
        api_key,
        library_id,
        target,
        lambda payload: find_item_in_payload_by_doi(payload, target),
    )


def find_existing_zotero_item_by_pmid(api_key: str, library_id: str, pmid: str) -> dict[str, Any] | None:
    target = (pmid or "").strip()
    if not target:
        return None
    return _find_existing_zotero_item(
        api_key,
        library_id,
        target,
        lambda payload: find_item_in_payload_by_pmid(payload, target),
    )


def find_existing_zotero_item(api_key: str, library_id: str, doi: str, pmid: str) -> dict[str, Any] | None:
    return find_existing_zotero_item_by_doi(api_key, library_id, doi) or find_existing_zotero_item_by_pmid(
        api_key, library_id, pmid
    )


def create_zotero_item(api_key: str, library_id: str, item: dict[str, Any]) -> dict[str, Any]:
    _, _, payload = zotero_request("POST", f"/users/{library_id}/items", api_key=api_key, body=[item])
    successful = payload.get("successful", {}) if isinstance(payload, dict) else {}
    if not successful:
        raise RuntimeError(f"Zotero item creation failed: {payload}")
    return next(iter(successful.values()))


def to_json_output(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2)


def verify_and_add(
    identifier: str,
    *,
    tags: list[str] | None = None,
    collection_keys: list[str] | None = None,
    dry_run: bool = False,
    pubmed_bin: Path = DEFAULT_PUBMED_BIN,
) -> dict[str, Any]:
    api_key = os.environ.get("ZOTERO_API_KEY", "")
    library_id = os.environ.get("ZOTERO_LIBRARY_ID", "")
    if not api_key or not library_id:
        raise RuntimeError("ZOTERO_API_KEY and ZOTERO_LIBRARY_ID must be set.")

    article = fetch_pubmed_article(identifier, pubmed_bin)
    template = get_zotero_template(api_key)
    item = article_to_zotero_item(template, article, tags=tags, collection_keys=collection_keys)
    existing = find_existing_zotero_item(api_key, library_id, item.get("DOI", ""), article.get("pmid") or "")
    if existing:
        return {
            "status": "exists",
            "verified": True,
            "pmid": article.get("pmid"),
            "doi": item.get("DOI"),
            "item_key": existing.get("key") or existing.get("data", {}).get("key"),
            "title": item.get("title"),
        }
    if dry_run:
        return {
            "status": "dry-run",
            "verified": True,
            "pmid": article.get("pmid"),
            "doi": item.get("DOI"),
            "item": item,
        }
    created = create_zotero_item(api_key, library_id, item)
    return {
        "status": "created",
        "verified": True,
        "pmid": article.get("pmid"),
        "doi": item.get("DOI"),
        "item_key": created.get("key"),
        "title": item.get("title"),
    }


def verify_pubmed_only(identifier: str, *, pubmed_bin: Path = DEFAULT_PUBMED_BIN) -> dict[str, Any]:
    return pubmed_article_summary(fetch_pubmed_article(identifier, pubmed_bin))


def run_batch(
    identifiers: list[str],
    *,
    tags: list[str] | None = None,
    collection_keys: list[str] | None = None,
    dry_run: bool = False,
    pubmed_only: bool = False,
    pubmed_bin: Path = DEFAULT_PUBMED_BIN,
) -> dict[str, Any]:
    results = []
    for identifier in identifiers:
        try:
            if pubmed_only:
                result = verify_pubmed_only(identifier, pubmed_bin=pubmed_bin)
            else:
                result = verify_and_add(
                    identifier,
                    tags=tags,
                    collection_keys=collection_keys,
                    dry_run=dry_run,
                    pubmed_bin=pubmed_bin,
                )
            result["identifier"] = identifier
        except Exception as exc:
            result = {"identifier": identifier, "verified": False, "status": "error", "error": str(exc)}
        results.append(result)

    return {
        "status": "batch",
        "count": len(results),
        "failed": sum(1 for result in results if result.get("verified") is False),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify references with PubMed and add verified items to Zotero.")
    parser.add_argument("identifier", nargs="?", help="PMID, DOI, DOI URL, or PubMed-searchable title/query")
    parser.add_argument("--from-file", type=Path, help="UTF-8 text/Markdown file containing PubMed links or DOIs")
    parser.add_argument("--limit", type=int, default=None, help="Maximum extracted identifiers to process")
    parser.add_argument("--pubmed-only", action="store_true", help="Verify with PubMed only; do not read or write Zotero")
    parser.add_argument("--tag", action="append", default=[], help="Tag to add to newly created Zotero item")
    parser.add_argument("--collection-key", action="append", default=[], help="Existing Zotero collection key")
    parser.add_argument("--dry-run", action="store_true", help="Verify and build Zotero payload without writing")
    parser.add_argument("--pubmed-bin", default=str(DEFAULT_PUBMED_BIN), help="Path to pubmed.exe")
    args = parser.parse_args(argv)

    pubmed_bin = Path(args.pubmed_bin)
    if args.from_file:
        text = args.from_file.read_text(encoding="utf-8-sig")
        identifiers = extract_identifiers_from_text(text)
        if args.limit is not None:
            identifiers = identifiers[: args.limit]
        if not identifiers:
            raise RuntimeError(f"No PubMed links or DOIs found in: {args.from_file}")
        result = run_batch(
            identifiers,
            tags=args.tag,
            collection_keys=args.collection_key,
            dry_run=args.dry_run,
            pubmed_only=args.pubmed_only,
            pubmed_bin=pubmed_bin,
        )
    else:
        if not args.identifier:
            parser.error("identifier is required unless --from-file is used")
        if args.pubmed_only:
            result = verify_pubmed_only(args.identifier, pubmed_bin=pubmed_bin)
        else:
            result = verify_and_add(
                args.identifier,
                tags=args.tag,
                collection_keys=args.collection_key,
                dry_run=args.dry_run,
                pubmed_bin=pubmed_bin,
            )
    print(to_json_output(result))
    return 1 if result.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
