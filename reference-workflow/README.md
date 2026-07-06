# Reference Workflow

本项目是一个本地参考文献工作流编排层，用于把“用户提供参考文献信息”转化为可验证、可入库、可插入 Word 手稿并可由 Zotero 更新的动态引用。

它不替代 PubMed、Zotero、EndNote 或 Word 插件，而是把这些工具串起来，形成一个更适合写作场景的半自动流程：

1. 从 PMID、DOI、PubMed 链接或 Markdown 文献清单中提取待验证文献。
2. 通过 `pubmed-cli` 查询 PubMed，确认文献真实存在。
3. 将确认后的文献转换为 Zotero 条目格式。
4. 通过 Zotero Web API 写入 Zotero，或在 dry-run 模式下只生成待写入内容。
5. 返回 Zotero item key，供 `zotero-word-mcp` 插入 Word 原生 Zotero 字段。
6. 调用 Zotero Word 集成刷新手稿，使引文和参考文献表变成 Zotero 可识别、可修改、可更新的动态字段。
7. 使用 `endnote-mcp` 将既有 EndNote XML 文献库作为本地补充检索源。

## 项目功能

- 单条文献验证：支持 PMID、DOI、DOI URL 和普通 PubMed 查询文本。
- 批量清单验证：从 UTF-8 Markdown 或文本文件中提取 PubMed 链接和 DOI。
- PubMed-only 模式：只确认文献真实性，不读取或写入 Zotero。
- Zotero dry-run 模式：生成 Zotero 条目 payload，但不写入 Zotero。
- Zotero 写入和查重：优先按 DOI 查重；无 DOI 时按 PMID 兜底，避免空 DOI 误判。
- Word 插入验证：与 `zotero-word-mcp` 配合插入 Zotero 原生 Word 字段。
- EndNote 补充索引：使用 EndNote XML 导出建立本地 SQLite 检索库。

## 工作流程

### 1. 用户提供文献信息

输入可以是：

- PMID，例如 `32179076`
- DOI，例如 `10.1016/j.exer.2020.108002`
- DOI URL，例如 `https://doi.org/10.1016/j.exer.2020.108002`
- 含 PubMed 链接或 DOI 的 Markdown 文件

### 2. PubMed 验证

先用 `--pubmed-only` 确认文献是否真实存在：

```powershell
$env:PYTHONIOENCODING='utf-8'
& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' .\ref_workflow.py `
  --from-file 'F:\我的坚果云\Writing\wiki\200｜科研工作\202｜论文阅读与思考\S_neutrophils.md' `
  --pubmed-only
```

输出会包含 PMID、DOI、题名、年份和期刊。`failed = 0` 表示这一批被 PubMed 成功确认。

### 3. Zotero dry-run

确认文献真实后，先 dry-run，检查即将写入 Zotero 的条目：

```powershell
$env:ZOTERO_API_KEY=[Environment]::GetEnvironmentVariable('ZOTERO_API_KEY','User')
$env:ZOTERO_LIBRARY_ID=[Environment]::GetEnvironmentVariable('ZOTERO_LIBRARY_ID','User')
$env:PYTHONIOENCODING='utf-8'

& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' .\ref_workflow.py `
  --from-file 'F:\我的坚果云\Writing\wiki\200｜科研工作\202｜论文阅读与思考\S_neutrophils.md' `
  --dry-run `
  --tag '_MCP-test-to-delete'
```

dry-run 不会写入 Zotero，适合检查作者、题名、期刊、年份、DOI 和 PMID 是否正确。

### 4. 写入 Zotero

单条文献写入示例：

```powershell
$env:ZOTERO_API_KEY=[Environment]::GetEnvironmentVariable('ZOTERO_API_KEY','User')
$env:ZOTERO_LIBRARY_ID=[Environment]::GetEnvironmentVariable('ZOTERO_LIBRARY_ID','User')

& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' .\ref_workflow.py `
  '32179076' `
  --tag 'verified-by-pubmed-cli'
```

如果 Zotero 中已经有相同 DOI 或 PMID 的条目，脚本会返回 `status: exists` 和已有 `item_key`，不会重复创建。

### 5. 插入 Word 手稿

拿到 Zotero item key 后，用 `zotero-word-mcp` 插入 Word 原生 Zotero 字段：

```powershell
$env:ZOTERO_WORD_DLL='D:\Program Files\Zotero\integration\word-for-windows\libzoteroWinWordIntegration.dll'
$env:ZOTERO_SQLITE_PATH='C:\Users\Administrator\Zotero\zotero.sqlite'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONPATH='F:\GitHub\01_Projects\Ref\zotero-word-mcp\src'

& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' -m zotero_word_mcp.native_bridge `
  insert-citation `
  --doc 'path\to\manuscript.docx' `
  --find 'INSERT_CITATION' `
  --placement replace `
  --keys ITEMKEY

& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' -m zotero_word_mcp.native_bridge `
  insert-bibliography `
  --doc 'path\to\manuscript.docx' `
  --find 'References' `
  --placement after

& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' -m zotero_word_mcp.native_bridge `
  refresh `
  --doc 'path\to\manuscript.docx' `
  --wait-seconds 90
```

刷新成功后，`{Citation}` 和 `{Bibliography}` 会变成 Zotero 可识别的动态引文和参考文献表。

### 6. Word/PDF 验证

本项目优先验证两层结果：

- DOCX 字段层：用 Zotero Word 集成 DLL 探测 Word 文档，确认字段类型、数量和占位符是否已刷新。
- 可见输出层：用本机 Microsoft Word 导出 PDF，再检查引文、参考文献和 DOI 是否出现在可见输出中。

对当前写作环境而言，Word 直接导出的 PDF 比 LibreOffice/`soffice` 生成的 PDF 更接近真实手稿效果。

## 原理说明

### PubMed 验证

`ref_workflow.py` 调用 `pubmed-cli`，根据输入类型选择查询方式：

- PMID：直接 fetch。
- DOI：用 DOI 字段查询 PubMed。
- 普通文本：作为 PubMed 查询语句搜索。

PubMed 返回的文章信息会被标准化为 Zotero `journalArticle` 条目，包括题名、作者、期刊、年份、卷期页、DOI、PMID 和摘要。

### Zotero 写入与查重

脚本通过 Zotero Web API 获取 `journalArticle` 模板，并将 PubMed 结果映射为 Zotero 条目。

查重逻辑：

- DOI 存在时，按标准化 DOI 精确匹配。
- DOI 不存在时，按 PMID 匹配 Zotero 条目的 `extra` 或 `PMID` 字段。
- 空 DOI 不参与匹配，避免把无 DOI 文献错误识别为同一篇。

### Word 动态字段

`zotero-word-mcp` 写入的是 Zotero 原生 Word 字段，而不是普通文本引用。插入后必须调用 Zotero Refresh，让 Zotero 根据本地库数据生成正式引文和参考文献表。

这一步的目标是确保插入结果能被 Zotero 继续识别、修改和更新。

### EndNote 补充

`endnote-mcp` 使用 EndNote 导出的 XML 文件建立本地 SQLite 索引。它适合作为补充检索源，用来查找用户既有 EndNote 文献库中可能已经保存的文献。

当前默认只做元数据索引；PDF 全文索引可选，但耗时更长。

## 本地依赖

- Python：`C:\ProgramData\anaconda3\envs\hsiou\python.exe`
- PubMed CLI：`F:\GitHub\01_Projects\Ref\pubmed-cli\bin\pubmed.exe`
- Zotero SQLite：`C:\Users\Administrator\Zotero\zotero.sqlite`
- Zotero Word DLL：`D:\Program Files\Zotero\integration\word-for-windows\libzoteroWinWordIntegration.dll`
- EndNote XML：`F:\Download\My_Library_20250814.xml`
- EndNote PDF 目录：`F:\我的坚果云\2、工作文档\文献\My_Library_20250814.Data\PDF`

需要的用户环境变量：

- `ZOTERO_API_KEY`
- `ZOTERO_LIBRARY_ID`
- `ZOTERO_LIBRARY_TYPE=user`
- `ZOTERO_LOCAL=true`
- `ZOTERO_SQLITE_PATH`
- `ZOTERO_WORD_DLL`

Windows 下建议设置：

```powershell
$env:PYTHONIOENCODING='utf-8'
```

否则 Zotero 字段 payload 或中文路径可能在控制台输出时触发编码错误。

## EndNote MCP

查看 EndNote 索引状态：

```powershell
& 'C:\ProgramData\anaconda3\envs\hsiou\Scripts\endnote-mcp.exe' status
```

重建元数据索引：

```powershell
& 'C:\ProgramData\anaconda3\envs\hsiou\Scripts\endnote-mcp.exe' index --full --skip-pdfs
```

当前配置：

- XML export：`F:\Download\My_Library_20250814.xml`
- PDF directory：`F:\我的坚果云\2、工作文档\文献\My_Library_20250814.Data\PDF`
- SQLite index：`C:\Users\Administrator\AppData\Roaming\endnote-mcp\library.db`

## 测试与验证

运行单元测试：

```powershell
& 'C:\ProgramData\anaconda3\envs\hsiou\python.exe' -m unittest discover -s tests -v
```

已验证过的关键能力：

- 从 Markdown 中提取 PubMed 链接和 DOI。
- PubMed-only 批量验证。
- PubMed 结果映射为 Zotero 条目。
- DOI 查重和 PMID 兜底查重。
- Zotero 原生 Word 字段插入和刷新。
- Word 导出 PDF 后可见输出中包含插入的引文和 DOI。
- EndNote XML 元数据索引。

## 注意事项

- 不要直接在原始手稿上调试；先复制到 `artifacts/` 目录。
- `pubmed-cli/bin/` 是本机构建产物，已在上游仓库中忽略，不作为源码提交。
- 本机未安装 LibreOffice/`soffice` 时，Codex 的 DOCX 专用渲染器不能工作；本流程优先使用 Microsoft Word 导出 PDF 进行可见输出验证。
- EndNote XML 中可能存在重复 DOI，最终插入 Word 前应以 PubMed 和 Zotero 条目为准。
- `S_neutrophils.md` 中 PMC 或 Nature 页面链接不会被当前 PubMed 链接提取器自动识别，除非同时提供 PMID 或 DOI。

## 项目结构

```text
reference-workflow/
├── README.md
├── HANDOFF.md
├── ref_workflow.py
└── tests/
    └── test_ref_workflow.py
```

## 致谢

本项目是在以下开源项目和本地工具基础上构建的编排层，特此致谢：

- [drpedapati/pubmed-cli](https://github.com/drpedapati/pubmed-cli)：提供 PubMed 查询、抓取和结构化输出能力。
- [Zhangchaokai1/zotero-word-mcp](https://github.com/Zhangchaokai1/zotero-word-mcp)：提供 Word 中 Zotero 原生字段插入、探测和刷新能力。
- [54yyyu/zotero-mcp](https://github.com/54yyyu/zotero-mcp)：提供 Zotero MCP/Web API 工作流参考。
- [gokmengokhan/endnote-mcp](https://github.com/gokmengokhan/endnote-mcp)：提供 EndNote XML 本地索引和检索能力。

本项目主要负责把这些能力组合成适合本地学术写作的参考文献验证、入库、插入和更新流程。
