# Errors

Command failures and integration errors.

---

## [ERR-20260707-001] endnote_enl_format

**Logged**: 2026-07-07T16:00:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
EndNote .enl 文件格式识别错误，假设为 XML 实际为 SQLite

### Error
```
尝试用 XML 解析器读取 .enl 文件失败
```

### Context
- 操作：读取 EndNote 文献库
- 输入：`F:\我的坚果云\2、工作文档\文献\My_Library_20260312.enl`
- 文件头为 `SQLite format 3`，是 SQLite 数据库而非 XML

### Suggested Fix
使用 sqlite3 模块读取 .enl 文件，核心数据在 `.Data/sdb/sdb.eni`

### Resolution
- **Resolved**: 2026-07-07T16:30:00Z
- **Notes**: 改用 sqlite3 直接读取，成功提取数据

---

## [ERR-20260707-002] endnote_members_blob_byte_order

**Logged**: 2026-07-07T16:05:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
EndNote groups 表 members BLOB 字节序解析错误

### Error
```
解析出的记录 ID 全部错误（如 503316480 而非 30）
struct.unpack('>i', members_blob[4:8])[0] 返回错误值
```

### Context
- 操作：解析 EndNote 文集成员列表
- BLOB 结构：version(4B) + count(4B) + record_ids(N*4B)
- version 使用 big-endian，count 和 IDs 使用 little-endian

### Suggested Fix
```python
version = struct.unpack(">i", blob[:4])[0]   # big-endian
count = struct.unpack("<i", blob[4:8])[0]    # little-endian
rec_id = struct.unpack("<i", blob[start:end])[0]  # little-endian
```

### Resolution
- **Resolved**: 2026-07-07T16:15:00Z
- **Notes**: 修正字节序后正确解析出 30 条记录

---

## [ERR-20260707-003] zotero_api_chinese_search_500

**Logged**: 2026-07-07T16:10:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Zotero API 搜索中文集合名称返回 HTTP 500

### Error
```
GET /users/17365633/collections?q=%E5%90%8C%E4%BA%8B&qmode=start
HTTP Error 500: Internal Server Error
```

### Context
- 操作：搜索 Zotero 集合
- 参数：`q=同事`（URL 编码后）
- Zotero API 对中文查询参数支持有限

### Suggested Fix
避免在查询参数中使用中文，改为列出所有集合后遍历查找

### Resolution
- **Resolved**: 2026-07-07T16:20:00Z
- **Notes**: 改用 `limit=100` 列出所有集合，然后 Python 端过滤

---

## [ERR-20260707-004] zotero_api_collection_array_required

**Logged**: 2026-07-07T16:12:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Zotero API 创建集合时要求 JSON 数组格式

### Error
```
HTTP Error 400: Uploaded data must be a JSON array
```

### Context
- 操作：创建 Zotero 集合
- 发送数据：`{"name": "同事"}`（对象）
- 实际需要：`[{"name": "同事"}]`（数组）

### Suggested Fix
所有 Zotero API POST 请求体使用数组格式

### Resolution
- **Resolved**: 2026-07-07T16:18:00Z
- **Notes**: 包装为数组后成功创建

---

## [ERR-20260707-005] zotero_api_item_template_404

**Logged**: 2026-07-07T16:14:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Zotero API 获取 item 模板端点返回 404

### Error
```
GET /users/17365633/items/new?itemType=journalArticle
HTTP Error 404: Not Found
```

### Context
- 操作：获取 Zotero item 模板
- 错误端点：`/users/{id}/items/new`
- 正确端点：`/items/new`（不需要用户 ID 前缀）

### Suggested Fix
使用 `/items/new?itemType=journalArticle`（无用户 ID）

### Resolution
- **Resolved**: 2026-07-07T16:25:00Z
- **Notes**: 修正端点后成功获取模板

---

## [ERR-20260707-006] zotero_api_qmode_doikey_invalid

**Logged**: 2026-07-07T16:16:00Z
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Zotero API 不支持 qmode=doiKey

### Error
```
HTTP Error 400: Invalid 'qmode' value 'doiKey'
```

### Context
- 操作：搜索 DOI 去重
- 尝试使用 `qmode=doiKey` 直接匹配 DOI
- Zotero API 只支持 `everything` 和 `titleCreatorYear`

### Suggested Fix
使用 `qmode=everything`，然后在结果中手动匹配 DOI

### Resolution
- **Resolved**: 2026-07-07T16:22:00Z
- **Notes**: 改用 everything 模式后正常工作

---

## [ERR-20260707-007] endnote_author_field_delimiter

**Logged**: 2026-07-07T16:08:00Z
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
EndNote author 字段使用 `\r` 分隔而非空格或逗号

### Error
```
作者被错误地连接为一个字符串
"Xue, Y.Liu, P.Wang, H." 而非 "Xue, Y. and Liu, P. and Wang, H."
```

### Context
- 操作：解析 EndNote 作者字段
- 实际格式：`LastName, FirstName\rLastName, FirstName\r...`
- 使用 `\r`（回车符）分隔

### Suggested Fix
按 `\r` 分割作者字段：`author_str.split("\r")`

### Resolution
- **Resolved**: 2026-07-07T16:12:00Z
- **Notes**: 修正分割符后正确解析

---

## [ERR-20260707-008] zotero_api_response_structure

**Logged**: 2026-07-07T16:20:00Z
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Zotero API 响应同时包含 successful 和 success 两个键

### Error
```
result["successful"] 包含完整对象
result["success"] 只包含 key
使用 result["successful"].values() 获取 key 时出错
```

### Context
- 操作：创建 Zotero 条目后获取 key
- `successful`：`{"0": {"key": "XXX", "version": 778, ...}}`
- `success`：`{"0": "XXX"}`

### Suggested Fix
优先使用 `success` 字段：`next(iter(result["success"].values()))`

### Resolution
- **Resolved**: 2026-07-07T16:28:00Z
- **Notes**: 修正后稳定获取 key

---
