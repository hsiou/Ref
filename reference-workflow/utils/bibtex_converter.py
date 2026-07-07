"""BibTeX 转换模块。

将 EndNote 记录转换为 BibTeX 格式。
"""

import re
from typing import Optional


# EndNote reference_type 到 Zotero item type 的映射
ENDNOTE_TYPE_MAP = {
    0: "journalArticle",    # Journal Article
    1: "book",              # Book
    2: "bookSection",       # Book Section
    3: "journalArticle",    # Journal Article (同0)
    6: "conferencePaper",   # Conference Paper
    7: "thesis",            # Thesis
    10: "report",           # Report
    11: "webpage",          # Web Page
    17: "journalArticle",   # Journal Article
    23: "patent",           # Patent
    28: "book",             # Book
}


def generate_bibtex_key(record: dict) -> str:
    """生成 BibTeX 引用键。
    
    Args:
        record: EndNote 记录字典
        
    Returns:
        引用键字符串
    """
    author = record.get("author", "")
    year = record.get("year", "")
    title = record.get("title", "")
    
    # 提取第一作者姓氏
    first_author = ""
    if author:
        authors = [a.strip() for a in author.split("\r") if a.strip()]
        if authors:
            first_part = authors[0]
            if "," in first_part:
                last_name = first_part.split(",")[0].strip()
            else:
                last_name = first_part
            first_author = re.sub(r"[^a-zA-Z]", "", last_name.lower())
    
    # 提取标题第一个实义词
    first_word = ""
    if title:
        words = re.findall(r"[A-Za-z]+", title)
        skip_words = {"the", "a", "an", "of", "in", "on", "for", "and", "or", "to"}
        for w in words:
            if w.lower() not in skip_words:
                first_word = w.lower()
                break
    
    key = f"{first_author}{year}{first_word}"
    return key if key else f"ref{record.get('id', '')}"


def record_to_bibtex(record: dict) -> str:
    """将 EndNote 记录转换为 BibTeX 条目。
    
    Args:
        record: EndNote 记录字典
        
    Returns:
        BibTeX 条目字符串
    """
    ref_type = record.get("reference_type", 0)
    bibtex_type = ENDNOTE_TYPE_MAP.get(ref_type, "article")
    
    key = generate_bibtex_key(record)
    title = record.get("title", "").strip()
    author = record.get("author", "").strip()
    year = record.get("year", "").strip()
    journal = record.get("secondary_title", "").strip()
    volume = record.get("volume", "").strip()
    number = record.get("number", "").strip()
    pages = record.get("pages", "").strip()
    doi = record.get("electronic_resource_number", "").strip()
    pmid = record.get("accession_number", "").strip()
    abstract = record.get("abstract", "").strip()
    keywords = record.get("keywords", "").strip()
    url = record.get("url", "").strip()
    isbn = record.get("isbn", "").strip()
    
    # 格式化作者（BibTeX 使用 "and" 分隔）
    if author:
        author_list = [a.strip() for a in author.split("\r") if a.strip()]
        if len(author_list) > 1:
            author_bibtex = " and ".join(author_list)
        else:
            author_bibtex = author
    else:
        author_bibtex = ""
    
    # 构建 BibTeX 条目
    lines = [f"@{bibtex_type}{{{key},"]
    
    if title:
        lines.append(f"  title = {{{title}}},")
    if author_bibtex:
        lines.append(f"  author = {{{author_bibtex}}},")
    if year:
        lines.append(f"  year = {{{year}}},")
    if journal:
        lines.append(f"  journal = {{{journal}}},")
    if volume:
        lines.append(f"  volume = {{{volume}}},")
    if number:
        lines.append(f"  number = {{{number}}},")
    if pages:
        lines.append(f"  pages = {{{pages}}},")
    if doi:
        lines.append(f"  doi = {{{doi}}},")
    if pmid:
        lines.append(f"  pmid = {{{pmid}}},")
    if url:
        # 提取 PubMed URL
        pubmed_url = ""
        for line in url.split("\n"):
            line = line.strip()
            if "pubmed.ncbi.nlm.nih.gov" in line:
                pubmed_url = line
                break
        if pubmed_url:
            lines.append(f"  url = {{{pubmed_url}}},")
    if abstract:
        # 清理 abstract 中的特殊字符
        abstract_clean = abstract.replace("{", "\\{").replace("}", "\\}")
        lines.append(f"  abstract = {{{abstract_clean}}},")
    if keywords:
        lines.append(f"  keywords = {{{keywords}}},")
    if isbn:
        lines.append(f"  isbn = {{{isbn}}},")
    
    lines.append("}")
    return "\n".join(lines)


def bibtex_to_zotero_item(bibtex_str: str, template: dict) -> dict:
    """将 BibTeX 条目转换为 Zotero item 数据。
    
    Args:
        bibtex_str: BibTeX 条目字符串
        template: Zotero item 模板
        
    Returns:
        Zotero item 字典
    """
    item = template.copy()
    
    # 解析 BibTeX 字段
    fields = {}
    for line in bibtex_str.split("\n"):
        line = line.strip()
        if "=" in line and not line.startswith("@") and not line.startswith("}"):
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().rstrip(",")
            # 去除 BibTeX 花括号
            if value.startswith("{") and value.endswith("}"):
                value = value[1:-1]
            fields[key] = value
    
    # 映射字段
    if "title" in fields:
        item["title"] = fields["title"]
    
    if "author" in fields:
        creators = []
        for author in fields["author"].split(" and "):
            author = author.strip()
            if "," in author:
                parts = author.split(",", 1)
                last_name = parts[0].strip()
                first_name = parts[1].strip()
            else:
                last_name = author
                first_name = ""
            
            creators.append({
                "creatorType": "author",
                "firstName": first_name,
                "lastName": last_name,
            })
        item["creators"] = creators
    
    if "year" in fields:
        item["date"] = fields["year"]
    
    if "journal" in fields:
        item["publicationTitle"] = fields["journal"]
    
    if "volume" in fields:
        item["volume"] = fields["volume"]
    
    if "number" in fields:
        item["issue"] = fields["number"]
    
    if "pages" in fields:
        item["pages"] = fields["pages"]
    
    if "doi" in fields:
        item["DOI"] = fields["doi"]
    
    if "abstract" in fields:
        item["abstractNote"] = fields["abstract"]
    
    if "keywords" in fields:
        item["tags"] = [{"tag": k.strip()} for k in fields["keywords"].split(",") if k.strip()]
    
    # Extra 字段存储 PMID
    extra_parts = []
    if "pmid" in fields:
        extra_parts.append(f"PMID: {fields['pmid']}")
    if "url" in fields:
        extra_parts.append(f"URL: {fields['url']}")
    if extra_parts:
        item["extra"] = "\n".join(extra_parts)
    
    return item
