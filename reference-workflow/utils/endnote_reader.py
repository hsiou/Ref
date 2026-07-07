"""EndNote 数据库读取模块。

支持读取 EndNote .enl 文件（SQLite 格式）和 .Data/sdb/sdb.eni 核心数据库。
"""

import re
import sqlite3
import struct
from pathlib import Path
from typing import Optional


class EndNoteReader:
    """EndNote 数据库读取器。"""
    
    def __init__(self, db_path: str | Path):
        """初始化读取器。
        
        Args:
            db_path: EndNote 数据库路径（.enl 或 sdb.eni）
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"数据库文件不存在: {self.db_path}")
        
        self._conn = None
    
    @property
    def conn(self) -> sqlite3.Connection:
        """获取数据库连接（懒加载）。"""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
        return self._conn
    
    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def list_groups(self) -> list[dict]:
        """列出所有组（文集）。"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT group_id, spec FROM groups")
        
        groups = []
        for row in cursor.fetchall():
            group_id, spec_blob = row
            if isinstance(spec_blob, bytes):
                spec_xml = spec_blob.decode("utf-8", errors="replace")
            else:
                spec_xml = spec_blob
            
            # 提取组名
            name_match = re.search(r"<name>([^<]+)</name>", spec_xml)
            if name_match:
                groups.append({
                    "group_id": group_id,
                    "name": name_match.group(1),
                })
        
        return groups
    
    def find_group(self, group_name: str) -> Optional[tuple[int, list[int]]]:
        """查找指定名称的组。
        
        Args:
            group_name: 组名称
            
        Returns:
            (group_id, record_ids) 或 None
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT group_id, spec, members FROM groups")
        
        for row in cursor.fetchall():
            group_id, spec_blob, members_blob = row
            
            # 解析 spec XML
            if isinstance(spec_blob, bytes):
                spec_xml = spec_blob.decode("utf-8", errors="replace")
            else:
                spec_xml = spec_blob
            
            if group_name in spec_xml:
                # 解码 members BLOB
                # 格式: 4字节版本(big-endian) + 4字节计数(little-endian) + N*4字节记录ID(little-endian)
                if isinstance(members_blob, bytes) and len(members_blob) >= 8:
                    version = struct.unpack(">i", members_blob[:4])[0]
                    count = struct.unpack("<i", members_blob[4:8])[0]
                    
                    if count > 0 and count < 1000:
                        ids = []
                        for i in range(count):
                            start = 8 + i * 4
                            end = start + 4
                            if end <= len(members_blob):
                                rec_id = struct.unpack("<i", members_blob[start:end])[0]
                                ids.append(rec_id)
                        return group_id, ids
        
        return None
    
    def fetch_records(self, record_ids: list[int]) -> list[dict]:
        """获取指定 ID 的记录。
        
        Args:
            record_ids: 记录 ID 列表
            
        Returns:
            记录字典列表
        """
        cursor = self.conn.cursor()
        placeholders = ",".join("?" * len(record_ids))
        cursor.execute(f"SELECT * FROM refs WHERE id IN ({placeholders})", record_ids)
        
        columns = [desc[0] for desc in cursor.description]
        records = []
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            records.append(record)
        
        return records
    
    def extract_authors(self, author_str: str) -> list[str]:
        """解析作者字段。
        
        EndNote 格式: "LastName, FirstName\\rLastName, FirstName\\r..."
        
        Args:
            author_str: 原始作者字符串
            
        Returns:
            作者列表（"LastName, FirstName" 格式）
        """
        if not author_str or not author_str.strip():
            return []
        
        authors = []
        for part in author_str.split("\r"):
            part = part.strip()
            if part and "," in part:
                authors.append(part)
        
        return authors
    
    def extract_doi(self, record: dict) -> str:
        """从记录中提取 DOI。
        
        Args:
            record: 记录字典
            
        Returns:
            DOI 字符串或空字符串
        """
        # electronic_resource_number 字段存储 DOI
        doi = record.get("electronic_resource_number", "")
        if doi and doi.startswith("10."):
            return doi.strip()
        
        # 尝试从 url 字段提取
        url = record.get("url", "")
        if url:
            for line in url.split("\n"):
                line = line.strip()
                if "doi.org/" in line or "doi:" in line.lower():
                    match = re.search(r"(10\.\d{4,}/[^\s]+)", line)
                    if match:
                        return match.group(1)
        
        return ""
    
    def extract_pmid(self, record: dict) -> str:
        """从记录中提取 PMID。
        
        Args:
            record: 记录字典
            
        Returns:
            PMID 字符串或空字符串
        """
        pmid = record.get("accession_number", "")
        if pmid and pmid.isdigit():
            return pmid
        return ""
