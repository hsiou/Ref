# -*- coding: utf-8 -*-
"""写入2024+论文被引次数，并提取河南省眼科学与视觉科学重点实验室论文副本。

输入：
  outputs/论文_2024年之后.xlsx            上一轮生成的2024后论文表
  outputs/citation_openalex_s2.json      OpenAlex/Semantic Scholar 被引数（DOI 匹配）
  outputs/pubmed_verified.json           PubMed 记录（含作者单位）
输出（就地更新 + 新副本）：
  outputs/论文_2024年之后.xlsx                       填写他引次数列（带来源批注）
  outputs/论文_2024年之后_河南省眼科学与视觉科学重点实验室.xlsx
"""
import json
import re
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
TABLE = OUT / "论文_2024年之后.xlsx"
EXTRACT = OUT / "论文_2024年之后_河南省眼科学与视觉科学重点实验室.xlsx"

# 重点实验室英文署名变体（含 Vision Science 少写 Visual 的变体）
LAB_RE = re.compile(r"Henan Key Laboratory (?:of|for) Ophthalmology and Vis")


def load_aux():
    cites = json.loads((OUT / "citation_openalex_s2.json").read_text(encoding="utf-8"))
    by_doi = {v["doi"].lower(): v for v in cites.values()}
    pubmed = json.loads((OUT / "pubmed_verified.json").read_text(encoding="utf-8"))
    aff_by_title = {}
    for r in pubmed:
        affs = " ".join(a.get("affiliation") or "" for a in r.get("authors", []))
        aff_by_title[r["title"]] = affs
    return by_doi, aff_by_title


def main() -> None:
    by_doi, aff_by_title = load_aux()
    wb = openpyxl.load_workbook(TABLE)
    ws = wb.active

    doi_by_title = {}
    pubmed = json.loads((OUT / "pubmed_verified.json").read_text(encoding="utf-8"))
    for r in pubmed:
        if r.get("year") and int(r["year"]) >= 2024:
            doi_by_title[r["title"]] = (r.get("doi") or "").lower()

    keep_rows = []
    for row in ws.iter_rows(min_row=2):
        title = str(row[2].value or "")
        cite_cell = row[6]  # 他引次数/或出版数量
        if title in doi_by_title and doi_by_title[title] in by_doi:
            item = by_doi[doi_by_title[title]]
            oa, s2 = item.get("openalex_cited"), item.get("s2_cited")
            val = oa if oa is not None else s2
            src = "OpenAlex" if oa is not None else "Semantic Scholar"
            note = f"来源：{src}（2026-10-29 按 DOI 查询）"
            if oa is not None and s2 is not None and oa != s2:
                note += f"；Semantic Scholar 为 {s2}"
            cite_cell.value = val
            cite_cell.comment = Comment(note, "citation-check")
        else:
            cite_cell.comment = Comment(
                "未获取：Google Scholar 本环境不可用（代理出口被拦截）；"
                "OpenAlex/Semantic Scholar 未收录该中文文献；CNKI 详情页反爬 403。",
                "citation-check",
            )
        affs = aff_by_title.get(title, "")
        if LAB_RE.search(affs):
            keep_rows.append([c.value for c in row])

    updated_table = TABLE
    try:
        wb.save(TABLE)
        print(f"updated {TABLE.name}, rows={ws.max_row - 1}")
    except PermissionError:
        # 目标文件被 Excel/WPS 锁定时，写入带后缀的新文件，避免打扰用户
        updated_table = TABLE.with_name("论文_2024年之后_已填被引.xlsx")
        wb.save(updated_table)
        print(f"locked, wrote {updated_table.name} instead, rows={ws.max_row - 1}")

    wb2 = openpyxl.load_workbook(updated_table)
    ws2 = wb2.active
    if ws2.max_row > 1:
        ws2.delete_rows(2, ws2.max_row - 1)
    for i, values in enumerate(keep_rows, start=1):
        ws2.append([i] + values[1:])
    wb2.save(EXTRACT)
    print(f"wrote {EXTRACT.name}: {len(keep_rows)} rows")


if __name__ == "__main__":
    main()
