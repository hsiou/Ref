"""Zotero API 客户端模块。

封装 Zotero Web API 的常用操作。
"""

import json
import os
import urllib.parse
import urllib.request
from typing import Optional


class ZoteroClient:
    """Zotero Web API 客户端。"""
    
    API_BASE = "https://api.zotero.org"
    
    def __init__(self, api_key: str, library_id: str):
        """初始化客户端。
        
        Args:
            api_key: Zotero API 密钥
            library_id: Zotero 用户/组 ID
        """
        self.api_key = api_key
        self.library_id = library_id
    
    @classmethod
    def from_env(cls) -> "ZoteroClient":
        """从环境变量创建客户端。"""
        api_key = os.environ.get("ZOTERO_API_KEY")
        library_id = os.environ.get("ZOTERO_LIBRARY_ID")
        if not api_key or not library_id:
            raise ValueError("请设置 ZOTERO_API_KEY 和 ZOTERO_LIBRARY_ID 环境变量")
        return cls(api_key, library_id)
    
    def _request(self, method: str, path: str, body=None, timeout: int = 30) -> dict:
        """发送 API 请求。
        
        Args:
            method: HTTP 方法（GET, POST, PUT, DELETE）
            path: API 路径
            body: 请求体（可选）
            timeout: 超时时间（秒）
            
        Returns:
            响应 JSON
        """
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
        
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                response_body = resp.read().decode("utf-8")
                if response_body:
                    return json.loads(response_body)
                return {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"Zotero API error {e.code}: {error_body}")
    
    def list_collections(self, limit: int = 100) -> list[dict]:
        """列出所有集合。"""
        result = self._request("GET", f"/users/{self.library_id}/collections?limit={limit}")
        return result if isinstance(result, list) else []
    
    def find_collection(self, name: str, parent_key: Optional[str] = None) -> Optional[str]:
        """查找集合。
        
        Args:
            name: 集合名称
            parent_key: 父集合 key（可选）
            
        Returns:
            集合 key 或 None
        """
        collections = self.list_collections(limit=100)
        for coll in collections:
            data = coll.get("data", {})
            if data.get("name") == name:
                if parent_key is None or data.get("parentCollection") == parent_key:
                    return data.get("key")
        return None
    
    def create_collection(self, name: str, parent_key: Optional[str] = None) -> str:
        """创建集合。
        
        Args:
            name: 集合名称
            parent_key: 父集合 key（可选）
            
        Returns:
            新集合的 key
        """
        coll_data = {"name": name}
        if parent_key:
            coll_data["parentCollection"] = parent_key
        
        result = self._request("POST", f"/users/{self.library_id}/collections", [coll_data])
        
        if "success" in result:
            return next(iter(result["success"].values()))
        elif "successful" in result:
            first_item = next(iter(result["successful"].values()))
            return first_item.get("key")
        
        raise RuntimeError(f"创建集合失败: {result}")
    
    def find_or_create_collection(self, path: str) -> str:
        """查找或创建集合路径。
        
        Args:
            path: 集合路径（如 "同事/李志杰"）
            
        Returns:
            最深层集合的 key
        """
        parts = [p for p in path.split("/") if p]
        parent_key = None
        
        for part in parts:
            # 先尝试查找
            found = self.find_collection(part, parent_key)
            if found:
                parent_key = found
            else:
                # 创建新集合
                parent_key = self.create_collection(part, parent_key)
        
        return parent_key
    
    def get_item_template(self, item_type: str = "journalArticle") -> dict:
        """获取 item 模板。
        
        Args:
            item_type: 条目类型
            
        Returns:
            模板字典
        """
        return self._request("GET", f"/items/new?itemType={item_type}")
    
    def find_existing_item(self, doi: Optional[str] = None, pmid: Optional[str] = None) -> Optional[str]:
        """查找已存在的条目。
        
        Args:
            doi: DOI
            pmid: PMID
            
        Returns:
            条目 key 或 None
        """
        if doi:
            try:
                result = self._request("GET", f"/users/{self.library_id}/items?q={doi}&qmode=everything&limit=10")
                if isinstance(result, list):
                    for item in result:
                        item_doi = item.get("data", {}).get("DOI", "")
                        if item_doi and item_doi.lower() == doi.lower():
                            return item.get("key")
            except Exception:
                pass
        
        if pmid:
            try:
                encoded_pmid = urllib.parse.quote(f"PMID: {pmid}", safe="")
                result = self._request("GET", f"/users/{self.library_id}/items?q={encoded_pmid}&qmode=everything&limit=10")
                if isinstance(result, list):
                    for item in result:
                        extra = item.get("data", {}).get("extra", "")
                        if f"PMID: {pmid}" in extra:
                            return item.get("key")
            except Exception:
                pass
        
        return None
    
    def create_item(self, item_data: dict) -> str:
        """创建条目。
        
        Args:
            item_data: 条目数据
            
        Returns:
            新条目的 key
        """
        result = self._request("POST", f"/users/{self.library_id}/items", [item_data])
        
        if "success" in result:
            return next(iter(result["success"].values()))
        elif "successful" in result:
            first_item = next(iter(result["successful"].values()))
            return first_item.get("key")
        
        raise RuntimeError(f"创建条目失败: {result}")
