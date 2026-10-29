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

## [ERR-20261020-001] UTF-8 与命令引号

**Logged**: 2026-10-20T12:39:39+08:00
**Priority**: medium
**Status**: resolved
**Area**: tools

### Summary
默认 Get-Content 显示乱码；一次 Python -c 嵌套引号失败；一次 rg 路径通配符失败。

### Fix
显式 UTF-8、脚本文件和 Path.glob/-g。

### Verification
任务原文读取成功，45 篇检索脚本运行完成，报告校验通过。

### Metadata
- Related Files: outputs/neutrophils_20261020/
- Tags: zotero, literature, verification

## [ERR-20261020-002] Zotero Bridge 与界面访问

**Logged**: 2026-10-20T12:39:39+08:00
**Priority**: medium
**Status**: resolved
**Area**: tools

### Summary
插件 appDisabled=true，Bridge 返回 404；Computer Use 的 Zotero 应用授权超时。

### Fix
保留应用设置，停止 UI 操作；只读接口核实同一库后按已授权方案使用官方 API 添加分类。

### Verification
本地读取成功，分类实际写入和成员回读结果见 verification.json；没有绕过 UI 授权或直写 SQLite。

### Metadata
- Related Files: outputs/neutrophils_20261020/
- Tags: zotero, literature, verification

## [ERR-20261020-003] 全文获取与证据分级

**Logged**: 2026-10-20T12:39:39+08:00
**Priority**: medium
**Status**: resolved
**Area**: tools

### Summary
部分 PMC XML 不可得，ScienceDirect 页面返回 403。

### Fix
使用用户库中已有文本索引；确实缺全文的三篇明确降为摘要。

### Verification
22 篇纳入记录中 19 篇有全文文本，三篇缺口在筛选表及报告中逐一标明。

### Metadata
- Related Files: outputs/neutrophils_20261020/
- Tags: zotero, literature, verification

## [ERR-20261020-004] 草稿作者核对

**Logged**: 2026-10-20T12:39:39+08:00
**Priority**: medium
**Status**: resolved
**Area**: tools

### Summary
草稿中两篇作者简称凭印象误写。

### Fix
用精确 DOI 的 Europe PMC authorString 核对，改为 Volberding 与 Zhu。

### Verification
最终报告已修正并通过作者及 DOI 检查，错误未进入交付稿。

### Metadata
- Related Files: outputs/neutrophils_20261020/
- Tags: zotero, literature, verification

## [ERR-20261029-001] playwright 浏览器缺失与 CDN 下载超时

**Logged**: 2026-10-29T11:58:00+08:00
**Priority**: high
**Status**: resolved
**Area**: tools

### Summary
cnki-mcp 初始化时 Playwright 报 chromium-1243 可执行文件缺失；`playwright install chromium` 访问 cdn.playwright.dev 每次 30 秒超时失败，npmmirror 镜像直装也失败。

### Error
```
playwright._impl._errors.Error: BrowserType.launch_persistent_context: Executable doesn't exist at
C:\Users\涸思雨\AppData\Local\ms-playwright\chromium-1243\chrome-win64\chrome.exe
Error: Request to https://cdn.playwright.dev/... timed out after 30000ms
```

### Fix
用 curl 按字节区间（-r）从 storage.googleapis.com 六段并行下载 chrome-win64.zip（205 MB），解压到 ms-playwright/chromium-1243/；headless 检索所需的 chrome-headless-shell 同法四段下载到 chromium_headless_shell-1243/，并放置 INSTALLATION_COMPLETE 标记。

### Verification
有头模式打开知网标题正确；cnki-mcp 检索 exit=0 返回 12 条结果。

### Metadata
- Reproducible: yes
- Related Files: cnki-mcp/
- Tags: playwright, cnki-mcp, download, mirror

## [ERR-20261029-002] aria2.exe 在本环境静默失败

**Logged**: 2026-10-29T12:35:00+08:00
**Priority**: medium
**Status**: resolved
**Area**: tools

### Summary
`D:\program\Tools\aria2.exe` 启动后无任何输出、不产生目标文件与 .aria2 控制文件，进程存在但无下载行为；stdout 日志始终为空。

### Context
同一 URL 用 curl 可正常下载（约 100-300 KB/s）。多次重试（不同镜像、不同参数）表现一致。

### Fix
放弃 aria2，改用 curl 分段 Range 下载。后续大文件下载在本机优先用 curl -r 分段并行，不再默认 aria2。

### Metadata
- Reproducible: yes
- Tags: aria2, curl, download

## [ERR-20261029-003] 分段下载静默截断与 zip 校验不足

**Logged**: 2026-10-29T13:02:00+08:00
**Priority**: high
**Status**: resolved
**Area**: tests

### Summary
六段并行下载中 part_0、part_4 因 curl 达到 max-time 提前退出，拼接后 zip 缺 8.9 MB；但仅用 `ZipFile().namelist()` 校验（只读中央目录）误报 ZIP OK。

### Fix
按每段期望字节区间计算缺口，用 curl -r 补齐缺失范围后重新拼接；校验必须同时检查：总字节数 == Content-Length、`testzip()` 全量 CRC 通过。

### Verification
补齐后总大小 205123748 与服务端一致，testzip() 返回 None，解压出 chrome.exe 可启动。

### Metadata
- Reproducible: yes
- Tags: segmented-download, zip-validation, curl

