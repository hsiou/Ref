# Learnings

Corrections, insights, and knowledge gaps captured during development.

**Categories**: correction | insight | knowledge_gap | best_practice

---

## [LRN-20260707-001] knowledge_gap

**Logged**: 2026-07-07T16:00:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
EndNote .enl 文件是 SQLite 数据库而非 XML

### Details
- .enl 文件头为 `SQLite format 3`
- 核心数据在 `.Data/sdb/sdb.eni`（14.2 MB）
- 包含 refs、groups、misc 等表
- groups 表存储文集定义，members BLOB 存储成员 ID

### Suggested Action
读取 EndNote 数据库时直接使用 sqlite3，无需导出 XML

### Metadata
- Source: error
- Related Files: `endnote_to_zotero.py`
- Tags: endnote, sqlite, database

---

## [LRN-20260707-002] insight

**Logged**: 2026-07-07T16:05:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
混合字节序在二进制格式中很常见

### Details
- EndNote members BLOB 使用混合字节序：
  - version: big-endian (0x00000002 = 2)
  - count: little-endian (0x1e000000 = 30)
  - record IDs: little-endian
- 必须逐字段验证字节序，不能假设统一

### Suggested Action
处理二进制数据时，先用已知值测试字节序

### Metadata
- Source: error
- Related Files: `endnote_to_zotero.py`
- Tags: binary, byte-order, struct

---

## [LRN-20260707-003] knowledge_gap

**Logged**: 2026-07-07T16:10:00Z
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
Zotero API 对中文查询参数支持有限

### Details
- `qmode=start` 搜索中文返回 500 错误
- URL 编码后仍失败
- 只能通过列出所有集合后遍历查找

### Suggested Action
避免在 Zotero API 查询参数中使用中文

### Metadata
- Source: error
- Related Files: `endnote_to_zotero.py`
- Tags: zotero, api, chinese, unicode

---

## [LRN-20260707-004] best_practice

**Logged**: 2026-07-07T16:15:00Z
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Zotero API POST 请求体必须是 JSON 数组

### Details
- 创建集合/条目时，请求体必须是数组格式
- `[{"name": "xxx"}]` 而非 `{"name": "xxx"}`
- 即使只创建一个对象也要用数组

### Suggested Action
统一使用数组格式包装 Zotero API POST 数据

### Metadata
- Source: error
- Related Files: `endnote_to_zotero.py`
- Tags: zotero, api, json, array

---

## [LRN-20260707-005] knowledge_gap

**Logged**: 2026-07-07T16:20:00Z
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
Zotero API 端点路径不一致

### Details
- 获取 item 模板：`/items/new`（无用户 ID）
- 其他操作：`/users/{id}/items`（需要用户 ID）
- 必须查阅官方文档确认端点

### Suggested Action
记录常用 Zotero API 端点，避免猜测

### Metadata
- Source: error
- Related Files: `endnote_to_zotero.py`
- Tags: zotero, api, endpoint

---

## [LRN-20260707-006] insight

**Logged**: 2026-07-07T16:25:00Z
**Priority**: medium
**Status**: resolved
**Area**: backend

### Summary
空错误信息可能是异常被吞掉

### Details
- 使用 `except Exception as e` 捕获异常
- `str(e)` 返回空字符串
- 需要更细致的异常处理和调试输出

### Suggested Action
在异常处理中打印异常类型和完整信息

### Metadata
- Source: error
- Related Files: `endnote_to_zotero.py`
- Tags: error-handling, debugging

---

## [LRN-20260707-007] best_practice

**Logged**: 2026-07-07T16:30:00Z
**Priority**: medium
**Status**: resolved
**Area**: config

### Summary
setx 设置的环境变量需要重启终端

### Details
- `setx` 设置的变量存储在注册表
- 当前 shell 会话不会自动加载
- 需要 `export` 或重启终端

### Suggested Action
在脚本中显式设置环境变量，或从配置文件读取

### Metadata
- Source: error
- Related Files: `endnote_to_zotero.py`
- Tags: environment, windows, shell

---
