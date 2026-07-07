#!/usr/bin/env python3
"""将PubMed检索结果添加到Zotero。

用法:
    python add_to_zotero.py --input papers.json --collection "同事/李志杰"
    python add_to_zotero.py --input papers.json --collection "同事/李志杰" --dry-run
    python add_to_zotero.py --input papers.json --collection "同事/李志杰" --api-key XXX --library-id 12345
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# ── 默认配置 ──────────────────────────────────────────────────────────────────

DEFAULT_API_KEY = os.environ.get("ZOTERO_API_KEY", "")
DEFAULT_LIBRARY_ID = os.environ.get("ZOTERO_LIBRARY_ID", "")
DEFAULT_BATCH_SIZE = 10  # 每批创建的条目数
DEFAULT_RETRY_COUNT = 3  # 重试次数
DEFAULT_RETRY_DELAY = 1  # 重试间隔（秒）


# ── Zotero API 客户端 ─────────────────────────────────────────────────────────

class ZoteroClient:
    """Zotero Web API 客户端。"""
    
    API_BASE = "https://api.zotero.org"
    
    def __init__(self, api_key: str, library_id: str):
        self.api_key = api_key
        self.library_id = library_id
    
    def _request(self, method: str, path: str, body=None, timeout: int = 30) -> dict:
        """发送API请求。"""
        url = f"{self.API_BASE}{path}"
        headers = {
            "Zotero-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8")
            if response_body:
                return json.loads(response_body)
            return {}
    
    def list_collections(self, limit: int = 100) -> list[dict]:
        """列出所有集合。"""
        return self._request("GET", f"/users/{self.library_id}/collections?limit={limit}")
    
    def find_collection(self, name: str, parent_key: str = None) -> str:
        """查找集合。"""
        collections = self.list_collections(limit=100)
        for coll in collections:
            data = coll.get("data", {})
            if data.get("name") == name:
                if parent_key is None or data.get("parentCollection") == parent_key:
                    return data.get("key")
        return None
    
    def find_or_create_collection(self, path: str) -> str:
        """查找或创建集合路径。"""
        parts = [p for p in path.split("/") if p]
        parent_key = None
        
        for part in parts:
            found = self.find_collection(part, parent_key)
            if found:
                parent_key = found
            else:
                # 创建新集合
                coll_data = {"name": part}
                if parent_key:
                    coll_data["parentCollection"] = parent_key
                result = self._request("POST", f"/users/{self.library_id}/collections", [coll_data])
                if "success" in result:
                    parent_key = next(iter(result["success"].values()))
                else:
                    raise RuntimeError(f"创建集合失败: {result}")
        
        return parent_key
    
    def get_item_template(self, item_type: str = "journalArticle") -> dict:
        """获取item模板。"""
        return self._request("GET", f"/items/new?itemType={item_type}")
    
    def find_existing_item_by_pmid(self, pmid: str, collection_key: str = None) -> str:
        """通过PMID查找已存在的条目。

        优先从指定集合中查找，如果未指定则搜索整个库。
        """
        if collection_key:
            # 从指定集合中查找
            items = self.get_collection_items(collection_key, limit=100)
            for item in items:
                extra = item.get("data", {}).get("extra", "")
                if f"PMID: {pmid}" in extra:
                    return item.get("key")
        else:
            # 搜索整个库
            try:
                result = self._request("GET", f"/users/{self.library_id}/items?q={pmid}&qmode=everything&limit=10")
                if isinstance(result, list):
                    for item in result:
                        extra = item.get("data", {}).get("extra", "")
                        if f"PMID: {pmid}" in extra:
                            return item.get("key")
            except Exception:
                pass
        return None
    
    def get_all_collection_pmids(self, collection_key: str) -> set[str]:
        """获取集合中所有论文的PMID。"""
        pmids = set()
        items = self.get_collection_items(collection_key, limit=100)
        for item in items:
            extra = item.get("data", {}).get("extra", "")
            if "PMID:" in extra:
                pmid = extra.split("PMID:")[1].split("\n")[0].strip()
                pmids.add(pmid)
        return pmids
    
    def create_items_batch(self, items: list[dict]) -> dict:
        """批量创建条目。"""
        result = self._request("POST", f"/users/{self.library_id}/items", items)
        return result
    
    def create_item(self, item_data: dict) -> str:
        """创建单个条目。"""
        result = self.create_items_batch([item_data])
        
        if "success" in result:
            return next(iter(result["success"].values()))
        elif "successful" in result:
            first_item = next(iter(result["successful"].values()))
            return first_item.get("key")
        
        raise RuntimeError(f"创建条目失败: {result}")
    
    def get_collection_items(self, collection_key: str, limit: int = 100) -> list[dict]:
        """获取集合中的所有条目。"""
        return self._request("GET", f"/users/{self.library_id}/collections/{collection_key}/items?limit={limit}")
    
    def merge_duplicates(self, duplicate_keys: list[str], target_key: str) -> bool:
        """合并重复条目。"""
        try:
            # 获取目标条目
            target = self._request("GET", f"/users/{self.library_id}/items/{target_key}")
            target_data = target.get("data", {})
            
            # 删除其他重复条目
            for key in duplicate_keys:
                if key != target_key:
                    try:
                        self._request("DELETE", f"/users/{self.library_id}/items/{key}")
                    except Exception:
                        pass
            
            return True
        except Exception:
            return False


# ── 输入验证 ──────────────────────────────────────────────────────────────────

def validate_paper(paper: dict) -> tuple[bool, str]:
    """验证论文数据。"""
    if not paper.get("pmid"):
        return False, "缺少 PMID"
    if not paper.get("title"):
        return False, "缺少标题"
    return True, ""


def validate_input_file(file_path: str) -> list[dict]:
    """验证并读取输入文件。"""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 格式错误: {e}")
    
    if not isinstance(data, list):
        raise ValueError("输入文件必须是 JSON 数组")
    
    # 验证每条记录
    valid_papers = []
    invalid_count = 0
    for i, paper in enumerate(data):
        is_valid, error = validate_paper(paper)
        if is_valid:
            valid_papers.append(paper)
        else:
            invalid_count += 1
            print(f"  警告: 第 {i+1} 条记录无效: {error}")
    
    if invalid_count > 0:
        print(f"  跳过 {invalid_count} 条无效记录")
    
    return valid_papers


# ── 转换函数 ──────────────────────────────────────────────────────────────────

def paper_to_zotero_item(paper: dict, template: dict, collection_key: str) -> dict:
    """将PubMed论文转换为Zotero item。"""
    item = template.copy()
    
    # 基本信息
    item["title"] = paper.get("title", "")
    
    # 作者
    authors = paper.get("authors", [])
    creators = []
    for author in authors:
        last_name = author.get("last_name", "")
        first_name = author.get("fore_name", "")
        if last_name:
            creators.append({
                "creatorType": "author",
                "firstName": first_name,
                "lastName": last_name,
            })
    item["creators"] = creators
    
    # 日期
    pub_date = paper.get("pub_date", "")
    if pub_date:
        item["date"] = pub_date[:10] if len(pub_date) >= 10 else pub_date
    
    # 期刊
    item["publicationTitle"] = paper.get("journal", "")
    
    # 卷号、期号、页码
    item["volume"] = paper.get("volume", "")
    item["issue"] = paper.get("issue", "")
    item["pages"] = paper.get("pages", "")
    
    # DOI
    item["DOI"] = paper.get("doi", "")
    
    # 摘要
    item["abstractNote"] = paper.get("abstract", "")
    
    # PMID 和 URL
    pmid = paper.get("pmid", "")
    item["extra"] = f"PMID: {pmid}"
    item["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    
    # 设置集合
    item["collections"] = [collection_key]
    
    return item


# ── 主函数 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="将PubMed检索结果添加到Zotero",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --input papers.json --collection "同事/李志杰"
  %(prog)s --input papers.json --collection "同事/李志杰" --dry-run
  %(prog)s --input papers.json --collection "同事/李志杰" --batch-size 20
        """
    )
    parser.add_argument("--input", "-i", required=True, help="输入JSON文件路径")
    parser.add_argument("--collection", "-c", required=True, help="Zotero目标集合路径（如 '同事/李志杰'）")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Zotero API密钥（或设置 ZOTERO_API_KEY 环境变量）")
    parser.add_argument("--library-id", default=DEFAULT_LIBRARY_ID, help="Zotero Library ID（或设置 ZOTERO_LIBRARY_ID 环境变量）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际写入")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"每批创建的条目数（默认 {DEFAULT_BATCH_SIZE}）")
    parser.add_argument("--retry", type=int, default=DEFAULT_RETRY_COUNT, help=f"重试次数（默认 {DEFAULT_RETRY_COUNT}）")
    parser.add_argument("--log", help="日志文件路径（可选）")
    
    args = parser.parse_args()
    
    # 验证凭证
    if not args.api_key:
        print("错误: 请提供 --api-key 或设置 ZOTERO_API_KEY 环境变量")
        sys.exit(1)
    if not args.library_id:
        print("错误: 请提供 --library-id 或设置 ZOTERO_LIBRARY_ID 环境变量")
        sys.exit(1)
    
    # 读取并验证输入文件
    print(f"1. 读取输入文件: {args.input}")
    try:
        papers = validate_input_file(args.input)
    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)
    print(f"   有效论文: {len(papers)} 篇")
    
    # 初始化客户端
    zotero = ZoteroClient(args.api_key, args.library_id)
    
    # 获取或创建集合
    print(f"\n2. 准备目标集合: {args.collection}")
    try:
        collection_key = zotero.find_or_create_collection(args.collection)
        print(f"   集合 key: {collection_key}")
    except Exception as e:
        print(f"错误: 无法创建目标集合: {e}")
        sys.exit(1)
    
    # 获取模板
    template = zotero.get_item_template("journalArticle")
    
    # 检查重复
    print(f"\n3. 检查重复...")
    existing_pmids = zotero.get_all_collection_pmids(collection_key)
    print(f"   集合中已有 {len(existing_pmids)} 篇论文")
    
    need_to_add = []
    already_exists = 0
    for paper in papers:
        pmid = paper.get("pmid", "")
        if pmid and pmid in existing_pmids:
            already_exists += 1
            continue
        need_to_add.append(paper)
    print(f"   已存在: {already_exists} 篇")
    print(f"   需要添加: {len(need_to_add)} 篇")
    
    if not need_to_add:
        print("\n没有需要添加的论文")
        return
    
    # 预览模式
    if args.dry_run:
        print(f"\n=== 预览模式 (dry-run) ===")
        print(f"将添加 {len(need_to_add)} 篇论文到集合 '{args.collection}'")
        print("\n前5篇:")
        for i, paper in enumerate(need_to_add[:5]):
            title = paper.get("title", "")[:60]
            pmid = paper.get("pmid", "")
            print(f"  {i+1}. [{pmid}] {title}...")
        if len(need_to_add) > 5:
            print(f"  ... 还有 {len(need_to_add) - 5} 篇")
        return
    
    # 批量添加
    print(f"\n4. 批量添加到 Zotero...")
    success_count = 0
    skip_count = 0
    error_count = 0
    failed_pmids = []
    
    start_time = time.time()
    
    for i in range(0, len(need_to_add), args.batch_size):
        batch = need_to_add[i:i + args.batch_size]
        batch_items = []
        
        for paper in batch:
            try:
                item = paper_to_zotero_item(paper, template, collection_key)
                batch_items.append(item)
            except Exception as e:
                pmid = paper.get("pmid", "unknown")
                print(f"   [{pmid}] 转换失败: {e}")
                error_count += 1
                failed_pmids.append(pmid)
        
        if not batch_items:
            continue
        
        # 重试机制
        for attempt in range(args.retry):
            try:
                result = zotero.create_items_batch(batch_items)
                
                # 处理结果
                if "success" in result:
                    for key in result["success"].values():
                        success_count += 1
                elif "successful" in result:
                    for item in result["successful"].values():
                        if isinstance(item, dict):
                            success_count += 1
                        else:
                            success_count += 1
                
                # 检查失败的
                if "failed" in result and result["failed"]:
                    for idx, error in result["failed"].items():
                        error_count += 1
                        batch_idx = int(idx)
                        if batch_idx < len(batch):
                            pmid = batch[batch_idx].get("pmid", "unknown")
                            failed_pmids.append(pmid)
                
                break  # 成功，退出重试循环
                
            except Exception as e:
                if attempt < args.retry - 1:
                    print(f"   批次 {i // args.batch_size + 1} 失败，重试 {attempt + 2}/{args.retry}...")
                    time.sleep(DEFAULT_RETRY_DELAY)
                else:
                    print(f"   批次 {i // args.batch_size + 1} 最终失败: {e}")
                    error_count += len(batch)
                    for paper in batch:
                        failed_pmids.append(paper.get("pmid", "unknown"))
        
        # 进度显示
        elapsed = time.time() - start_time
        processed = min(i + args.batch_size, len(need_to_add))
        progress = processed / len(need_to_add) * 100
        eta = (elapsed / processed) * (len(need_to_add) - processed) if processed > 0 else 0
        
        print(f"   进度: {processed}/{len(need_to_add)} ({progress:.1f}%) - 成功: {success_count}, 失败: {error_count} - ETA: {eta:.0f}秒")
        
        time.sleep(0.5)  # 避免速率限制
    
    # 汇总
    elapsed = time.time() - start_time
    print(f"\n=== 完成 ===")
    print(f"成功: {success_count}")
    print(f"跳过: {skip_count}")
    print(f"失败: {error_count}")
    print(f"耗时: {elapsed:.1f}秒")
    
    if failed_pmids:
        print(f"\n失败的PMID:")
        for pmid in failed_pmids:
            print(f"  - {pmid}")
    
    # 写入日志
    if args.log:
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "input_file": args.input,
            "collection": args.collection,
            "total_papers": len(papers),
            "already_exists": already_exists,
            "need_to_add": len(need_to_add),
            "success": success_count,
            "failed": error_count,
            "failed_pmids": failed_pmids,
            "elapsed_seconds": elapsed,
        }
        with open(args.log, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        print(f"\n日志已保存: {args.log}")


if __name__ == "__main__":
    main()
