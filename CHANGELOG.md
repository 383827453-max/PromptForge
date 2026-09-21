# Changelog

本文件记录 PromptForge 的所有重要变更。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.3.0] - 2026-09-21

`llmclient` 拆分为独立仓库。

### 变更

- **`llmclient` 移出本仓库**，成为独立项目：
  **https://github.com/383827453-max/llmclient**
  - 单一代码源，不再有「内嵌子包」与「独立发布」两份需要同步的风险
  - 用 `git subtree split` 保留完整提交历史
  - 独立仓库自带 CI（Linux/Windows/macOS × Python 3.9/3.12/3.13 + ruff +
    构建 sdist/wheel + twine check + 装 wheel 验证公开 API）、LICENSE、
    CHANGELOG、MANIFEST.in
  - 已打 tag `v0.1.0`
- 本仓库改为**按 tag 钉版本**的 git 依赖：
  `llmclient @ git+https://github.com/383827453-max/llmclient.git@v0.1.0`
  上游改动不会自动影响本应用，升级需显式改版本号
- `promptforge/llm_client.py` 简化为纯转发层（删掉 `sys.path` 回退 hack，
  已成为普通依赖，不再需要）
- `PromptForge.spec` 删掉 `pathex` 与 `hiddenimports` 手工兜底
  （llmclient 现在装在 site-packages，PyInstaller 能自动找到）
- CI 不再需要单独安装/测试子包；改为安装后验证依赖确实解析到位
- README 更新仓库结构、安装方式与「如何修改 LLMClient」章节

### 安装方式变化

```bash
# 旧（monorepo）
pip install -e ./llmclient && pip install -e .

# 新（独立仓库依赖，一条命令）
pip install -e .
```

### 独立使用 llmclient

```bash
pip install "git+https://github.com/383827453-max/llmclient.git@v0.1.0"
```

## [1.2.0] - 2026-09-21

三项工程改进：抽出可复用客户端包、API Key 加密存储、多模型并发对比。

### 新增

- **`llmclient` 独立包**（`llmclient/`，src layout）
  - 把网关兼容逻辑从应用里抽出来，消除同一套代码在多个项目重复维护
  - 无 GUI 依赖，只要 `requests`；cfg 为鸭子类型，宿主可用自己的配置类
  - 新增 `list_models()` / `probe_models()` / `probe_chat()` / `probe()`：
    带计时的端点探测，单次失败不抛异常，方便批量扫一堆网关
  - 43 个单测；`promptforge/llm_client.py` 保留为兼容层，含路径回退，
    从仓库根直接 `python run.py` 无需先安装
- **多模型并发对比**（`compare.py` + `ui/compare_tab.py`）
  - 同一提示词同时发往多个 API 配置，并排比较输出
  - 记录**首字延迟（TTFT）与总耗时**，区分「慢在首字」和「慢在生成」
  - 耗时排名 + 一句话结论（最快 / 最长 / 耗时差）
  - 单个配置失败不影响其他结果；支持整轮取消
  - 对比引擎与 GUI 解耦（`CompareRunner`），27 个单测覆盖并发、取消、排名
- **API Key 加密存储**（`credential.py`）
  - Windows 用 DPAPI（`CryptProtectData`）加密，密文绑定当前用户账户
  - 旧版明文配置平滑迁移：读出可用，下次保存自动转密文
  - 换机器/换用户解不开时置空该 Key 并保留其余配置，不清空整份配置
  - 幂等保存：配置未变则复用原密文，文件内容不抖动
  - 非 Windows 降级为机器指纹派生密钥 + 完整性校验（非安全边界，仅防明文裸奔）
  - POSIX 下 `chmod 0600` 收紧权限
- **端到端验证脚本**（`tools/e2e_check.py`）
  - 起本地 OpenAI 兼容 mock 网关（快/慢/报错三种模型），无需 API Key
  - 真实验证流式解析、协作式取消、并发对比、失败隔离
  - 断言并发确实生效（墙钟 ≈ 最慢单请求，而非各请求之和）
- 主窗口标签索引常量 `TAB_MAIN` / `TAB_COMPARE` / …，去掉散落的魔法数字

### 变更

- 主窗口从 4 个标签变为 5 个（新增「多模型对比」）
- `requirements.txt` 注明需先安装 `llmclient` 子包
- CI 增加：`llmclient` 测试、e2e 检查、对 `tools/` 与 `llmclient/` 的 ruff 检查
- PyInstaller spec 显式声明 `pathex=['llmclient\\src']` 与 hiddenimports

### 修复

| 位置 | 问题 | 后果 |
|---|---|---|
| `compare.py` | `parse_notes_bullets` 用 `split(" ")` 剥序号 | `1、中文序号` 这种无空格写法切不开，条目丢失 |
| `compare.py` | `diff_summary` 只报一个「最长」 | 字符数并列时信息不完整 |
| `tools/e2e_check.py` | mock 网关用单线程 `HTTPServer` | 并发请求被服务端排队，并发收益测不出来、排名断言不稳定 |
| `config.py` | 密文复用未校验旧值确实是密文 | 旧明文被判定为「未变」而沿用，**迁移永远不生效，Key 一直以明文躺盘** |

### 说明

`promptforge/llm_client.py` 的 `complete()` 现在也显式关闭响应
（v1.1.0 的 CHANGELOG 提前记了这条，实际落在本版）。

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
