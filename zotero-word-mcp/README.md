# zotero-word-mcp

`zotero-word-mcp` 是一个面向 Windows 的 MCP Server，用于把 **Zotero 原生动态引文** 直接插入 **Microsoft Word 桌面版** 文档。

它不是静态编号脚本，也不是通用 `.docx` 编辑器，而是专门解决下面这个断点：

- Zotero MCP 负责文献库
- Word MCP 负责文档内容
- 但 AI 很难把 **Zotero 可继续维护的原生引文** 真正插进 Word

本项目补上的就是这一步。

## 核心能力

- 向 Word 文档插入 Zotero 原生 `ADDIN ZOTERO_ITEM` 引文字段
- 向 Word 文档插入 Zotero 原生 `ADDIN ZOTERO_BIBL` 参考文献字段
- 写入 `ZOTERO_PREF_1..N` 文档首选项
- 触发 Zotero 官方 Word `Refresh`
- 列出文档中的 Zotero 原生字段
- 设置文档的 CSL 样式
- 使用 Zotero 官方 `libzoteroWinWordIntegration.dll` 探测文档是否可被识别
- 分析并批量转换 `[1]`、`[1, 2]`、`[1-3]` 这类静态数字引用

## 为什么单独做这个 MCP

普通 Word MCP 更适合：

- 插段落
- 排版
- 查找替换
- 表格/图片处理

而 `zotero-word-mcp` 解决的是：

- 引文必须是 Zotero 原生字段
- 刷新后要继续被 Zotero 插件接管
- 用户后续还要能在 Word 里继续点 `Add/Edit Citation`

这决定了它必须直接面向 Zotero Word 集成，而不是只写普通文本。

## 适用环境

- Windows
- Microsoft Word 桌面版
- Zotero 7
- Python 3.10+

当前未完整验证：

- WPS
- Word Online
- 受保护文档
- 多人实时协作文档

## 安装

```powershell
git clone https://github.com/Zhangchaokai1/zotero-word-mcp.git
cd zotero-word-mcp
pip install -e .
```

如果你只想本地运行：

```powershell
pip install "mcp[cli]" pywin32 requests
```

## 配置

可选环境变量：

- `ZOTERO_DATA_DIR`
  Zotero 数据目录，例如 `D:\Zotero\ZoteroFile`
- `ZOTERO_SQLITE_PATH`
  指向 `zotero.sqlite`
- `ZOTERO_WORD_DLL`
  指向 `libzoteroWinWordIntegration.dll`

如果不显式设置，程序会优先从 Zotero `prefs.js` 自动发现数据目录。

## MCP 工具

### `insert_citation`

向 Word 文档插入 Zotero 原生引文。

主要参数：

- `doc`
- `keys`
- `find_text`
- `placement`
- `style_id`
- `library_id`
- `prefix`
- `suffix`
- `refresh_after`
- `wait_seconds`

### `insert_bibliography`

向 Word 文档插入 Zotero 原生参考文献字段。

### `refresh_document`

触发 Zotero 官方 `Refresh`，并等待占位字段解析完成。

### `list_fields`

列出文档中的 Zotero 原生字段和文档首选项。

### `set_document_style`

设置文档 Zotero CSL 样式，不立即刷新。

### `analyze_numbered_citations`

分析 Word 文档中的数字方括号引用和静态参考文献列表，不修改文档。

适合在转换前确认：

- 正文引用标记数量
- `References` 标题段落位置
- 文末静态参考文献数量
- 是否有超出参考文献范围的引用编号

主要参数：

- `doc`
- `bibliography_heading`，默认 `References`

### `convert_numbered_citations`

将静态数字引用批量替换成 Zotero 原生字段。

支持：

- `[1]`
- `[1, 2]`
- `[1，2]`
- `[1-3]`

主要参数：

- `doc`
- `citation_map`
- `output_doc`
- `bibliography_heading`
- `library_id`
- `style_id`
- `locale`
- `delete_static_references`
- `insert_bibliography`
- `refresh_after`
- `wait_seconds`

`citation_map` 示例：

```json
{
  "1": "ABCD1234",
  "2": "EFGH5678",
  "3": "IJKL9012"
}
```

推荐智能体使用 `output_doc`，让工具先复制原文档再转换，避免覆盖原文件。

### `validate_zotero_document`

综合验证 Zotero 原生字段状态。

返回：

- citation 字段数量
- bibliography 字段数量
- `{Citation}` / `{Bibliography}` 占位符数量
- bibliography 字段是否从参考文献标题后一段开始
- 当前文档字段列表

### `probe_document`

调用 Zotero 官方 `libzoteroWinWordIntegration.dll` 验证当前文档是否能被官方集成识别。

## 推荐批量转换流程

智能体把静态编号文献转换成 Zotero 原生引用时，推荐使用：

1. 用 `analyze_numbered_citations` 检查编号引用和参考文献列表。
2. 用 Zotero MCP 或其他文献工具生成 `citation_map`。
3. 调用 `convert_numbered_citations`，传入 `output_doc`、`citation_map` 和 `style_id`。
4. 用 `validate_zotero_document` 检查字段数量、占位符和 bibliography 起始位置。
5. 用 `probe_document` 确认 Zotero 官方 Word 集成能识别字段。

## 启动服务

```powershell
zotero-word-mcp
```

如果你的 MCP 客户端支持命令式 server，可以这样配置：

```toml
[mcp_servers.zotero-word]
command = "python"
args = ["-m", "zotero_word_mcp"]
```

## 项目结构

- `src/zotero_word_mcp/word_bridge.py`
  Word COM 基础桥接
- `src/zotero_word_mcp/native_bridge.py`
  Zotero 原生字段与刷新逻辑
- `src/zotero_word_mcp/server.py`
  MCP 工具封装
- `docs/DEVELOPMENT_REVIEW.md`
  开发复盘与技术路线说明

## 与静态引用方案的区别

静态方案通常是：

- 正文写 `[1]`
- 文末写普通文本参考文献
- 再靠 Word 交叉引用或脚本刷新

这类方案容易控，但不是 Zotero 原生动态引文。

本项目写入的是 Zotero 官方 Word 集成可识别的字段，因此：

- Zotero 可以继续接管这份文档
- 用户后续仍能用 Word 里的 Zotero 插件继续维护

## 已知边界

- 仅支持 Windows + Word 桌面版
- 依赖本机可用的 Zotero Word 集成
- 相邻无间隔插入多个新引文时，Zotero 刷新后可能自动合并为复合引文字段
- 复杂受保护文档仍建议先做副本测试

## 开发复盘

详见：

- [docs/DEVELOPMENT_REVIEW.md](docs/DEVELOPMENT_REVIEW.md)

## License

MIT
