#!/usr/bin/env python
"""Local Zotero-Word bridge.

This script does two things:
1. Stores Zotero citation/bibliography fields in Word rich-text content controls.
2. Talks to Zotero's HTTP integration endpoint so Zotero itself formats citations.

The resulting fields are not the official Word Zotero add-in fields. They are a
bridge-managed representation that can still be refreshed by Zotero through the
HTTP integration engine.
"""

from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import time
import traceback
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pythoncom
import requests
from win32com.client import constants, gencache

from . import reference_formatter as brf
from .config import default_log_path, discover_zotero_sqlite

try:
    from win32com.client import GetActiveObject
except ImportError:  # pragma: no cover
    GetActiveObject = None


FIELD_TAG_PREFIX = "ZOTERO_HTTP_FIELD:"
CODE_VAR_PREFIX = "ZOTERO_HTTP_CODE_"
DOC_DATA_VAR = "ZOTERO_HTTP_DOCUMENT_DATA"
DEFAULT_STYLE_ID = (
    "http://www.zotero.org/styles/"
    "gb-t-7714-2015-numeric-bilingual-no-uppercase-no-url-doi"
)
SCHEMA_URL = "https://github.com/citation-style-language/schema/raw/master/csl-citation.json"
CONNECTOR_BASE_URL = "http://127.0.0.1:23119/connector"
PROCESSOR_NAME = "Zotero Word MCP Bridge"
LOG_PATH = default_log_path()
SQLITE_PATH = discover_zotero_sqlite()


class BridgeError(RuntimeError):
    pass


class _HTMLToText(HTMLParser):
    BLOCK_TAGS = {"p", "div", "li", "ul", "ol", "tr", "table", "section"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag in {"br", "hr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        text = html.unescape("".join(self.parts))
        text = text.replace("\xa0", " ")
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(value: str) -> str:
    if not value:
        return ""
    parser = _HTMLToText()
    parser.feed(value)
    return parser.get_text()


def normalize_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))


def log_debug(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"[{timestamp}] {message}\n")
    except Exception:
        return


def citation_code_from_keys(
    keys: Iterable[str],
    library_id: int,
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
) -> str:
    citation_items = []
    for key in keys:
        item: Dict[str, Any] = {"key": key, "libraryID": library_id}
        if prefix:
            item["prefix"] = prefix
        if suffix:
            item["suffix"] = suffix
        citation_items.append(item)
    payload = {
        "citationID": uuid.uuid4().hex,
        "properties": {},
        "citationItems": citation_items,
        "schema": SCHEMA_URL,
    }
    return f"ITEM CSL_CITATION {json.dumps(payload, ensure_ascii=False)}"


def empty_bibliography_code() -> str:
    return "BIBL {} CSL_BIBLIOGRAPHY"


def extract_json_from_code(raw_code: str) -> Dict[str, Any]:
    if not raw_code:
        return {}
    start = raw_code.find("{")
    end = raw_code.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        return json.loads(raw_code[start : end + 1])
    except Exception:
        return {}


def normalize_doc_key(key: str) -> str:
    return (key or "").strip().upper()


@dataclass
class WordHandle:
    app: Any
    created_app: bool


class ZoteroLocalLibrary:
    def __init__(self, sqlite_path: Path = SQLITE_PATH) -> None:
        self.sqlite_path = sqlite_path
        self._cache: Dict[Tuple[int, str], Dict[str, Any]] = {}

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.sqlite_path.as_posix()}?mode=ro&immutable=1", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def load_items(self, refs: Iterable[Tuple[int, str]]) -> Dict[Tuple[int, str], Dict[str, Any]]:
        wanted = {(int(lib_id), normalize_doc_key(key)) for lib_id, key in refs if key}
        missing = [pair for pair in wanted if pair not in self._cache]
        if not missing:
            return {pair: self._cache[pair] for pair in wanted if pair in self._cache}

        conn = self._connect()
        try:
            placeholders = ",".join("?" for _ in missing)
            key_params = [key for _, key in missing]
            rows = conn.execute(
                f"""
                SELECT items.itemID,
                       items.key as itemKey,
                       ifnull(items.libraryID, 1) as libraryID,
                       itemTypes.typeName as itemType,
                       fieldsCombined.fieldName as fieldName,
                       itemDataValues.value as value
                FROM items
                JOIN itemTypes ON items.itemTypeID = itemTypes.itemTypeID
                LEFT JOIN itemData ON items.itemID = itemData.itemID
                LEFT JOIN itemDataValues ON itemData.valueID = itemDataValues.valueID
                LEFT JOIN fieldsCombined ON itemData.fieldID = fieldsCombined.fieldID
                WHERE upper(items.key) IN ({placeholders})
                """,
                key_params,
            ).fetchall()

            item_id_map: Dict[int, Tuple[int, str]] = {}
            for row in rows:
                pair = (int(row["libraryID"] or 1), normalize_doc_key(row["itemKey"]))
                entry = self._cache.setdefault(
                    pair,
                    {
                        "itemID": row["itemID"],
                        "key": row["itemKey"],
                        "libraryID": int(row["libraryID"] or 1),
                        "itemType": row["itemType"],
                        "creators": [],
                    },
                )
                item_id_map[row["itemID"]] = pair
                if row["fieldName"]:
                    entry[row["fieldName"]] = row["value"]

            if item_id_map:
                creator_placeholders = ",".join("?" for _ in item_id_map)
                creator_rows = conn.execute(
                    f"""
                    SELECT itemCreators.itemID,
                           creatorTypes.creatorType as creatorType,
                           creators.firstName as firstName,
                           creators.lastName as lastName,
                           itemCreators.orderIndex as orderIndex
                    FROM itemCreators
                    JOIN creators ON itemCreators.creatorID = creators.creatorID
                    JOIN creatorTypes ON itemCreators.creatorTypeID = creatorTypes.creatorTypeID
                    WHERE itemCreators.itemID IN ({creator_placeholders})
                    ORDER BY itemCreators.itemID, itemCreators.orderIndex
                    """,
                    list(item_id_map.keys()),
                ).fetchall()
                for row in creator_rows:
                    pair = item_id_map[row["itemID"]]
                    self._cache[pair]["creators"].append(
                        {
                            "creatorType": row["creatorType"],
                            "firstName": row["firstName"] or "",
                            "lastName": row["lastName"] or "",
                        }
                    )
        finally:
            conn.close()

        return {pair: self._cache[pair] for pair in wanted if pair in self._cache}

    def get_item(self, library_id: int, key: str) -> Optional[Dict[str, Any]]:
        pair = (int(library_id or 1), normalize_doc_key(key))
        if pair not in self._cache:
            self.load_items([pair])
        return self._cache.get(pair)


class WordBridge:
    def __init__(self, visible: bool = False) -> None:
        self.visible = visible
        self._handle: Optional[WordHandle] = None
        self._open_by_me: Dict[str, bool] = {}
        self._pending_bib_styles: Dict[str, Dict[str, Any]] = {}
        self.library = ZoteroLocalLibrary()

    def __enter__(self) -> "WordBridge":
        pythoncom.CoInitialize()
        self._handle = self._attach_word()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._handle and self._handle.created_app:
                app = self._handle.app
                while app.Documents.Count > 0:
                    app.Documents.Item(1).Close(False)
                app.Quit()
        finally:
            self._handle = None
            pythoncom.CoUninitialize()

    @property
    def app(self) -> Any:
        if not self._handle:
            raise BridgeError("Word 尚未初始化")
        return self._handle.app

    def _attach_word(self) -> WordHandle:
        app = None
        created = False
        if GetActiveObject is not None:
            try:
                app = GetActiveObject("Word.Application")
                log_debug("Attached to existing Word instance")
            except Exception:
                app = None
        if app is None:
            app = gencache.EnsureDispatch("Word.Application")
            created = True
            app.Visible = self.visible
            log_debug("Created new Word instance")
        return WordHandle(app=app, created_app=created)

    def get_document(self, doc_path: str) -> Any:
        doc_path = normalize_path(doc_path)
        for idx in range(1, self.app.Documents.Count + 1):
            doc = self.app.Documents.Item(idx)
            if normalize_path(doc.FullName) == doc_path:
                self._open_by_me.setdefault(doc_path, False)
                log_debug(f"Reused open document: {doc_path}")
                return doc
        doc = self.app.Documents.Open(doc_path)
        self._open_by_me[doc_path] = True
        log_debug(f"Opened document: {doc_path}")
        return doc

    def activate_document(self, doc: Any, make_visible: bool = False) -> None:
        doc.Activate()
        if make_visible:
            self.app.Visible = True
            self.app.ActiveWindow.Visible = True
        log_debug(f"Activated document: {normalize_path(doc.FullName)} visible={make_visible}")

    def save_document(self, doc: Any) -> None:
        doc.Save()
        log_debug(f"Saved document: {normalize_path(doc.FullName)}")

    def close_if_needed(self, doc: Any) -> None:
        doc_path = normalize_path(doc.FullName)
        if self._handle and self._handle.created_app and self._open_by_me.get(doc_path):
            doc.Close(True)

    def _ensure_variable(self, doc: Any, name: str, value: str) -> None:
        try:
            doc.Variables(name).Value = value
        except Exception:
            doc.Variables.Add(name, value)

    def _get_variable(self, doc: Any, name: str, default: str = "") -> str:
        try:
            return str(doc.Variables(name).Value)
        except Exception:
            return default

    def _delete_variable(self, doc: Any, name: str) -> None:
        try:
            doc.Variables(name).Delete()
        except Exception:
            return

    def load_document_data(self, doc: Any) -> Dict[str, Any]:
        raw = self._get_variable(doc, DOC_DATA_VAR)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            raise BridgeError("文档中的 Zotero documentData 不是合法 JSON")

    def ensure_document_data(
        self,
        doc: Any,
        style_id: Optional[str] = None,
        locale: str = "zh-CN",
    ) -> Dict[str, Any]:
        data = self.load_document_data(doc)
        session_id = data.get("sessionID") or uuid.uuid4().hex
        if not data:
            data = {
                "style": {
                    "styleID": style_id or DEFAULT_STYLE_ID,
                    "locale": locale,
                    "hasBibliography": True,
                    "bibliographyStyleHasBeenSet": False,
                },
                "prefs": {
                    "fieldType": "Http",
                    "noteType": 0,
                    "automaticJournalAbbreviations": False,
                    "delayCitationUpdates": False,
                },
                "sessionID": session_id,
                "zoteroVersion": "zotero-word-mcp-http-bridge",
                "dataVersion": 4,
            }
        else:
            data.setdefault("style", {})
            data.setdefault("prefs", {})
            data["sessionID"] = session_id
            data["dataVersion"] = 4
            data["style"]["styleID"] = style_id or data["style"].get("styleID") or DEFAULT_STYLE_ID
            data["style"]["locale"] = data["style"].get("locale") or locale
            data["style"]["hasBibliography"] = bool(data["style"].get("hasBibliography", True))
            data["style"]["bibliographyStyleHasBeenSet"] = bool(
                data["style"].get("bibliographyStyleHasBeenSet", False)
            )
            data["prefs"]["fieldType"] = "Http"
            data["prefs"]["noteType"] = int(data["prefs"].get("noteType", 0) or 0)
            data["prefs"]["automaticJournalAbbreviations"] = bool(
                data["prefs"].get("automaticJournalAbbreviations", False)
            )
            data["prefs"]["delayCitationUpdates"] = bool(
                data["prefs"].get("delayCitationUpdates", False)
            )
        self._ensure_variable(doc, DOC_DATA_VAR, json.dumps(data, ensure_ascii=False))
        log_debug(
            "Ensured documentData "
            f"style={data['style'].get('styleID')} fieldType={data['prefs'].get('fieldType')}"
        )
        return data

    def update_document_style(self, doc: Any, style_id: str, locale: str = "zh-CN") -> Dict[str, Any]:
        data = self.ensure_document_data(doc, style_id=style_id, locale=locale)
        data["style"]["styleID"] = style_id
        data["style"]["locale"] = locale
        data["style"]["bibliographyStyleHasBeenSet"] = False
        self._ensure_variable(doc, DOC_DATA_VAR, json.dumps(data, ensure_ascii=False))
        return data

    def _iter_zotero_controls(self, doc: Any) -> List[Any]:
        controls = []
        for idx in range(1, doc.ContentControls.Count + 1):
            control = doc.ContentControls.Item(idx)
            tag = str(control.Tag or "")
            if tag.startswith(FIELD_TAG_PREFIX):
                controls.append(control)
        controls.sort(key=lambda cc: (cc.Range.Start, cc.Range.End))
        return controls

    def _control_id(self, control: Any) -> str:
        tag = str(control.Tag or "")
        if not tag.startswith(FIELD_TAG_PREFIX):
            raise BridgeError("不是 zotero-word-mcp HTTP 字段")
        return tag[len(FIELD_TAG_PREFIX) :]

    def _code_var_name(self, field_id: str) -> str:
        return f"{CODE_VAR_PREFIX}{field_id}"

    def _field_kind(self, raw_code: str) -> str:
        if raw_code.startswith("BIBL"):
            return "bibliography"
        if raw_code.startswith("ITEM") or raw_code.startswith("CITATION"):
            return "citation"
        return "temp"

    def _citation_keys_from_code(self, raw_code: str) -> List[Tuple[int, str]]:
        data = extract_json_from_code(raw_code)
        out: List[Tuple[int, str]] = []
        for item in data.get("citationItems") or []:
            key = item.get("key")
            if not key:
                continue
            out.append((int(item.get("libraryID") or 1), normalize_doc_key(key)))
        return out

    def _set_control_code(self, doc: Any, control: Any, raw_code: str) -> None:
        field_id = self._control_id(control)
        self._ensure_variable(doc, self._code_var_name(field_id), raw_code)
        kind = self._field_kind(raw_code)
        if kind == "bibliography":
            control.Title = "Zotero Word MCP Bibliography"
        elif kind == "citation":
            control.Title = "Zotero Word MCP Citation"
        else:
            control.Title = "Zotero Word MCP Field"

    def _field_payload(self, doc: Any, control: Any) -> Dict[str, Any]:
        field_id = self._control_id(control)
        raw_code = self._get_variable(doc, self._code_var_name(field_id), "TEMP")
        return {
            "id": field_id,
            "code": raw_code,
            "text": str(control.Range.Text),
            "noteIndex": 0,
            "adjacent": False,
        }

    def list_fields(self, doc: Any) -> List[Dict[str, Any]]:
        fields = []
        for cc in self._iter_zotero_controls(doc):
            payload = self._field_payload(doc, cc)
            payload["kind"] = self._field_kind(payload["code"])
            if payload["kind"] == "citation":
                payload["items"] = [
                    {"libraryID": lib_id, "key": key}
                    for lib_id, key in self._citation_keys_from_code(payload["code"])
                ]
            fields.append(payload)
        return fields

    def find_control(self, doc: Any, field_id: str) -> Any:
        for control in self._iter_zotero_controls(doc):
            if self._control_id(control) == field_id:
                return control
        raise BridgeError(f"找不到字段 {field_id}")

    def _insert_control_at_range(self, doc: Any, rng: Any, raw_code: str, text: str = "") -> Dict[str, Any]:
        control = rng.ContentControls.Add(constants.wdContentControlRichText)
        control.Tag = f"{FIELD_TAG_PREFIX}{uuid.uuid4().hex}"
        control.SetPlaceholderText(None, None, "")
        control.LockContents = False
        control.LockContentControl = False
        if text:
            control.Range.Text = text
        self._set_control_code(doc, control, raw_code)
        return self._field_payload(doc, control)

    def _find_range(self, doc: Any, text: str) -> Optional[Any]:
        rng = doc.Content.Duplicate
        finder = rng.Find
        finder.ClearFormatting()
        finder.Text = text
        ok = finder.Execute()
        if not ok:
            return None
        return rng

    def resolve_insert_range(self, doc: Any, find_text: Optional[str], placement: str) -> Any:
        placement = placement.lower()
        self.activate_document(doc, make_visible=(placement == "current" and not find_text))
        if not find_text:
            if placement == "end":
                return doc.Range(doc.Content.End - 1, doc.Content.End - 1)
            return self.app.Selection.Range

        found = self._find_range(doc, find_text)
        if not found:
            raise BridgeError(f"未找到文本: {find_text}")

        if placement == "replace":
            start, end = found.Start, found.End
            doc.Range(start, end).Text = ""
            return doc.Range(start, start)
        if placement == "before":
            return doc.Range(found.Start, found.Start)
        if placement == "after":
            return doc.Range(found.End, found.End)
        if placement == "current":
            return found
        raise BridgeError(f"不支持的插入位置: {placement}")

    def cursor_in_field(self, doc: Any) -> Optional[Dict[str, Any]]:
        selection = self.app.Selection.Range
        if selection.ContentControls.Count:
            for idx in range(1, selection.ContentControls.Count + 1):
                control = selection.ContentControls.Item(idx)
                tag = str(control.Tag or "")
                if tag.startswith(FIELD_TAG_PREFIX):
                    return self._field_payload(doc, control)
        return None

    def can_insert_field(self, doc: Any) -> bool:
        return True

    def delete_field(self, doc: Any, field_id: str, delete_contents: bool) -> bool:
        control = self.find_control(doc, field_id)
        self._delete_variable(doc, self._code_var_name(field_id))
        control.Delete(delete_contents)
        return True

    def set_field_code(self, doc: Any, field_id: str, raw_code: str) -> bool:
        control = self.find_control(doc, field_id)
        self._set_control_code(doc, control, raw_code)
        return True

    def select_field(self, doc: Any, field_id: str) -> bool:
        control = self.find_control(doc, field_id)
        control.Range.Select()
        return True

    def set_pending_bibliography_style(self, doc: Any, args: Dict[str, Any]) -> bool:
        doc_key = normalize_path(doc.FullName)
        self._pending_bib_styles[doc_key] = args
        return True

    def _apply_bibliography_style(self, control: Any, style: Dict[str, Any]) -> None:
        try:
            paragraphs = control.Range.Paragraphs
            for idx in range(1, paragraphs.Count + 1):
                para = paragraphs.Item(idx)
                fmt = para.Range.ParagraphFormat
                fmt.LeftIndent = style["bodyIndent"]
                fmt.FirstLineIndent = style["firstLineIndent"]
                fmt.LineSpacing = max(12, style["lineSpacing"])
                fmt.SpaceAfter = style["entrySpacing"]
                if style["tabStops"]:
                    fmt.TabStops.ClearAll()
                    for tab_stop in style["tabStops"]:
                        fmt.TabStops.Add(tab_stop)
        except Exception:
            return

    def set_field_text(self, doc: Any, field_id: str, text: str) -> bool:
        control = self.find_control(doc, field_id)
        raw_code = self._get_variable(doc, self._code_var_name(field_id), "")
        plain_text = html_to_text(text) if "<" in text and ">" in text else text
        control.Range.Text = plain_text
        if raw_code.startswith("BIBL"):
            doc_key = normalize_path(doc.FullName)
            style = self._pending_bib_styles.get(doc_key)
            if style:
                self._apply_bibliography_style(control, style)
        return True

    def insert_citation_field(
        self,
        doc: Any,
        keys: Iterable[str],
        library_id: int = 1,
        find_text: Optional[str] = None,
        placement: str = "current",
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.ensure_document_data(doc)
        rng = self.resolve_insert_range(doc, find_text=find_text, placement=placement)
        raw_code = citation_code_from_keys(keys, library_id=library_id, prefix=prefix, suffix=suffix)
        payload = self._insert_control_at_range(doc, rng, raw_code=raw_code, text="[待刷新引文]")
        self.save_document(doc)
        log_debug(f"Inserted citation field for keys={list(keys)}")
        return payload

    def insert_bibliography_field(
        self,
        doc: Any,
        find_text: Optional[str] = None,
        placement: str = "current",
    ) -> Dict[str, Any]:
        self.ensure_document_data(doc)
        rng = self.resolve_insert_range(doc, find_text=find_text, placement=placement)
        payload = self._insert_control_at_range(
            doc,
            rng,
            raw_code=empty_bibliography_code(),
            text="参考文献待刷新",
        )
        self.save_document(doc)
        log_debug("Inserted bibliography field")
        return payload

    def refresh_static(self, doc: Any) -> Dict[str, Any]:
        controls = self._iter_zotero_controls(doc)
        citations: List[Tuple[Any, Dict[str, Any], List[Tuple[int, str]]]] = []
        bibliographies: List[Tuple[Any, Dict[str, Any]]] = []
        wanted_items: List[Tuple[int, str]] = []

        for control in controls:
            payload = self._field_payload(doc, control)
            kind = self._field_kind(payload["code"])
            if kind == "citation":
                refs = self._citation_keys_from_code(payload["code"])
                citations.append((control, payload, refs))
                wanted_items.extend(refs)
            elif kind == "bibliography":
                bibliographies.append((control, payload))

        item_map = self.library.load_items(wanted_items)

        order: List[Tuple[int, str]] = []
        seen = set()
        for _, _, refs in citations:
            for ref in refs:
                if ref not in seen and ref in item_map:
                    seen.add(ref)
                    order.append(ref)

        index_map = {ref: idx + 1 for idx, ref in enumerate(order)}

        updated_citations = 0
        for control, _, refs in citations:
            numbers = [index_map[ref] for ref in refs if ref in index_map]
            text = "[" + ", ".join(str(n) for n in numbers) + "]" if numbers else "[?]"
            control.Range.Text = text
            updated_citations += 1

        bibliography_entries: List[str] = []
        for idx, ref in enumerate(order, start=1):
            item = item_map.get(ref)
            if not item:
                bibliography_entries.append(f"[{idx}] 未找到 Zotero 条目: {ref[1]}")
                continue
            url = item.get("url") or ""
            formatted = brf.format_reference(item, 0, url)
            bibliography_entries.append(f"[{idx}] {formatted}")

        bibliography_text = "\r".join(bibliography_entries) if bibliography_entries else "参考文献待补充"
        for control, _ in bibliographies:
            control.Range.Text = bibliography_text

        self.save_document(doc)
        log_debug(
            f"Static refresh completed citations={updated_citations} refs={len(order)} "
            f"bibliographies={len(bibliographies)}"
        )
        return {
            "citations": updated_citations,
            "references": len(order),
            "bibliographies": len(bibliographies),
        }


class ZoteroConnectorClient:
    def __init__(self, bridge: WordBridge, base_url: str = CONNECTOR_BASE_URL) -> None:
        self.bridge = bridge
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.timeout = 120

    def _post_json(self, path: str, payload: Any) -> requests.Response:
        log_debug(f"HTTP POST {path} payload={json.dumps(payload, ensure_ascii=False)[:500]}")
        resp = self.session.post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        log_debug(f"HTTP {path} status={resp.status_code} body={resp.text[:500]}")
        return resp

    def exec_command(self, doc_path: str, command: str) -> None:
        doc_path = normalize_path(doc_path)
        doc = self.bridge.get_document(doc_path)
        self.bridge.activate_document(doc, make_visible=False)
        log_debug(f"Starting Zotero command={command} doc={doc_path}")
        response = self._post_json(
            "/document/execCommand",
            {"command": command, "docId": doc_path},
        )
        next_command = self._parse_response(response)
        while next_command:
            payload = self._dispatch(next_command, doc_path)
            response = self._post_json("/document/respond", payload)
            next_command = self._parse_response(response)
        self.bridge.save_document(doc)

    def _parse_response(self, response: requests.Response) -> Optional[Dict[str, Any]]:
        body = response.text.strip()
        if not body:
            log_debug("No further Zotero command response")
            return None
        try:
            data = response.json()
        except ValueError as exc:
            raise BridgeError(f"Zotero 返回了非 JSON 响应: {body[:200]}") from exc
        if not isinstance(data, dict) or "command" not in data:
            log_debug(f"Ignored non-command response: {body[:200]}")
            return None
        log_debug(f"Next Zotero command={data.get('command')}")
        return data

    def _dispatch(self, message: Dict[str, Any], doc_path: str) -> Any:
        command = message["command"]
        args = message.get("arguments", [])
        log_debug(f"Dispatch command={command} args={json.dumps(args, ensure_ascii=False)[:500]}")
        try:
            return self._dispatch_inner(command, args, doc_path)
        except Exception as exc:
            log_debug(f"Dispatch error command={command} error={exc}\n{traceback.format_exc()}")
            return {
                "error": exc.__class__.__name__,
                "message": str(exc),
                "stack": traceback.format_exc(),
            }

    def _dispatch_inner(self, command: str, args: List[Any], doc_path: str) -> Any:
        doc = self.bridge.get_document(doc_path)
        if command == "Application.getActiveDocument":
            return {
                "documentID": normalize_path(doc.FullName),
                "outputFormat": "html",
                "supportedNotes": [],
                "supportsImportExport": False,
                "supportsTextInsertion": False,
                "supportsCitationMerging": False,
                "processorName": PROCESSOR_NAME,
            }

        if command == "Document.activate":
            self.bridge.activate_document(doc, make_visible=False)
            return True
        if command == "Document.canInsertField":
            return self.bridge.can_insert_field(doc)
        if command == "Document.displayAlert":
            # Non-interactive bridge: log and acknowledge.
            if len(args) >= 4:
                dialog_text = args[1]
                print(f"[Zotero alert] {dialog_text}", file=sys.stderr)
            return 0
        if command == "Document.getDocumentData":
            return self.bridge._get_variable(doc, DOC_DATA_VAR, "")
        if command == "Document.setDocumentData":
            self.bridge._ensure_variable(doc, DOC_DATA_VAR, args[1])
            self.bridge.save_document(doc)
            return True
        if command == "Document.setBibliographyStyle":
            self.bridge.set_pending_bibliography_style(
                doc,
                {
                    "firstLineIndent": int(args[1]),
                    "bodyIndent": int(args[2]),
                    "lineSpacing": int(args[3]),
                    "entrySpacing": int(args[4]),
                    "tabStops": list(args[5] or []),
                },
            )
            return True
        if command == "Document.insertText":
            self.bridge.app.Selection.Range.Text = str(args[1])
            return True
        if command == "Document.cursorInField":
            return self.bridge.cursor_in_field(doc)
        if command == "Document.insertField":
            rng = self.bridge.app.Selection.Range
            return self.bridge._insert_control_at_range(doc, rng, raw_code="TEMP", text="")
        if command == "Document.getFields":
            return self.bridge.list_fields(doc)
        if command == "Document.complete":
            self.bridge.save_document(doc)
            return True

        if command == "Field.delete":
            return self.bridge.delete_field(doc, args[1], delete_contents=True)
        if command == "Field.removeCode":
            return self.bridge.delete_field(doc, args[1], delete_contents=False)
        if command == "Field.select":
            return self.bridge.select_field(doc, args[1])
        if command == "Field.setText":
            return self.bridge.set_field_text(doc, args[1], args[2])
        if command == "Field.setCode":
            return self.bridge.set_field_code(doc, args[1], args[2])

        raise BridgeError(f"尚未实现的命令: {command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="zotero-word-mcp HTTP bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_doc_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--doc", required=True, help="目标 Word 文档路径")
        p.add_argument(
            "--style-id",
            default=None,
            help="Zotero CSL style ID；不传则沿用文档设置或默认使用 GB/T 7714 数字制",
        )
        p.add_argument(
            "--find",
            default=None,
            help="定位文本；和 --placement before/after/replace 一起使用",
        )
        p.add_argument(
            "--placement",
            choices=["current", "end", "before", "after", "replace"],
            default="current",
            help="插入位置，默认使用当前 Word 光标位置",
        )

    p_insert = subparsers.add_parser("insert-citation", help="插入一个 Zotero 引文并刷新")
    add_doc_options(p_insert)
    p_insert.add_argument("--keys", nargs="+", required=True, help="Zotero 条目 key，可一次传多个")
    p_insert.add_argument("--library-id", type=int, default=1, help="Zotero libraryID，默认 1")
    p_insert.add_argument("--prefix", default=None, help="引文前缀")
    p_insert.add_argument("--suffix", default=None, help="引文后缀")

    p_bib = subparsers.add_parser("insert-bibliography", help="插入参考文献表并刷新")
    add_doc_options(p_bib)

    p_refresh = subparsers.add_parser("refresh", help="刷新文档中的所有 HTTP bridge 字段")
    add_doc_options(p_refresh)

    p_refresh_official = subparsers.add_parser("refresh-official", help="实验性：走 Zotero 官方 HTTP integration 刷新")
    add_doc_options(p_refresh_official)

    p_style = subparsers.add_parser("set-style", help="更新文档中的 Zotero style 设置")
    p_style.add_argument("--doc", required=True, help="目标 Word 文档路径")
    p_style.add_argument("--style-id", required=True, help="新的 Zotero CSL style ID")
    p_style.add_argument("--refresh", action="store_true", help="更新后立刻 refresh")

    p_list = subparsers.add_parser("list-fields", help="列出当前文档中的 HTTP bridge 字段")
    p_list.add_argument("--doc", required=True, help="目标 Word 文档路径")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    doc_path = normalize_path(args.doc)
    with WordBridge() as bridge:
        doc = bridge.get_document(doc_path)
        show_doc = bool(
            getattr(args, "placement", "") == "current" and args.command in {"insert-citation", "insert-bibliography"}
        )
        bridge.activate_document(doc, make_visible=show_doc)

        if args.command == "insert-citation":
            if args.style_id:
                bridge.update_document_style(doc, args.style_id)
            else:
                bridge.ensure_document_data(doc)
            payload = bridge.insert_citation_field(
                doc,
                keys=args.keys,
                library_id=args.library_id,
                find_text=args.find,
                placement=args.placement,
                prefix=args.prefix,
                suffix=args.suffix,
            )
            summary = bridge.refresh_static(doc)
            print(
                json.dumps(
                    {"inserted": payload, "refresh": summary, "doc": doc_path},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "insert-bibliography":
            if args.style_id:
                bridge.update_document_style(doc, args.style_id)
            else:
                bridge.ensure_document_data(doc)
            payload = bridge.insert_bibliography_field(
                doc,
                find_text=args.find,
                placement=args.placement,
            )
            summary = bridge.refresh_static(doc)
            print(
                json.dumps(
                    {"inserted": payload, "refresh": summary, "doc": doc_path},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "refresh":
            if args.style_id:
                bridge.update_document_style(doc, args.style_id)
            else:
                bridge.ensure_document_data(doc)
            summary = bridge.refresh_static(doc)
            print(json.dumps({"refreshed": True, "summary": summary, "doc": doc_path}, ensure_ascii=False, indent=2))
            return 0

        if args.command == "refresh-official":
            if args.style_id:
                bridge.update_document_style(doc, args.style_id)
            else:
                bridge.ensure_document_data(doc)
            ZoteroConnectorClient(bridge).exec_command(doc_path, "refresh")
            print(json.dumps({"refreshed": True, "mode": "official", "doc": doc_path}, ensure_ascii=False, indent=2))
            return 0

        if args.command == "set-style":
            bridge.update_document_style(doc, args.style_id)
            if args.refresh:
                summary = bridge.refresh_static(doc)
            else:
                summary = None
            bridge.save_document(doc)
            out = {"styleUpdated": args.style_id, "doc": doc_path}
            if summary is not None:
                out["refresh"] = summary
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0

        if args.command == "list-fields":
            print(json.dumps(bridge.list_fields(doc), ensure_ascii=False, indent=2))
            return 0

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BridgeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
