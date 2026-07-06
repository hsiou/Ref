#!/usr/bin/env python
"""Native Word-Zotero bridge using official Word field/custom-property formats.

This bridge writes Zotero-compatible native Word fields:
- document preferences in split custom document properties: ZOTERO_PREF_1..N
- citations/bibliographies as native ADDIN fields with codes like:
  ADDIN ZOTERO_ITEM CSL_CITATION {...}

It can also trigger Zotero's official Word integration refresh command and probe
whether the official Word integration DLL recognizes the generated document.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import pythoncom
import pywintypes

from .config import discover_word_integration_dll
from .word_bridge import (
    BridgeError,
    DEFAULT_STYLE_ID,
    WordBridge,
    citation_code_from_keys,
    empty_bibliography_code,
    log_debug,
    normalize_path,
)


CUSTOM_PROP_PREFIX = "ZOTERO_PREF"
MAX_CUSTOM_PROP_LENGTH = 255
WORD_FIELD_QUOTE = 35
NATIVE_FIELD_PREFIX = " ADDIN ZOTERO_"
FIELD_PLACEHOLDER = "{Citation}"
BIBL_PLACEHOLDER = "{Bibliography}"
WORD_INTEGRATION_DLL = discover_word_integration_dll()
RPC_E_CALL_REJECTED = -2147418111
NUMBERED_CITATION_RE = re.compile(r"\[((?:\d+\s*(?:[-,，]\s*\d+\s*)*)+)\]")
STATIC_REFERENCE_RE = re.compile(r"^\[(\d+)\]\s+")

MACRO_MAP = {
    "refresh": "Project.Zotero.ZoteroRefresh",
    "setDocPrefs": "Project.Zotero.ZoteroSetDocPrefs",
    "addEditCitation": "Project.Zotero.ZoteroAddEditCitation",
    "addEditBibliography": "Project.Zotero.ZoteroAddEditBibliography",
}


class NativeWordBridge(WordBridge):
    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._handle:
                app = self._handle.app
                for doc_path, opened_by_me in list(self._open_by_me.items()):
                    if not opened_by_me:
                        continue
                    for idx in range(app.Documents.Count, 0, -1):
                        try:
                            doc = app.Documents.Item(idx)
                        except Exception:
                            continue
                        if normalize_path(getattr(doc, "FullName", "")) != doc_path:
                            continue
                        try:
                            doc.Close(False)
                        except Exception:
                            continue
                if self._handle.created_app:
                    try:
                        app.Quit()
                    except Exception:
                        pass
        finally:
            self._handle = None
            pythoncom.CoUninitialize()

    def _prop_name(self, index: int) -> str:
        return f"{CUSTOM_PROP_PREFIX}_{index}"

    def _get_custom_prop(self, doc: Any, name: str) -> Optional[str]:
        try:
            return str(doc.CustomDocumentProperties(name).Value)
        except Exception:
            return None

    def _set_custom_prop(self, doc: Any, name: str, value: str) -> None:
        try:
            doc.CustomDocumentProperties(name).Value = value
        except Exception:
            doc.CustomDocumentProperties.Add(name, False, 4, value)

    def _delete_custom_prop(self, doc: Any, name: str) -> None:
        try:
            doc.CustomDocumentProperties(name).Delete()
        except Exception:
            return

    def _is_rpc_call_rejected(self, exc: Exception) -> bool:
        return bool(getattr(exc, "args", None)) and exc.args[0] == RPC_E_CALL_REJECTED

    def _retry_word_call(
        self,
        func,
        *,
        timeout_sec: float = 15.0,
        poll_interval_sec: float = 0.25,
    ):
        deadline = time.time() + timeout_sec
        while True:
            try:
                return func()
            except pywintypes.com_error as exc:
                if self._is_rpc_call_rejected(exc) and time.time() < deadline:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(poll_interval_sec)
                    continue
                raise

    def load_native_document_data(self, doc: Any) -> Dict[str, Any]:
        chunks: List[str] = []
        index = 1
        while True:
            value = self._get_custom_prop(doc, self._prop_name(index))
            if value is None:
                break
            chunks.append(value)
            index += 1
        raw = "".join(chunks)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BridgeError("Word 原生 Zotero 文档属性不是合法 JSON") from exc

    def ensure_native_document_data(
        self,
        doc: Any,
        style_id: Optional[str] = None,
        locale: str = "zh-CN",
    ) -> Dict[str, Any]:
        data = self.load_native_document_data(doc)
        if not data:
            data = {
                "style": {
                    "styleID": style_id or DEFAULT_STYLE_ID,
                    "locale": locale,
                    "hasBibliography": True,
                    "bibliographyStyleHasBeenSet": False,
                },
                "prefs": {
                    "fieldType": "Field",
                    "noteType": 0,
                    "automaticJournalAbbreviations": False,
                    "delayCitationUpdates": False,
                },
                "sessionID": uuid.uuid4().hex,
                "zoteroVersion": "zotero-word-mcp-native-bridge",
                "dataVersion": 4,
            }
        else:
            data.setdefault("style", {})
            data.setdefault("prefs", {})
            data["dataVersion"] = 4
            data["style"]["styleID"] = style_id or data["style"].get("styleID") or DEFAULT_STYLE_ID
            data["style"]["locale"] = data["style"].get("locale") or locale
            data["style"]["hasBibliography"] = bool(data["style"].get("hasBibliography", True))
            data["style"]["bibliographyStyleHasBeenSet"] = bool(
                data["style"].get("bibliographyStyleHasBeenSet", False)
            )
            data["prefs"]["fieldType"] = "Field"
            data["prefs"]["noteType"] = int(data["prefs"].get("noteType", 0) or 0)
            data["prefs"]["automaticJournalAbbreviations"] = bool(
                data["prefs"].get("automaticJournalAbbreviations", False)
            )
            data["prefs"]["delayCitationUpdates"] = bool(data["prefs"].get("delayCitationUpdates", False))
        raw = json.dumps(data, ensure_ascii=False)
        chunks = [
            raw[idx : idx + MAX_CUSTOM_PROP_LENGTH]
            for idx in range(0, len(raw), MAX_CUSTOM_PROP_LENGTH)
        ] or [""]
        for idx, chunk in enumerate(chunks, start=1):
            self._set_custom_prop(doc, self._prop_name(idx), chunk)
        extra = len(chunks) + 1
        while self._get_custom_prop(doc, self._prop_name(extra)) is not None:
            self._delete_custom_prop(doc, self._prop_name(extra))
            extra += 1
        log_debug(
            "Ensured native documentData "
            f"style={data['style'].get('styleID')} chunks={len(chunks)}"
        )
        return data

    def update_native_document_style(self, doc: Any, style_id: str, locale: str = "zh-CN") -> Dict[str, Any]:
        data = self.ensure_native_document_data(doc, style_id=style_id, locale=locale)
        data["style"]["styleID"] = style_id
        data["style"]["locale"] = locale
        data["style"]["bibliographyStyleHasBeenSet"] = False
        data["sessionID"] = uuid.uuid4().hex
        raw = json.dumps(data, ensure_ascii=False)
        chunks = [raw[i : i + MAX_CUSTOM_PROP_LENGTH] for i in range(0, len(raw), MAX_CUSTOM_PROP_LENGTH)] or [""]
        for idx, chunk in enumerate(chunks, start=1):
            self._set_custom_prop(doc, self._prop_name(idx), chunk)
        extra = len(chunks) + 1
        while self._get_custom_prop(doc, self._prop_name(extra)) is not None:
            self._delete_custom_prop(doc, self._prop_name(extra))
            extra += 1
        return data

    def _native_field_code(self, code: str) -> str:
        return f"{NATIVE_FIELD_PREFIX}{code} "

    def _strip_native_field_code(self, raw_code: str) -> Optional[str]:
        if not raw_code:
            return None
        if raw_code.startswith(NATIVE_FIELD_PREFIX):
            trimmed = raw_code[len(NATIVE_FIELD_PREFIX) :]
            return trimmed[:-1] if trimmed.endswith(" ") else trimmed
        return None

    def list_native_fields(self, doc: Any) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = []
        field_count = int(self._retry_word_call(lambda: doc.Fields.Count))
        for idx in range(1, field_count + 1):
            field = self._retry_word_call(lambda idx=idx: doc.Fields.Item(idx))
            raw_code = str(self._retry_word_call(lambda field=field: field.Code.Text or ""))
            code = self._strip_native_field_code(raw_code)
            if code is None:
                continue
            kind = "bibliography" if code.startswith("BIBL") else "citation"
            fields.append(
                {
                    "index": idx,
                    "type": int(self._retry_word_call(lambda field=field: field.Type)),
                    "kind": kind,
                    "code": code,
                    "text": str(self._retry_word_call(lambda field=field: field.Result.Text or "")),
                }
            )
        return fields

    def _field_result_signature(self, doc: Any) -> List[tuple]:
        return [
            (payload.get("kind") or "", (payload.get("text") or "").strip())
            for payload in self.list_native_fields(doc)
        ]

    def _paragraph_count(self, doc: Any) -> int:
        return int(self._retry_word_call(lambda: doc.Paragraphs.Count))

    def _paragraph(self, doc: Any, index: int) -> Any:
        return self._retry_word_call(lambda: doc.Paragraphs.Item(index))

    def _paragraph_text(self, paragraph: Any) -> str:
        raw = str(self._retry_word_call(lambda: paragraph.Range.Text or ""))
        return raw.replace("\r", "").replace("\x07", "").strip()

    def _paragraph_native_field_kinds(self, paragraph: Any) -> List[str]:
        kinds: List[str] = []
        field_count = int(self._retry_word_call(lambda: paragraph.Range.Fields.Count))
        for idx in range(1, field_count + 1):
            field = self._retry_word_call(lambda idx=idx: paragraph.Range.Fields.Item(idx))
            raw_code = str(self._retry_word_call(lambda field=field: field.Code.Text or ""))
            code = self._strip_native_field_code(raw_code)
            if code is None:
                continue
            kinds.append("bibliography" if code.startswith("BIBL") else "citation")
        return kinds

    def _find_heading_paragraph_index(self, doc: Any, heading_text: str) -> Optional[int]:
        target = heading_text.strip().casefold()
        for idx in range(self._paragraph_count(doc), 0, -1):
            if self._paragraph_text(self._paragraph(doc, idx)).casefold() == target:
                return idx
        return None

    def _expand_numbered_citation(self, value: str) -> List[int]:
        numbers: List[int] = []
        for part in re.split(r"[,，]", value):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_raw, end_raw = part.split("-", 1)
                start = int(start_raw.strip())
                end = int(end_raw.strip())
                step = 1 if end >= start else -1
                numbers.extend(range(start, end + step, step))
            else:
                numbers.append(int(part))
        return numbers

    def analyze_numbered_citations(
        self,
        doc: Any,
        bibliography_heading: str = "References",
    ) -> Dict[str, Any]:
        heading_index = self._find_heading_paragraph_index(doc, bibliography_heading)
        paragraph_count = self._paragraph_count(doc)
        citation_markers: List[Dict[str, Any]] = []
        static_references: List[Dict[str, Any]] = []
        max_reference_number = 0

        body_end_index = heading_index or paragraph_count + 1
        for paragraph_index in range(1, body_end_index):
            text = self._paragraph_text(self._paragraph(doc, paragraph_index))
            for match_index, match in enumerate(NUMBERED_CITATION_RE.finditer(text), start=1):
                raw = match.group(0)
                numbers = self._expand_numbered_citation(match.group(1))
                citation_markers.append(
                    {
                        "paragraphIndex": paragraph_index,
                        "matchIndex": match_index,
                        "raw": raw,
                        "numbers": numbers,
                    }
                )

        if heading_index is not None:
            for paragraph_index in range(heading_index + 1, paragraph_count + 1):
                text = self._paragraph_text(self._paragraph(doc, paragraph_index))
                match = STATIC_REFERENCE_RE.match(text)
                if not match:
                    continue
                number = int(match.group(1))
                max_reference_number = max(max_reference_number, number)
                static_references.append(
                    {
                        "paragraphIndex": paragraph_index,
                        "number": number,
                        "text": text,
                    }
                )

        bad_numbers: List[Dict[str, Any]] = []
        if max_reference_number:
            for marker in citation_markers:
                for number in marker["numbers"]:
                    if number < 1 or number > max_reference_number:
                        bad_numbers.append(
                            {
                                "raw": marker["raw"],
                                "number": number,
                                "paragraphIndex": marker["paragraphIndex"],
                            }
                        )

        return {
            "bibliographyHeading": bibliography_heading,
            "bibliographyHeadingParagraphIndex": heading_index,
            "paragraphCount": paragraph_count,
            "citationMarkerCount": len(citation_markers),
            "citationMarkers": citation_markers,
            "staticReferenceCount": len(static_references),
            "staticReferences": static_references,
            "maxReferenceNumber": max_reference_number,
            "badCitationNumbers": bad_numbers,
        }

    def _find_text_range(self, doc: Any, text: str, start: int, end: int) -> Optional[Any]:
        rng = doc.Range(start, end)
        finder = rng.Find
        finder.ClearFormatting()
        finder.Text = text
        finder.Forward = True
        ok = finder.Execute()
        if not ok:
            return None
        return rng

    def _citation_keys_for_numbers(
        self,
        citation_map: Mapping[str, Any],
        numbers: Sequence[int],
    ) -> List[str]:
        keys: List[str] = []
        for number in numbers:
            value = citation_map.get(str(number), citation_map.get(number))  # type: ignore[arg-type]
            if value is None:
                raise BridgeError(f"缺少编号 {number} 对应的 Zotero item key")
            if isinstance(value, str):
                keys.append(value)
            elif isinstance(value, Sequence):
                keys.extend(str(item) for item in value)
            else:
                raise BridgeError(f"编号 {number} 的 Zotero item key 映射无效")
        return keys

    def delete_static_references_after_heading(
        self,
        doc: Any,
        bibliography_heading: str = "References",
    ) -> Dict[str, Any]:
        analysis = self.analyze_numbered_citations(doc, bibliography_heading=bibliography_heading)
        deleted: List[Dict[str, Any]] = []
        for ref in reversed(analysis["staticReferences"]):
            paragraph = self._paragraph(doc, int(ref["paragraphIndex"]))
            paragraph.Range.Delete()
            deleted.append(ref)
        return {
            "bibliographyHeadingParagraphIndex": analysis["bibliographyHeadingParagraphIndex"],
            "deletedReferenceCount": len(deleted),
            "deletedReferences": list(reversed(deleted)),
        }

    def insert_native_bibliography_after_heading(
        self,
        doc: Any,
        bibliography_heading: str = "References",
    ) -> Dict[str, Any]:
        self.ensure_native_document_data(doc)
        heading_index = self._find_heading_paragraph_index(doc, bibliography_heading)
        if heading_index is None:
            raise BridgeError(f"未找到参考文献标题段落: {bibliography_heading}")
        heading_paragraph = self._paragraph(doc, heading_index)
        heading_paragraph.Range.InsertParagraphAfter()
        insert_paragraph = self._paragraph(doc, heading_index + 1)
        rng = insert_paragraph.Range
        rng.End = max(rng.Start, rng.End - 1)
        payload = self._insert_native_field_at_range(doc, rng, empty_bibliography_code(), BIBL_PLACEHOLDER)
        self.save_document(doc)
        return {
            **payload,
            "bibliographyHeadingParagraphIndex": heading_index,
            "bibliographyParagraphIndex": heading_index + 1,
        }

    def convert_numbered_citations(
        self,
        doc: Any,
        citation_map: Mapping[str, Any],
        bibliography_heading: str = "References",
        library_id: int = 1,
        delete_static_references: bool = True,
        insert_bibliography: bool = True,
    ) -> Dict[str, Any]:
        self.ensure_native_document_data(doc)
        analysis = self.analyze_numbered_citations(doc, bibliography_heading=bibliography_heading)
        if analysis["bibliographyHeadingParagraphIndex"] is None:
            raise BridgeError(f"未找到参考文献标题段落: {bibliography_heading}")
        if analysis["badCitationNumbers"]:
            raise BridgeError(f"正文引用编号超出参考文献范围: {analysis['badCitationNumbers']}")

        planned_markers = analysis["citationMarkers"]
        deleted_references = None
        if delete_static_references:
            deleted_references = self.delete_static_references_after_heading(
                doc,
                bibliography_heading=bibliography_heading,
            )

        heading_index = self._find_heading_paragraph_index(doc, bibliography_heading)
        if heading_index is None:
            raise BridgeError(f"未找到参考文献标题段落: {bibliography_heading}")
        body_start = 0

        inserted_citations: List[Dict[str, Any]] = []
        for index, marker in enumerate(planned_markers, start=1):
            raw = str(marker["raw"])
            keys = self._citation_keys_for_numbers(citation_map, marker["numbers"])
            heading_index = self._find_heading_paragraph_index(doc, bibliography_heading)
            if heading_index is None:
                raise BridgeError(f"未找到参考文献标题段落: {bibliography_heading}")
            heading_paragraph = self._paragraph(doc, heading_index)
            body_end = int(self._retry_word_call(lambda: heading_paragraph.Range.Start))
            found = self._find_text_range(doc, raw, body_start, body_end)
            if found is None:
                raise BridgeError(f"未找到待替换引用标记: {raw}")
            start, end = int(found.Start), int(found.End)
            doc.Range(start, end).Text = ""
            rng = doc.Range(start, start)
            code = citation_code_from_keys(keys, library_id=library_id)
            payload = self._insert_native_field_at_range(doc, rng, code, FIELD_PLACEHOLDER)
            inserted_citations.append(
                {
                    "index": index,
                    "raw": raw,
                    "numbers": marker["numbers"],
                    "keys": keys,
                    "field": payload,
                }
            )

        bibliography_payload = None
        if insert_bibliography:
            bibliography_payload = self.insert_native_bibliography_after_heading(
                doc,
                bibliography_heading=bibliography_heading,
            )
        self.save_document(doc)
        return {
            "analysis": analysis,
            "deletedReferences": deleted_references,
            "insertedCitationCount": len(inserted_citations),
            "insertedCitations": inserted_citations,
            "bibliography": bibliography_payload,
        }

    def validate_zotero_document(
        self,
        doc: Any,
        bibliography_heading: str = "References",
    ) -> Dict[str, Any]:
        fields = self.list_native_fields(doc)
        citation_fields = [field for field in fields if field.get("kind") == "citation"]
        bibliography_fields = [field for field in fields if field.get("kind") == "bibliography"]
        placeholders = [
            field
            for field in fields
            if (field.get("text") or "").strip() in {FIELD_PLACEHOLDER, BIBL_PLACEHOLDER}
        ]

        heading_index = self._find_heading_paragraph_index(doc, bibliography_heading)
        bibliography_paragraphs: List[Dict[str, Any]] = []
        paragraph_count = self._paragraph_count(doc)
        for paragraph_index in range(1, paragraph_count + 1):
            paragraph = self._paragraph(doc, paragraph_index)
            kinds = self._paragraph_native_field_kinds(paragraph)
            if "bibliography" not in kinds:
                continue
            text = self._paragraph_text(paragraph)
            bibliography_paragraphs.append(
                {
                    "paragraphIndex": paragraph_index,
                    "textStart": text[:200],
                    "textLength": len(text),
                    "sharesHeadingParagraph": (
                        heading_index == paragraph_index
                        and text.casefold().startswith(bibliography_heading.casefold())
                    ),
                    "afterHeading": bool(heading_index and paragraph_index > heading_index),
                }
            )

        bibliography_starts_after_heading = (
            bool(bibliography_paragraphs)
            and heading_index is not None
            and bibliography_paragraphs[0]["paragraphIndex"] == heading_index + 1
            and not bibliography_paragraphs[0]["sharesHeadingParagraph"]
        )

        return {
            "fieldCount": len(fields),
            "citationFieldCount": len(citation_fields),
            "bibliographyFieldCount": len(bibliography_fields),
            "placeholderCount": len(placeholders),
            "allResolved": len(placeholders) == 0,
            "bibliographyHeading": bibliography_heading,
            "bibliographyHeadingParagraphIndex": heading_index,
            "bibliographyParagraphs": bibliography_paragraphs,
            "bibliographyAfterHeading": bibliography_starts_after_heading,
            "fields": fields,
        }

    def _insert_native_field_at_range(self, doc: Any, rng: Any, code: str, placeholder: str) -> Dict[str, Any]:
        field = doc.Fields.Add(rng, WORD_FIELD_QUOTE, FIELD_PLACEHOLDER, True)
        field.Code.Text = self._native_field_code(code)
        field.Result.Text = placeholder
        payload = {
            "type": int(field.Type),
            "code": code,
            "text": str(field.Result.Text or ""),
        }
        log_debug(f"Inserted native field kind={'bibliography' if code.startswith('BIBL') else 'citation'}")
        return payload

    def insert_native_citation(
        self,
        doc: Any,
        keys: Iterable[str],
        library_id: int = 1,
        find_text: Optional[str] = None,
        placement: str = "current",
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.ensure_native_document_data(doc)
        rng = self.resolve_insert_range(doc, find_text=find_text, placement=placement)
        code = citation_code_from_keys(keys, library_id=library_id, prefix=prefix, suffix=suffix)
        payload = self._insert_native_field_at_range(doc, rng, code, FIELD_PLACEHOLDER)
        self.save_document(doc)
        return payload

    def insert_native_bibliography(
        self,
        doc: Any,
        find_text: Optional[str] = None,
        placement: str = "current",
    ) -> Dict[str, Any]:
        self.ensure_native_document_data(doc)
        rng = self.resolve_insert_range(doc, find_text=find_text, placement=placement)
        payload = self._insert_native_field_at_range(doc, rng, empty_bibliography_code(), BIBL_PLACEHOLDER)
        self.save_document(doc)
        return payload

    def trigger_zotero_macro(self, doc: Any, command: str) -> Dict[str, Any]:
        macro = MACRO_MAP.get(command)
        if not macro:
            raise BridgeError(f"不支持的 Zotero Word 宏命令: {command}")
        self.activate_document(doc, make_visible=True)
        self.app.Run(macro)
        log_debug(f"Triggered Zotero macro command={command}")
        return {"command": command, "macro": macro, "sent": True}

    def _native_field_status(self, doc: Any) -> Dict[str, Any]:
        statuses: List[Dict[str, Any]] = []
        citation_placeholders = 0
        bibliography_placeholders = 0

        for payload in self.list_native_fields(doc):
            result_text = (payload.get("text") or "").strip()
            code_text = payload.get("code") or ""
            code_type = payload.get("kind") or ""
            status = {
                "index": payload.get("index"),
                "type": code_type,
                "resultText": result_text,
                "isPlaceholder": False,
            }
            if code_type == "citation" and result_text == FIELD_PLACEHOLDER:
                citation_placeholders += 1
                status["isPlaceholder"] = True
            elif code_type == "bibliography" and result_text == BIBL_PLACEHOLDER:
                bibliography_placeholders += 1
                status["isPlaceholder"] = True
            elif not result_text and code_text:
                status["isPlaceholder"] = True
            statuses.append(status)

        return {
            "fields": statuses,
            "total": len(statuses),
            "citationPlaceholders": citation_placeholders,
            "bibliographyPlaceholders": bibliography_placeholders,
            "allResolved": citation_placeholders == 0 and bibliography_placeholders == 0 and bool(statuses),
        }

    def wait_until_word_accessible(self, doc: Any, timeout_sec: float = 15.0) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                _ = doc.Fields.Count
                return True
            except pywintypes.com_error as exc:
                if exc.args and exc.args[0] == RPC_E_CALL_REJECTED:
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.5)
                    continue
                raise
        return False

    def wait_for_refresh_completion(
        self,
        doc: Any,
        timeout_sec: float = 90.0,
        poll_interval_sec: float = 1.0,
        baseline_signature: Optional[List[tuple]] = None,
        min_resolved_wait_sec: float = 0.0,
        stable_window_sec: float = 1.5,
    ) -> Dict[str, Any]:
        deadline = time.time() + timeout_sec
        start_time = time.time()
        last_status: Dict[str, Any] = {"fields": [], "total": 0, "citationPlaceholders": 0, "bibliographyPlaceholders": 0, "allResolved": False}
        last_signature: Optional[List[tuple]] = None
        stable_since: Optional[float] = None
        observed_change = False

        while time.time() < deadline:
            try:
                last_status = self._native_field_status(doc)
                current_signature = self._field_result_signature(doc)
                now = time.time()
                if last_signature != current_signature:
                    last_signature = current_signature
                    stable_since = now
                if baseline_signature is not None and current_signature != baseline_signature:
                    observed_change = True
                if last_status["allResolved"] and stable_since is not None:
                    elapsed = now - start_time
                    stable_for = now - stable_since
                    ready = elapsed >= min_resolved_wait_sec
                    if observed_change:
                        ready = ready and stable_for >= stable_window_sec
                    else:
                        ready = ready and stable_for >= min(stable_window_sec, 1.0)
                    if not ready:
                        time.sleep(poll_interval_sec)
                        continue
                    save_error = None
                    save_attempted = False
                    try:
                        self.save_document(doc)
                        save_attempted = True
                    except Exception as exc:
                        save_attempted = True
                        save_error = str(exc)
                    last_status["completed"] = True
                    last_status["timedOut"] = False
                    last_status["saveAttempted"] = save_attempted
                    last_status["saveError"] = save_error
                    return last_status
            except pywintypes.com_error as exc:
                if exc.args and exc.args[0] == RPC_E_CALL_REJECTED:
                    pythoncom.PumpWaitingMessages()
                else:
                    raise
            time.sleep(poll_interval_sec)

        last_status["completed"] = False
        last_status["timedOut"] = True
        last_status["saveAttempted"] = False
        last_status["saveError"] = None
        return last_status


class _ProbeListNode(ctypes.Structure):
    pass


_ProbeListNode._fields_ = [("value", ctypes.c_void_p), ("next", ctypes.POINTER(_ProbeListNode))]


@dataclass
class NativeProbeResult:
    doc_data: str
    fields: List[Dict[str, Any]]


class WinWordIntegrationProbe:
    def __init__(self, dll_path: Path = WORD_INTEGRATION_DLL) -> None:
        if not dll_path.exists():
            raise BridgeError(f"找不到 Word 集成 DLL: {dll_path}")
        self.dll = ctypes.WinDLL(str(dll_path))
        self._setup_signatures()

    def _setup_signatures(self) -> None:
        self.document_p = ctypes.c_void_p
        self.field_p = ctypes.c_void_p
        self.listnode_p = ctypes.POINTER(_ProbeListNode)

        self.dll.getDocument.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(self.document_p)]
        self.dll.getDocument.restype = ctypes.c_ushort
        self.dll.freeDocument.argtypes = [self.document_p]
        self.dll.freeDocument.restype = None
        self.dll.getDocumentData.argtypes = [self.document_p, ctypes.POINTER(ctypes.c_void_p)]
        self.dll.getDocumentData.restype = ctypes.c_ushort
        self.dll.getFields.argtypes = [self.document_p, ctypes.c_wchar_p, ctypes.POINTER(self.listnode_p)]
        self.dll.getFields.restype = ctypes.c_ushort
        self.dll.getText.argtypes = [self.field_p, ctypes.POINTER(ctypes.c_void_p)]
        self.dll.getText.restype = ctypes.c_ushort
        self.dll.getNoteIndex.argtypes = [self.field_p, ctypes.POINTER(ctypes.c_ulong)]
        self.dll.getNoteIndex.restype = ctypes.c_ushort
        self.dll.freeData.argtypes = [ctypes.c_void_p]
        self.dll.freeData.restype = None
        self.dll.getError.argtypes = []
        self.dll.getError.restype = ctypes.c_wchar_p
        self.dll.clearError.argtypes = []
        self.dll.clearError.restype = None

    def _check(self, status: int, label: str) -> None:
        if status == 0:
            return
        err = None
        try:
            err = self.dll.getError()
            self.dll.clearError()
        except Exception:
            err = None
        if err:
            raise BridgeError(f"{label} 失败: {err}")
        raise BridgeError(f"{label} 失败，状态码 {status}")

    def probe(self, doc_path: str) -> NativeProbeResult:
        doc_ptr = self.document_p()
        self._check(self.dll.getDocument(doc_path, ctypes.byref(doc_ptr)), "getDocument")
        doc_data_ptr = ctypes.c_void_p()
        self._check(self.dll.getDocumentData(doc_ptr, ctypes.byref(doc_data_ptr)), "getDocumentData")
        doc_data = ctypes.wstring_at(doc_data_ptr)
        self.dll.freeData(doc_data_ptr)

        field_list = self.listnode_p()
        self._check(self.dll.getFields(doc_ptr, "Field", ctypes.byref(field_list)), "getFields")

        fields: List[Dict[str, Any]] = []
        node = field_list
        index = 0
        while bool(node):
            index += 1
            field_ptr = self.field_p(node.contents.value)
            text_ptr = ctypes.c_void_p()
            self._check(self.dll.getText(field_ptr, ctypes.byref(text_ptr)), f"getText[{index}]")
            text = ctypes.wstring_at(text_ptr)
            self.dll.freeData(text_ptr)
            note_index = ctypes.c_ulong()
            self._check(self.dll.getNoteIndex(field_ptr, ctypes.byref(note_index)), f"getNoteIndex[{index}]")
            fields.append(
                {
                    "index": index,
                    "text": text,
                    "noteIndex": int(note_index.value),
                }
            )
            node = node.contents.next
        # NOTE:
        # The native DLL occasionally corrupts the process heap when freeDocument()
        # is called from Python/ctypes after field enumeration. Since this probe is
        # intended for short-lived CLI diagnostics, we intentionally skip that call.
        return NativeProbeResult(doc_data=doc_data, fields=fields)


def run_refresh_cycle(bridge: NativeWordBridge, doc: Any, wait_seconds: float) -> Dict[str, Any]:
    bridge.ensure_native_document_data(doc)
    before_status = bridge._native_field_status(doc)
    before_signature = bridge._field_result_signature(doc)
    result = bridge.trigger_zotero_macro(doc, "refresh")
    wait_ok = None
    after_status = None
    if wait_seconds and wait_seconds > 0:
        wait_ok = bridge.wait_until_word_accessible(doc, timeout_sec=wait_seconds)
        after_status = bridge.wait_for_refresh_completion(
            doc,
            timeout_sec=max(wait_seconds, 60),
            baseline_signature=before_signature,
            min_resolved_wait_sec=8.0 if before_status["allResolved"] else 0.0,
        )
    return {
        "before": before_status,
        "refresh": result,
        "waitSucceeded": wait_ok,
        "after": after_status,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Native Word-Zotero bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_doc_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--doc", required=True, help="目标 Word 文档路径")
        p.add_argument("--style-id", default=None, help="Zotero CSL style ID")
        p.add_argument("--find", default=None, help="定位文本")
        p.add_argument(
            "--placement",
            choices=["current", "end", "before", "after", "replace"],
            default="current",
            help="插入位置",
        )
        p.add_argument("--refresh-after", action="store_true", help="插入后立即触发 Zotero Refresh")
        p.add_argument("--wait-seconds", type=float, default=90.0, help="插入后自动 Refresh 的最长等待秒数")

    p_insert = subparsers.add_parser("insert-citation", help="插入原生 Zotero 引文字段")
    add_doc_options(p_insert)
    p_insert.add_argument("--keys", nargs="+", required=True, help="Zotero 条目 key")
    p_insert.add_argument("--library-id", type=int, default=1, help="Zotero libraryID")
    p_insert.add_argument("--prefix", default=None, help="引文前缀")
    p_insert.add_argument("--suffix", default=None, help="引文后缀")

    p_bib = subparsers.add_parser("insert-bibliography", help="插入原生 Zotero 参考文献字段")
    add_doc_options(p_bib)

    p_refresh = subparsers.add_parser("refresh", help="触发 Zotero 官方 Word 刷新")
    p_refresh.add_argument("--doc", required=True, help="目标 Word 文档路径")
    p_refresh.add_argument("--wait-seconds", type=float, default=90.0, help="发送刷新后等待完成的最长秒数")

    p_probe = subparsers.add_parser("probe", help="用官方 Word 集成 DLL 探测文档")
    p_probe.add_argument("--doc", required=True, help="目标 Word 文档路径")

    p_list = subparsers.add_parser("list-fields", help="列出文档中的原生 Zotero 字段")
    p_list.add_argument("--doc", required=True, help="目标 Word 文档路径")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    doc_path = normalize_path(args.doc)

    if args.command == "probe":
        with NativeWordBridge() as bridge:
            doc = bridge.get_document(doc_path)
            bridge.activate_document(doc, make_visible=False)
            result = WinWordIntegrationProbe().probe(doc_path)
            print(
                json.dumps(
                    {
                        "doc": doc_path,
                        "docData": result.doc_data,
                        "recognizedFields": result.fields,
                        "recognizedFieldCount": len(result.fields),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

    with NativeWordBridge() as bridge:
        doc = bridge.get_document(doc_path)
        show_doc = bool(getattr(args, "placement", "") == "current" and args.command in {"insert-citation", "insert-bibliography"})
        bridge.activate_document(doc, make_visible=show_doc or args.command == "refresh")

        if args.command == "insert-citation":
            if args.style_id:
                bridge.update_native_document_style(doc, args.style_id)
            else:
                bridge.ensure_native_document_data(doc)
            payload = bridge.insert_native_citation(
                doc,
                keys=args.keys,
                library_id=args.library_id,
                find_text=args.find,
                placement=args.placement,
                prefix=args.prefix,
                suffix=args.suffix,
            )
            refresh_result = None
            if args.refresh_after:
                refresh_result = run_refresh_cycle(bridge, doc, args.wait_seconds)
            print(
                json.dumps(
                    {
                        "inserted": payload,
                        "doc": doc_path,
                        "refreshAfter": refresh_result,
                        "nativeFields": bridge.list_native_fields(doc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "insert-bibliography":
            if args.style_id:
                bridge.update_native_document_style(doc, args.style_id)
            else:
                bridge.ensure_native_document_data(doc)
            payload = bridge.insert_native_bibliography(doc, find_text=args.find, placement=args.placement)
            refresh_result = None
            if args.refresh_after:
                refresh_result = run_refresh_cycle(bridge, doc, args.wait_seconds)
            print(
                json.dumps(
                    {
                        "inserted": payload,
                        "doc": doc_path,
                        "refreshAfter": refresh_result,
                        "nativeFields": bridge.list_native_fields(doc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "refresh":
            refresh_result = run_refresh_cycle(bridge, doc, args.wait_seconds)
            print(
                json.dumps(
                    {
                        "doc": doc_path,
                        **refresh_result,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "list-fields":
            bridge.ensure_native_document_data(doc)
            print(
                json.dumps(
                    {
                        "doc": doc_path,
                        "nativeFields": bridge.list_native_fields(doc),
                        "documentData": bridge.load_native_document_data(doc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BridgeError as exc:
        print(str(exc))
        raise SystemExit(1)
