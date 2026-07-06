# Publishing

## 1. 创建 GitHub 仓库

先在 GitHub 上创建一个空仓库：

- `zotero-word-mcp`

不要勾选初始化 README、`.gitignore` 或 License。

## 2. 初始化本地仓库

```powershell
git init
git add .
git commit -m "Initial release"
git branch -M main
git remote add origin git@github.com:Zhangchaokai1/zotero-word-mcp.git
git push -u origin main
```

## 3. 验证

- 检查 `README.md` 是否正常显示
- 检查 `pyproject.toml` 中仓库链接是否正确
- 检查 `docs/DEVELOPMENT_REVIEW.md` 是否可访问

## 4. MCP 客户端配置示例

```toml
[mcp_servers.zotero-word]
command = "python"
args = ["-m", "zotero_word_mcp"]
```
