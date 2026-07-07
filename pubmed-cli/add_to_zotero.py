#!/usr/bin/env python3
"""将PubMed检索结果添加到Zotero。"""

import json
import os
import urllib.request
import urllib.parse
import time

API_KEY = os.environ.get("ZOTERO_API_KEY", "i4cjHUfuseWCRB84AkPobGdW")
LIBRARY_ID = os.environ.get("ZOTERO_LIBRARY_ID", "17365633")
COLLECTION_KEY = "6HAD68IE"  # 同事/李志杰 集合的key

def zotero_request(method, path, body=None, timeout=30):
    """发送Zotero API请求。"""
    url = f"https://api.zotero.org{path}"
    headers = {
        "Zotero-API-Key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_body = resp.read().decode("utf-8")
            if response_body:
                return json.loads(response_body)
            return {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(f"Zotero API error {e.code}: {error_body}")

def get_item_template(item_type="journalArticle"):
    """获取item模板。"""
    return zotero_request("GET", f"/items/new?itemType={item_type}")

def find_existing_item(pmid=None):
    """查找已存在的条目。"""
    if pmid:
        try:
            result = zotero_request("GET", f"/users/{LIBRARY_ID}/items?q={pmid}&qmode=everything&limit=10")
            if isinstance(result, list):
                for item in result:
                    extra = item.get("data", {}).get("extra", "")
                    if f"PMID: {pmid}" in extra:
                        return item.get("key")
        except Exception:
            pass
    return None

def create_item(item_data):
    """创建条目。"""
    result = zotero_request("POST", f"/users/{LIBRARY_ID}/items", [item_data])
    
    if "success" in result:
        return next(iter(result["success"].values()))
    elif "successful" in result:
        first_item = next(iter(result["successful"].values()))
        return first_item.get("key")
    
    raise RuntimeError(f"创建条目失败: {result}")

def paper_to_zotero_item(paper, template):
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
    item["collections"] = [COLLECTION_KEY]
    
    return item

def main():
    # 读取PubMed论文
    with open("li_zhijie_papers.json", "r", encoding="utf-8") as f:
        papers = json.load(f)
    
    print(f"PubMed检索到 {len(papers)} 篇论文")
    
    # 获取模板
    template = get_item_template("journalArticle")
    
    # 需要添加的PMIDs
    need_to_add = ['41186356', '39920996', '37682569', '35569517', '34415987', 
                   '33717118', '31434991', '31136724', '30470496', '30362583', 
                   '30032655', '29988115', '29463199', '27818315', '27611469', 
                   '26039076', '22695965', '17962453', '17216113', '17071583']
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for pmid in need_to_add:
        # 查找对应的论文
        paper = next((p for p in papers if p.get("pmid") == pmid), None)
        if not paper:
            print(f"[{pmid}] 未找到论文数据")
            error_count += 1
            continue
        
        # 检查是否已存在
        existing_key = find_existing_item(pmid=pmid)
        if existing_key:
            print(f"[{pmid}] 已存在: {existing_key}")
            skip_count += 1
            continue
        
        # 创建条目
        try:
            item = paper_to_zotero_item(paper, template)
            new_key = create_item(item)
            title = item.get("title", "")[:50]
            print(f"[{pmid}] 已创建: {new_key} - {title}")
            success_count += 1
            time.sleep(0.5)  # 避免速率限制
        except Exception as e:
            print(f"[{pmid}] 错误: {e}")
            error_count += 1
    
    print(f"\n=== 完成 ===")
    print(f"成功: {success_count}")
    print(f"跳过: {skip_count}")
    print(f"失败: {error_count}")

if __name__ == "__main__":
    main()
