from __future__ import annotations

import re
from typing import Dict, List


def is_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def format_creators(item: Dict) -> str:
    creators: List[Dict] = [c for c in (item.get("creators") or []) if c.get("creatorType") == "author"]
    if not creators:
        return ""

    chinese = any(is_chinese((c.get("lastName") or "") + (c.get("firstName") or "")) for c in creators)
    names = []
    for creator in creators:
        if chinese:
            names.append((creator.get("lastName") or "") + (creator.get("firstName") or ""))
            continue
        first = (creator.get("firstName") or "").strip()
        last = (creator.get("lastName") or "").strip()
        if first and last:
            names.append(f"{last} {first[0]}")
        else:
            names.append(last or first)

    if len(names) > 3:
        return ("，".join(names[:3]) + "，等") if chinese else (", ".join(names[:3]) + ", et al.")
    return ("，" if chinese else ", ").join(names)


def infer_doc_type(item: Dict, original_url: str) -> str:
    item_type = (item.get("itemType") or "").lower()
    if item_type == "thesis":
        return "D"
    if item_type == "journalarticle":
        return "J"
    if item_type == "conferencepaper":
        return "C"
    url = (original_url or item.get("url") or "").lower()
    if "arxiv.org" in url:
        return "A"
    return "EB/OL"


def extract_year(item: Dict, original_url: str) -> str:
    for text in [item.get("date", ""), item.get("DOI", ""), item.get("url", ""), original_url]:
        if not text:
            continue
        match = re.search(r"(19|20)\d{2}", str(text))
        if match:
            return match.group(0)
    return ""


def format_reference(item: Dict, paragraph: int = 0, original_url: str = "") -> str:
    del paragraph
    title = (item.get("title") or "").strip()
    creators = format_creators(item)
    year = extract_year(item, original_url)
    publication = (item.get("publicationTitle") or "").strip()
    volume = (item.get("volume") or "").strip()
    issue = (item.get("issue") or "").strip()
    pages = (item.get("pages") or "").strip()
    university = (item.get("university") or "").strip()
    doc_type = infer_doc_type(item, original_url)

    prefix = ""
    if creators:
        prefix = creators + (" " if creators.endswith(".") else ". ")

    if doc_type == "J":
        source = publication
        if year:
            source += f", {year}"
        if volume:
            source += f", {volume}"
            if issue:
                source += f"({issue})"
        elif issue:
            source += f", ({issue})"
        if pages:
            source += f":{pages}"
        return f"{prefix}{title}[J]. {source}."

    if doc_type == "D":
        tail = ", ".join([part for part in [university, year] if part])
        return f"{prefix}{title}[D]. {tail or 'n.d.'}."

    if doc_type == "C":
        source = publication or "Conference paper"
        if year:
            source += f", {year}"
        if pages:
            source += f":{pages}"
        return f"{prefix}{title}[C]. {source}."

    if doc_type == "A":
        source = "arXiv"
        if year:
            source += f", {year}"
        return f"{prefix}{title}[A]. {source}."

    if publication:
        source = publication + (f", {year}" if year else "")
        return f"{prefix}{title}[EB/OL]. {source}."
    if year:
        return f"{prefix}{title}[EB/OL]. {year}."
    return f"{prefix}{title}[EB/OL]."
