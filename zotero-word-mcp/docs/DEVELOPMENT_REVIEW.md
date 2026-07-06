# 开发复盘

## 1. 目标

本项目的目标不是“往 Word 里写一个 `[1]`”，而是让 AI 能像熟练用户一样，把 **Zotero 原生动态引文** 插入到 **Microsoft Word**，并让后续的 Zotero 插件继续接管这份文档。

这决定了路线选择必须满足两个要求：

1. 插进去的不是静态文本
2. Zotero 官方 Word 集成必须能识别并继续刷新

## 2. 为什么没有停留在静态桥接

前一阶段已经做通过一套静态桥接：

- Word 文末参考文献使用自动编号列表
- 正文使用 Word 交叉引用显示 `[1]`
- 重新排序后可以 `Ctrl+A -> F9` 整体更新

这套方案稳定、易控，但存在两个根本限制：

- 它不是 Zotero 原生引文字段
- 后续用户如果继续用 Zotero 插件插引文，工作流会割裂

所以它适合作为应急方案，不适合作为长期 MCP 产品形态。

## 3. 第一条失败路线：HTTP integration 桥接

最早尝试的是借用 Zotero HTTP integration 的思路：

- 在 Word 文档中放入自定义内容控件
- 自己保存 `documentData`
- 把字段 code 存在 Word Variables
- 再通过 Zotero connector 触发 refresh

这条路线可以做到：

- 由 AI 自动插入引用位点
- 按顺序生成静态编号
- 在某些场景里由 Zotero HTTP 侧完成格式化

但最终问题很明确：

- Word 文档中的字段载体不是 Zotero 官方 Word 集成认可的原生字段
- 在 `Document.getFields` 之后，官方刷新链路会报错
- 即使局部刷新可用，也不具备长期稳定性

结论是：
HTTP integration 这条路适合做实验和静态替代，不适合做“原生 Zotero 动态引文”的最终方案。

## 4. 关键转折：回到 Zotero 官方字段格式

真正打通的关键，是不再伪造自己的字段结构，而是直接生成 Zotero Word 集成可识别的原生结构：

### 4.1 文档首选项

使用 Word 自定义文档属性写入：

- `ZOTERO_PREF_1`
- `ZOTERO_PREF_2`
- ...

内容为分片后的 `documentData` JSON。

### 4.2 引文字段

使用 Word Field 写入原生 code：

- `ADDIN ZOTERO_ITEM CSL_CITATION {...}`
- `ADDIN ZOTERO_BIBL {} CSL_BIBLIOGRAPHY`

占位文本分别使用：

- `{Citation}`
- `{Bibliography}`

### 4.3 刷新触发

通过 Word 宏调用 Zotero 官方集成命令：

- `Project.Zotero.ZoteroRefresh`

这一步不是模拟按钮点击，而是直接触发 Zotero 的 Word 集成命令。

## 5. 核心验证方法

开发过程中真正有价值的验证不是“Word 看起来像成功了”，而是下面三层：

### 5.1 文档侧验证

检查 Word 中是否真的写入了：

- `ZOTERO_PREF_1..N`
- `ADDIN ZOTERO_ITEM ...`
- `ADDIN ZOTERO_BIBL ...`

### 5.2 官方 DLL 验证

调用 Zotero 官方 DLL：

- `libzoteroWinWordIntegration.dll`

验证它是否能识别文档中的字段。这一步很重要，因为它直接回答了：

“当前文档是不是 Zotero 官方集成真正认可的文档？”

### 5.3 人工工作流验证

让用户在 Word 中继续操作：

- 点击 `Refresh`
- 再插入一条新的 `Add/Edit Citation`

如果这两步都能继续工作，说明文档没有被桥接脚本做坏。

## 6. 遇到的关键问题与处理

### 6.1 Word COM 调用被拒绝

症状：

- `RPC_E_CALL_REJECTED`

处理：

- 增加 `wait_until_word_accessible()`
- 在刷新轮询中补 `pythoncom.PumpWaitingMessages()`

### 6.2 Zotero 刷新后占位文本不替换

症状：

- 宏已触发，但 `{Citation}`、`{Bibliography}` 不变化

原因排查后发现：

- 问题不在 Word 宏是否触发
- 而在文档字段格式是否真正符合 Zotero 官方期待

切回原生 `ADDIN ZOTERO_*` 字段后，这个问题被解决。

### 6.3 Word 弹“另存为”

症状：

- 刷新后脚本保存文档时弹出“另存为”

原因：

- 测试文档在某些阶段处于只读/锁定状态

处理：

- 减少非必要的自动保存
- 刷新完成判定后再保存
- 正式文档和测试文档分离

### 6.4 相邻引文被 Zotero 合并

症状：

- 多个很近的引文字段在 refresh 后被 Zotero 合成一个复合字段

结论：

- 这是 Zotero 自身的重写行为，不是桥接脚本损坏字段

规避策略：

- 正式插入时按具体句子位置落点
- 避免把多个新引文无间隔插在同一位置

### 6.5 Word 排版脚本与 Zotero 字段互相影响

经验结论：

- 纯文本排版可以用 Word COM
- 但不应在最后排版阶段再主动 `Fields.Update()`
- 否则容易触发 Zotero 字段重算，带来额外锁和保存冲突

## 7. 当前架构

当前项目分为三层：

### 7.1 `word_bridge.py`

提供基础能力：

- 连接 Word COM
- 打开/激活/保存文档
- 定位文本
- 插入内容控件或原生字段所需的共用方法
- 读取本地 Zotero SQLite 元数据

### 7.2 `native_bridge.py`

提供原生 Zotero 动态引文能力：

- 写入 `ZOTERO_PREF_1..N`
- 写入原生 `ADDIN ZOTERO_ITEM` / `ADDIN ZOTERO_BIBL`
- 触发官方宏
- 轮询刷新完成
- 通过官方 DLL 探测

### 7.3 `server.py`

将上述能力暴露为 MCP 工具：

- `insert_citation`
- `insert_bibliography`
- `refresh_document`
- `list_fields`
- `set_document_style`
- `probe_document`

## 8. 为什么这个项目值得单独发布

因为它解决的是一个非常具体但普遍存在的断点：

- 普通 Word MCP 只能改文档内容
- Zotero MCP 只能管理文献库
- 真正困难的是“让 AI 把 Zotero 动态引文插进 Word”

这个断点一旦补上，AI 才能在学术写作、项目申报、技术报告、专利草稿等场景里真正闭环工作。

## 9. 当前边界

当前版本仍有明确边界：

- 仅支持 Windows
- 仅支持 Microsoft Word 桌面版
- 假定用户本机已安装 Zotero Word 集成
- 未完整验证 WPS、Word Online、受保护文档、多人实时协作文档

## 10. 后续建议

### 10.1 优先补充

- 文档活动窗口检测
- 获取当前光标位置并直接插引文
- 对复杂文档的只读/锁定状态做更友好的报错

### 10.2 可选增强

- 直接从 Zotero collection 中搜索条目再插引文
- 插入脚注体例
- 支持批量把静态编号文档转换成 Zotero 原生引文文档

### 10.3 发布前建议

- 补一个 `examples/` 目录
- 补最小演示 GIF 或截图
- 在 README 增加 Codex / Claude Desktop 配置示例
- 明确标注“Windows-only”

## 11. 最终结论

这次开发最重要的结果，不是“写了一个 Word 脚本”，而是：

1. 确认了 HTTP integration 方案不足以作为原生动态引文产品方案
2. 找到了 Zotero 官方 Word 字段的稳定写入路径
3. 将这条路径整理成了可进一步发布为 MCP Server 的工程结构

这意味着后续不需要再从零试错，而是可以直接围绕这套原生桥接能力继续做产品化迭代。
