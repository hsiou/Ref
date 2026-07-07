#!/usr/bin/env python3
"""EndNote → Zotero 迁移脚本：将指定文集的条目迁移到 Zotero。

用法:
    python endnote_to_zotero.py [--dry-run] [--group-name 李志杰教授] [--collection 同事/李志杰]

功能:
    1. 读取 EndNote SQLite 数据库
    2. 找到指定文集（group）的所有记录
    3. 转换为 BibTeX 格式
    4. 通过 Zotero Web API 写入指定集合
"""

import argparse
import sys
from pathlib import Path

from utils.endnote_reader import EndNoteReader
from utils.zotero_client import ZoteroClient
from utils.bibtex_converter import record_to_bibtex, bibtex_to_zotero_item


# ── 配置 ──────────────────────────────────────────────────────────────────────

ENDNOTE_SDB = Path(r"F:\我的坚果云\2、工作文档\文献\My_Library_20260312.Data\sdb\sdb.eni")


def main():
    parser = argparse.ArgumentParser(description="EndNote → Zotero 迁移工具")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际写入")
    parser.add_argument("--group-name", default="李志杰教授", help="EndNote 文集名称")
    parser.add_argument("--collection", default="同事/李志杰", help="Zotero 目标集合路径")
    parser.add_argument("--sdb-path", default=str(ENDNOTE_SDB), help="EndNote sdb.eni 路径")
    args = parser.parse_args()
    
    print("=== EndNote → Zotero 迁移 ===")
    print(f"源文集: {args.group_name}")
    print(f"目标集合: {args.collection}")
    print(f"数据库: {args.sdb_path}")
    print()
    
    # 连接 EndNote 数据库
    db_path = Path(args.sdb_path)
    if not db_path.exists():
        print(f"错误: 数据库文件不存在: {db_path}")
        sys.exit(1)
    
    with EndNoteReader(db_path) as reader:
        # 查找组
        print("1. 查找 EndNote 文集...")
        result = reader.find_group(args.group_name)
        
        if not result:
            print(f"错误: 未找到文集 '{args.group_name}'")
            sys.exit(1)
        
        group_id, record_ids = result
        print(f"   找到文集 (group_id={group_id})，包含 {len(record_ids)} 条记录")
        
        # 获取记录
        print("\n2. 读取记录...")
        records = reader.fetch_records(record_ids)
        print(f"   读取到 {len(records)} 条记录")
        
        # 生成 BibTeX
        print("\n3. 生成 BibTeX...")
        bibtex_entries = []
        for rec in records:
            bibtex = record_to_bibtex(rec)
            bibtex_entries.append(bibtex)
        
        # 保存到临时文件
        bib_path = db_path.parent / "endnote_export_temp.bib"
        with open(bib_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(bibtex_entries))
        print(f"   保存到: {bib_path}")
        
        if args.dry_run:
            print("\n=== 预览模式 (dry-run) ===")
            print(f"将导入 {len(bibtex_entries)} 条记录到 Zotero 集合 '{args.collection}'")
            print("\n前3条记录预览:")
            for i, bibtex in enumerate(bibtex_entries[:3]):
                print(f"\n--- 记录 {i+1} ---")
                print(bibtex[:300])
                if len(bibtex) > 300:
                    print("...")
            return
    
    # 写入 Zotero
    print("\n4. 写入 Zotero...")
    try:
        zotero = ZoteroClient.from_env()
    except ValueError as e:
        print(f"错误: {e}")
        sys.exit(1)
    
    # 创建或查找集合
    print(f"   创建集合: {args.collection}")
    try:
        collection_key = zotero.find_or_create_collection(args.collection)
        print(f"   集合 key: {collection_key}")
    except Exception as e:
        print(f"错误: 无法创建目标集合: {e}")
        sys.exit(1)
    
    # 获取模板
    template = zotero.get_item_template("journalArticle")
    
    # 逐条导入
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, bibtex in enumerate(bibtex_entries):
        try:
            # 转换为 Zotero item
            item = bibtex_to_zotero_item(bibtex, template)
            item["collections"] = [collection_key]
            
            # 提取 DOI 和 PMID 用于去重
            doi = item.get("DOI")
            pmid = None
            extra = item.get("extra", "")
            if "PMID:" in extra:
                pmid = extra.split("PMID:")[1].split("\n")[0].strip()
            
            # 检查重复
            existing_key = zotero.find_existing_item(doi=doi, pmid=pmid)
            if existing_key:
                print(f"   [{i+1}/{len(bibtex_entries)}] 跳过（已存在）: {existing_key}")
                skip_count += 1
                continue
            
            # 创建条目
            new_key = zotero.create_item(item)
            title = item.get("title", "")[:50]
            print(f"   [{i+1}/{len(bibtex_entries)}] 已创建: {new_key} - {title}")
            success_count += 1
            
        except Exception as e:
            error_msg = str(e)
            if error_msg:
                print(f"   [{i+1}/{len(bibtex_entries)}] 错误: {error_msg[:150]}")
            else:
                print(f"   [{i+1}/{len(bibtex_entries)}] 错误: (空错误信息)")
            error_count += 1
    
    # 汇总
    print(f"\n=== 迁移完成 ===")
    print(f"成功: {success_count}")
    print(f"跳过（已存在）: {skip_count}")
    print(f"失败: {error_count}")
    print(f"总计: {len(records)}")


if __name__ == "__main__":
    main()
