# Changelog

本文件记录 PromptForge 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.1.0] - 2026-09-15

### 新增
- **测试套件**（`tests/`，117 个用例）：覆盖配置读写、模板填充、SSE 解析、
  历史库 CRUD、增强引擎解析降级，以及 offscreen GUI 冒烟测试
- **GitHub Actions CI**（`.github/workflows/ci.yml`）：
  Windows + Linux × Python 3.9/3.12/3.13 矩阵跑测试，ruff 静态检查，
  main 分支构建 exe 并做「启动后存活 12 秒」的冒烟验证
- **`pyproject.toml`**：PEP 621 元数据、`pip install -e .[dev]` 可安装、
  pytest 与 ruff 配置、包内资源声明
- **协作式取消**：`LLMClient.stream()` 新增 `should_stop` 参数，
  `EnhanceWorker.request_stop()` 替代 `QThread.terminate()`
- **原子写入**：`settings.json` 与 `user_templates.json` 改为
  临时文件 + `os.replace`，避免写入中断导致配置损毁
- **CHANGELOG.md**（本文件）

### 修复
| 位置 | 问题 | 后果 |
|---|---|---|
| `ui/main_window.py` | `_save_settings` 里导入路径写成 `from .app`（`app` 在 `promptforge/`，不在 `ui/`） | **设置页点保存必崩** |
| `templates.py` | `_load` 用 `Template(builtin=builtin, **t)`，而 `save_user` 落盘的 JSON 自带 `builtin` 键 | **新建模板保存后永远不显示**（重复关键字参数异常被吞） |
| `config.py` | `Settings(**raw)` / `ApiConfig(**p)` 遇未知键抛 `TypeError` | **用户 API Key 与全部配置档案被静默清空** |
| `llm_client.py` | 引用 `requests.SSLError`（未导出，应为 `requests.exceptions.SSLError`） | **错误处理器自身崩溃**，SSL 故障时用户看不到诊断信息 |
| `llm_client.py` | 非流式 `complete()` 未关闭响应 | 连接泄漏 |
| `templates.py` | `fill()` 用 `"{{"+k+"}}"` 字面量替换 | `{{ 主题 }}`（带空格）替换不掉，**占位符泄漏进最终提示词** |
| `enhancer.py` | 只输出 `<notes>` 时标签被当作增强结果 | **脏数据写进历史库并复制到剪贴板** |
| `enhancer.py` | `USER_STRATEGY_DIR` 在 import 时定死 | 环境变量重定向数据目录后，自定义策略永不生效 |
| `templates.py` | `USER_PATH` 在 import 时定死 | 同上，自定义模板读不到 |
| `app.py` | `apply_current_theme` 在模块级 `_app` 为 None 时静默跳过 | **换肤不生效且无任何提示** |
| `database.py` | `LIKE` 未转义 `%` / `_` | 搜 `100%` 命中全部记录 |
| `database.py` | 仅按 `ts DESC` 排序，而 `ts` 精度为秒 | 同秒记录顺序不稳定，列表顺序错乱 |
| `main_window.py` | `_apply_hotkey` 每次新建 `QShortcut` 不回收 | 每存一次设置多注册一个快捷键，最终触发 N 次 |
| `ui/main_window.py` | `on_cancel` / `closeEvent` 用 `QThread.terminate()` | 强杀线程导致 socket 悬空、句柄泄漏、随机崩溃 |

### 变更
- 版本号统一为 `1.1.0`（`pyproject.toml` 与 `promptforge/__init__.py`）
- `.gitignore` 补充 `.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`

## [1.0.0] - 2026-09-15

### 新增
- 首个公开版本
- 一键增强提示词，四种增强策略（通用 / 编程 / 绘画 / 写作）
- OpenAI 兼容接口客户端，SSE 流式输出 + 非流式降级
- 对比视图、增强点说明、多轮迭代
- SQLite 历史记录（搜索 / 筛选 / 收藏 / 删除）
- 模板库（8 个内置 + 自定义 `{{变量}}` 填充）
- 多套 API 配置、脱敏显示、深色/浅色主题
- PyInstaller 单文件 exe 打包
