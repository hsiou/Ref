from __future__ import annotations

import shutil
from typing import Any, Dict, List, Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    FastMCP = None

from .native_bridge import NativeWordBridge, WinWordIntegrationProbe, run_refresh_cycle
from .word_bridge import BridgeError, normalize_path


def _summarize_conversion(conversion: Dict[str, Any]) -> Dict[str, Any]:
    analysis = conversion.get("analysis") or {}
    deleted_references = conversion.get("deletedReferences") or {}
    bibliography = conversion.get("bibliography")
    return {
        "citationMarkerCount": analysis.get("citationMarkerCount"),
        "staticReferenceCount": analysis.get("staticReferenceCount"),
        "badCitationNumbers": analysis.get("badCitationNumbers", []),
        "deletedReferenceCount": deleted_references.get("deletedReferenceCount", 0),
        "insertedCitationCount": conversion.get("insertedCitationCount", 0),
        "bibliographyInserted": bibliography is not None,
        "bibliography": bibliography,
    }


def _summarize_validation(validation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fieldCount": validation.get("fieldCount"),
        "citationFieldCount": validation.get("citationFieldCount"),
        "bibliographyFieldCount": validation.get("bibliographyFieldCount"),
        "placeholderCount": validation.get("placeholderCount"),
        "allResolved": validation.get("allResolved"),
        "bibliographyAfterHeading": validation.get("bibliographyAfterHeading"),
        "bibliographyHeadingParagraphIndex": validation.get("bibliographyHeadingParagraphIndex"),
        "bibliographyParagraphs": validation.get("bibliographyParagraphs", []),
    }


def _require_fastmcp():
    if FastMCP is None:  # pragma: no cover
        raise RuntimeError(
            "未安装 mcp Python SDK。请先执行 `pip install \"mcp[cli]\"`。"
        )
    return FastMCP


def _open_doc(bridge: NativeWordBridge, doc_path: str, make_visible: bool = False):
    doc = bridge.get_document(normalize_path(doc_path))
    bridge.activate_document(doc, make_visible=make_visible)
    return doc


def create_server():
    fast_mcp = _require_fastmcp()
    mcp = fast_mcp("zotero-word-mcp")

    @mcp.tool()
    def insert_citation(
        doc: str,
        keys: List[str],
        find_text: Optional[str] = None,
        placement: str = "current",
        style_id: Optional[str] = None,
        library_id: int = 1,
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
        refresh_after: bool = True,
        wait_seconds: float = 90.0,
    ) -> Dict[str, Any]:
        """向 Word 文档插入 Zotero 原生引文字段，并可选自动刷新。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=(placement == "current" and not find_text))
            if style_id:
                bridge.update_native_document_style(doc_obj, style_id)
            else:
                bridge.ensure_native_document_data(doc_obj)
            inserted = bridge.insert_native_citation(
                doc_obj,
                keys=keys,
                library_id=library_id,
                find_text=find_text,
                placement=placement,
                prefix=prefix,
                suffix=suffix,
            )
            refresh_result = None
            if refresh_after:
                refresh_result = run_refresh_cycle(bridge, doc_obj, wait_seconds)
            return {
                "doc": normalize_path(doc),
                "inserted": inserted,
                "refresh": refresh_result,
                "fields": bridge.list_native_fields(doc_obj),
            }

    @mcp.tool()
    def insert_bibliography(
        doc: str,
        find_text: Optional[str] = None,
        placement: str = "end",
        style_id: Optional[str] = None,
        refresh_after: bool = True,
        wait_seconds: float = 90.0,
    ) -> Dict[str, Any]:
        """向 Word 文档插入 Zotero 原生参考文献字段。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=(placement == "current" and not find_text))
            if style_id:
                bridge.update_native_document_style(doc_obj, style_id)
            else:
                bridge.ensure_native_document_data(doc_obj)
            inserted = bridge.insert_native_bibliography(
                doc_obj,
                find_text=find_text,
                placement=placement,
            )
            refresh_result = None
            if refresh_after:
                refresh_result = run_refresh_cycle(bridge, doc_obj, wait_seconds)
            return {
                "doc": normalize_path(doc),
                "inserted": inserted,
                "refresh": refresh_result,
                "fields": bridge.list_native_fields(doc_obj),
            }

    @mcp.tool()
    def refresh_document(doc: str, wait_seconds: float = 90.0) -> Dict[str, Any]:
        """触发 Zotero 官方 Word Refresh，并等待占位字段解析完成。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=True)
            return {
                "doc": normalize_path(doc),
                **run_refresh_cycle(bridge, doc_obj, wait_seconds),
            }

    @mcp.tool()
    def list_fields(doc: str) -> Dict[str, Any]:
        """列出文档中的 Zotero 原生字段及文档首选项。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=False)
            bridge.wait_until_word_accessible(doc_obj, timeout_sec=15.0)
            bridge.ensure_native_document_data(doc_obj)
            return {
                "doc": normalize_path(doc),
                "fields": bridge.list_native_fields(doc_obj),
                "documentData": bridge.load_native_document_data(doc_obj),
            }

    @mcp.tool()
    def set_document_style(doc: str, style_id: str, locale: str = "zh-CN") -> Dict[str, Any]:
        """设置文档的 Zotero CSL 样式，不立即刷新。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=False)
            data = bridge.update_native_document_style(doc_obj, style_id=style_id, locale=locale)
            bridge.save_document(doc_obj)
            return {
                "doc": normalize_path(doc),
                "documentData": data,
            }

    @mcp.tool()
    def analyze_numbered_citations(doc: str, bibliography_heading: str = "References") -> Dict[str, Any]:
        """分析 Word 中的数字方括号引用和静态参考文献列表，不修改文档。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=False)
            return {
                "doc": normalize_path(doc),
                **bridge.analyze_numbered_citations(
                    doc_obj,
                    bibliography_heading=bibliography_heading,
                ),
            }

    @mcp.tool()
    def convert_numbered_citations(
        doc: str,
        citation_map: Dict[str, Any],
        output_doc: Optional[str] = None,
        bibliography_heading: str = "References",
        library_id: int = 1,
        style_id: Optional[str] = None,
        locale: str = "zh-CN",
        delete_static_references: bool = True,
        insert_bibliography: bool = True,
        refresh_after: bool = True,
        wait_seconds: float = 90.0,
    ) -> Dict[str, Any]:
        """将 [1]、[1, 2]、[1-3] 这类数字引用批量替换成 Zotero 原生字段。"""
        target_doc = normalize_path(output_doc or doc)
        source_doc = normalize_path(doc)
        if output_doc and target_doc != source_doc:
            shutil.copy2(source_doc, target_doc)
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, target_doc, make_visible=False)
            if style_id:
                bridge.update_native_document_style(doc_obj, style_id=style_id, locale=locale)
            else:
                bridge.ensure_native_document_data(doc_obj, locale=locale)
            conversion = bridge.convert_numbered_citations(
                doc_obj,
                citation_map=citation_map,
                bibliography_heading=bibliography_heading,
                library_id=library_id,
                delete_static_references=delete_static_references,
                insert_bibliography=insert_bibliography,
            )
            refresh_result = None
            if refresh_after:
                refresh_result = run_refresh_cycle(bridge, doc_obj, wait_seconds)
            validation = bridge.validate_zotero_document(
                doc_obj,
                bibliography_heading=bibliography_heading,
            )
            return {
                "doc": target_doc,
                "sourceDoc": source_doc,
                "copiedToOutput": bool(output_doc and target_doc != source_doc),
                "conversion": _summarize_conversion(conversion),
                "refresh": refresh_result,
                "validation": _summarize_validation(validation),
            }

    @mcp.tool()
    def validate_zotero_document(doc: str, bibliography_heading: str = "References") -> Dict[str, Any]:
        """验证 Zotero 原生字段数量、占位符状态和 bibliography 是否位于参考文献标题后。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=False)
            bridge.ensure_native_document_data(doc_obj)
            return {
                "doc": normalize_path(doc),
                **bridge.validate_zotero_document(
                    doc_obj,
                    bibliography_heading=bibliography_heading,
                ),
            }

    @mcp.tool()
    def probe_document(doc: str) -> Dict[str, Any]:
        """使用 Zotero 官方 Word 集成 DLL 验证文档原生字段是否可识别。"""
        with NativeWordBridge() as bridge:
            doc_obj = _open_doc(bridge, doc, make_visible=False)
            del doc_obj
            result = WinWordIntegrationProbe().probe(normalize_path(doc))
            return {
                "doc": normalize_path(doc),
                "docData": result.doc_data,
                "recognizedFields": result.fields,
                "recognizedFieldCount": len(result.fields),
            }

    return mcp


def main() -> int:
    try:
        server = create_server()
        server.run()
    except BridgeError as exc:
        raise SystemExit(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
