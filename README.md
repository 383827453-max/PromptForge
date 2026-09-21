# PromptForge 提示词工坊

一键增强提示词的 Windows 桌面工具。输入原始提示词，选增强策略，一键产出结构化、可直接投入使用的高质量提示词。

`PySide6` + `SQLite` + OpenAI 兼容接口，纯本地运行，数据不出机器。

---

## 功能特性

- **一键增强** — 调用任意 OpenAI 兼容 API（官方接口 / 自建网关 / 中转站均可），把口语化需求改写为结构化提示词
- **四种增强策略** — 通用 / 编程 / 绘画 / 写作，每种独立元提示词模板，可自定义覆盖
- **流式输出** — SSE 实时增量渲染；网关不支持时可一键降级为非流式
- **对比视图** — 原文与增强版左右对照
- **增强点说明** — 逐条解释每处修改理由（`<notes>` 区块）
- **多轮迭代** — 「再次增强」把当前结果作为新输入继续优化
- **历史记录** — SQLite 本地存储，搜索 / 按策略筛选 / 收藏 / 删除
- **模板库** — 8 个内置场景模板 + 自定义模板，支持 `{{变量}}` 占位符弹窗填充
- **多套 API 配置** — Base URL / Key / 模型随意切换，状态栏脱敏显示
- **双主题** — 深色科技风 / 浅色，快捷键快速聚焦输入框（默认 `Ctrl+Alt+P`）

## 环境要求

- Windows 10/11
- Python 3.9+（开发运行）
- 任意 OpenAI 兼容接口（本地网关 / 官方 API / 中转站）

## 快速开始

```bash
pip install -r requirements.txt
python run.py
```

首次使用：打开「设置」页 → 填 Base URL（如 `http://127.0.0.1:8080/v1`）、API Key、模型名 → 点「测试连接」验证。

**Base URL 归一化规则**（`llm_client.build_endpoint`）：

| 你填的 | 实际请求地址 |
|---|---|
| `http://127.0.0.1:8080` | `http://127.0.0.1:8080/v1/chat/completions` |
| `http://127.0.0.1:8080/v1` | `http://127.0.0.1:8080/v1/chat/completions` |
| `http://x/v1/chat/completions` | 原样使用 |

设置页会实时显示「实际请求地址」预览，填错立刻能看出来。

## 打包单文件 exe

```bat
build.bat
```

产物位于 `dist\PromptForge.exe`（约 54 MB，PyInstaller onefile + UPX）。

也可用 spec 文件构建：

```bat
python -m PyInstaller --noconfirm --clean PromptForge.spec
```

## 数据存储

所有数据仅存本地 `%APPDATA%\PromptForge\`（可用环境变量 `PROMPTFORGE_DATA_DIR` 重定向）：

| 文件 | 内容 |
|---|---|
| `settings.json` | API 配置与偏好设置（**含明文 API Key，注意保管**） |
| `history.db` | 历史记录（SQLite） |
| `user_templates.json` | 自定义模板 |
| `strategies/*.md` | 用户自定义策略（同名覆盖内置） |

## 项目结构

```
promptforge/
├── app.py                 # 应用入口、资源路径解析、主题应用
├── config.py              # 配置管理（多配置档案、脱敏）
├── database.py            # SQLite 历史记录
├── llm_client.py          # OpenAI 兼容客户端（SSE 流式/非流式、重试、诊断）
├── enhancer.py            # 增强引擎（策略装配 + <enhanced>/<notes> 解析）
├── templates.py           # 模板库（内置 + 用户）
├── theme.py               # 深色/浅色 QSS
├── strategies/            # 四种增强策略元提示词（Markdown）
│   ├── general.md
│   ├── coding.md
│   ├── drawing.md
│   └── writing.md
├── templates_builtin/     # 内置场景模板
│   └── templates.json
└── ui/
    ├── main_window.py     # 四标签主窗口
    ├── dialogs.py         # 模板填充 / 编辑对话框
    └── workers.py         # QThread 工作线程（增强、连通性测试）
```

## 自定义策略

在 `%APPDATA%\PromptForge\strategies\` 放 `general.md` / `coding.md` / `drawing.md` / `writing.md`，同名即覆盖内置策略，无需改代码。

策略模板必须包含两个占位符：

- `{original_prompt}` — 用户原始提示词
- `{extra_instructions}` — 附加要求区块（为空时替换成空串）

并约定模型按如下格式输出，`enhancer.parse_output` 据此解析：

```
<enhanced>
增强后的完整提示词
</enhanced>
<notes>
增强点说明，3-5 条
</notes>
```

模型不按格式输出时自动降级：去掉 `<notes>` 区块后整体作为增强结果展示。

## 已知行为与故障排查

| 现象 | 原因 / 处置 |
|---|---|
| 中文显示为乱码 | 已强制按 UTF-8 解码响应；若仍异常说明网关返回非 UTF-8 |
| 返回文字后卡住一会 | 已加 `Connection: close` 强制短连接；仍卡则关掉流式输出 |
| 读取超时 | Base URL 大概率不是 OpenAI 兼容接口（填了普通网站地址），看错误提示里的实际请求地址 |
| 测试连接卡 UI | 已在 `TestWorker` 后台线程执行，不应再卡；若卡请确认版本 |
| 设置里 Key 显示为 `abcd******wxyz` | 正常，状态栏脱敏显示，实际请求用完整 Key |
| 自定义策略/模板改了没反应 | 路径为 `%APPDATA%\PromptForge\strategies\` 与 `user_templates.json`；可用环境变量 `PROMPTFORGE_DATA_DIR` 重定向数据目录 |

## 开发

```bash
pip install -e ".[dev]"     # 或 pip install -r requirements.txt

python -m pytest tests -v   # 跑测试（含 offscreen GUI 冒烟）
python -m ruff check .      # 静态检查
python -m compileall -q promptforge tests
```

测试全部在临时数据目录里运行（`conftest.py` 自动重定向
`PROMPTFORGE_DATA_DIR`），不会污染你的 `%APPDATA%\PromptForge`。
GUI 用例设置 `QT_QPA_PLATFORM=offscreen`，无需显示器。

CI 见 `.github/workflows/ci.yml`：Windows + Linux × Python 3.9/3.12/3.13
矩阵跑测试，ruff 静态检查；main 分支推送时构建 exe 并做「启动后存活 12 秒」
的冒烟验证。

## 安全提示

- `settings.json` 里的 API Key 为**明文存储**，请勿把该文件提交到任何仓库（`.gitignore` 已排除）
- 本工具只把提示词发往你自己配置的 API 地址，无任何遥测、无第三方回传

## 版本历史

见 [CHANGELOG.md](CHANGELOG.md)。

## License

MIT © 2026 Liu
