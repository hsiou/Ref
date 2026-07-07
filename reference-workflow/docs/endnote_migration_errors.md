# EndNote → Zotero 迁移错误总结

## 背景

在将 EndNote 文献库中 "文集/李志杰教授" 的 30 条记录迁移到 Zotero "同事/李志杰" 集合的过程中，遇到了以下技术问题。

---

## 错误1：EndNote .enl 文件格式识别错误

**现象**：最初假设 .enl 文件是 XML 格式，尝试用 XML 解析器读取。

**实际**：.enl 文件是 SQLite 数据库格式（文件头为 `SQLite format 3`）。

**解决方案**：使用 sqlite3 模块直接读取 .enl 文件。

**关键文件**：`My_Library_20260312.Data/sdb/sdb.eni`（核心数据库）

---

## 错误2：Members BLOB 字节序解析错误

**现象**：解析 EndNote groups 表中的 members BLOB 时，记录 ID 全部错误（如 503316480）。

**原因**：members BLOB 使用混合字节序：
- 前 4 字节（version）：big-endian，值为 2
- 接下来 4 字节（count）：little-endian
- 之后的记录 ID：little-endian

**错误代码**：
```python
# 错误：全部使用 big-endian
version = struct.unpack(">i", members_blob[:4])[0]  # 正确
count = struct.unpack(">i", members_blob[4:8])[0]   # 错误！
rec_id = struct.unpack(">i", members_blob[start:end])[0]  # 错误！
```

**正确代码**：
```python
version = struct.unpack(">i", members_blob[:4])[0]   # big-endian
count = struct.unpack("<i", members_blob[4:8])[0]    # little-endian
rec_id = struct.unpack("<i", members_blob[start:end])[0]  # little-endian
```

---

## 错误3：Zotero API 中文搜索返回 500 错误

**现象**：使用 `qmode=start` 搜索包含中文字符的集合名称时，Zotero API 返回 HTTP 500。

**请求示例**：
```
GET /users/17365633/collections?q=%E5%90%8C%E4%BA%8B&qmode=start
```

**解决方案**：放弃搜索，改为直接创建集合，或通过列出所有集合后遍历查找。

---

## 错误4：Zotero API 请求格式错误（数组要求）

**现象**：创建集合时返回 `HTTP 400: Uploaded data must be a JSON array`。

**原因**：Zotero API 要求 POST 请求体为 JSON 数组格式，而非单个对象。

**错误代码**：
```python
body = {"name": "同事"}  # 错误：对象
```

**正确代码**：
```python
body = [{"name": "同事"}]  # 正确：数组
```

---

## 错误5：Zotero API item 模板端点错误

**现象**：获取 item 模板时返回 `HTTP 404 Not Found`。

**错误端点**：
```
GET /users/17365633/items/new?itemType=journalArticle  # 404
```

**正确端点**：
```
GET /items/new?itemType=journalArticle  # 200（不需要用户 ID 前缀）
```

---

## 错误6：Zotero API qmode 参数不支持 doiKey

**现象**：使用 `qmode=doiKey` 搜索 DOI 时返回 `HTTP 400: Invalid 'qmode' value 'doiKey'`。

**原因**：Zotero API 只支持 `everything` 和 `titleCreatorYear` 两种 qmode。

**解决方案**：使用 `qmode=everything`，然后在结果中手动匹配 DOI。

---

## 错误7：作者字段解析错误

**现象**：EndNote 的 author 字段中，多个作者之间用 `\r`（回车符）分隔，而非空格或逗号。

**错误数据示例**：
```
Xue, Y.\rLiu, P.\rWang, H.\rXiao, C.
```

**解决方案**：按 `\r` 分割作者字段：
```python
authors = [a.strip() for a in author_str.split("\r") if a.strip()]
```

---

## 错误8：BibTeX 条目分割不完整

**现象**：从生成的 .bib 文件中分割 BibTeX 条目时，简单的 `split("@journalArticle{")` 无法正确处理嵌套花括号。

**解决方案**：使用深度计数器找到正确的结束位置：
```python
depth = 0
for i, c in enumerate(entry_text):
    if c == '{':
        depth += 1
    elif c == '}':
        if depth == 0:
            end_idx = i
            break
        depth -= 1
```

---

## 错误9：Zotero API 响应结构不一致

**现象**：创建条目后，响应中同时存在 `successful` 和 `success` 两个键：
- `successful`：包含完整的条目对象
- `success`：只包含 key 的简单映射

**解决方案**：优先使用 `success` 字段获取 key：
```python
if "success" in result:
    key = next(iter(result["success"].values()))
```

---

## 错误10：环境变量未在 Git Bash 中加载

**现象**：使用 `setx` 设置的环境变量在当前 Git Bash 会话中不可用。

**原因**：`setx` 设置的变量需要重新打开终端窗口才会生效。

**解决方案**：在脚本执行前使用 `export` 命令设置：
```bash
export ZOTERO_API_KEY="xxx"
export ZOTERO_LIBRARY_ID="xxx"
```

---

## 经验教训

1. **数据库格式识别**：不要假设文件格式，先检查文件头。
2. **字节序处理**：混合字节序很常见，需要逐字段验证。
3. **API 兼容性**：Zotero API 对中文支持有限，避免在查询参数中使用中文。
4. **错误处理**：空错误信息可能是异常被吞掉了，需要更细致的异常捕获。
5. **环境变量**：跨会话的环境变量需要显式设置或从配置文件读取。
