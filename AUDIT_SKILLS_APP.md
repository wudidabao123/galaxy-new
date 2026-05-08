# 🔍 Galaxy New — 代码审计报告: skills/builtin/* + app.py + config.py

**审计日期:** 2026-05-08
**审计范围:** 16个文件，深度代码审计

---

## 一、严重 Bug (会导致运行时崩溃)

### 🔴 BUG-01: `project_tools.py` 导入不存在的函数名
**文件:** `skills/builtin/project_tools.py`
**行号:** 顶部 import
```python
from skills.builtin.file_ops import _clip, _workspace_root
```
**问题:** `file_ops.py` 中实际函数名是 `_clip_output` 和 `_get_workspace_root`。
`_clip` 和 `_workspace_root` 两个名字都不存在。
**影响:** 文件 import 即崩溃，整个 project_tools 模块不可用。
**修复:** 改为 `from skills.builtin.file_ops import _clip_output as _clip`（或直接用 `_clip_output`）+ 将 `_workspace_root` 改为 `_get_workspace_root`。

### 🔴 BUG-02: `export.py` / `project_tools.py` 对 `file_ops` 的交叉依赖不安全
**文件:** 多个文件
**行号:** `export.py` L134 `from skills.builtin.file_ops import _get_workspace_root`
**问题:** `file_ops.py` 内部 `_get_workspace_root` 依赖 `from config import DATA_DIR` 和 `from data.database import get_db`，这在某些初始化阶段可能未就绪。多个模块都在函数体内做 lazy import 规避循环依赖，但错误处理不一致。
**影响:** 如果 `data.database` 模块未初始化，所有依赖 `_get_workspace_root` 的 tool 调用都会失败。
**严重级别:** 中高 — 取决于初始化顺序。

---

## 二、安全隐患

### 🟠 SEC-01: `patch_tools.py` — 未验证 patch 中的文件路径
**文件:** `skills/builtin/patch_tools.py`
**行号:** L56-77 `tool_patch_apply`
```python
proc = subprocess.run(
    ["git", "apply", "--verbose"],
    input=patch_content,
    cwd=str(root),
    ...
)
```
**问题:** `git apply` 会修改 patch 中声明的文件路径。如果 patch 包含 `../` 越界路径（如 `+++ b/../../etc/hosts`），git apply 可能直接写到 workspace 之外。`--verbose` 没有提供路径沙箱保护。
**影响:** 潜在路径穿越，攻击者可通过恶意 patch 写入系统文件。
**修复:** 在传给 `git apply` 之前，解析 `+++ b/...` 行并验证路径在 workspace 内。或使用 `--directory` + `--unsafe-paths` 组合限制作用域。

### 🟠 SEC-02: `patch_tools.py` / `shell.py` — `subprocess.run` 注入风险
**文件:** `skills/builtin/patch_tools.py` L85, `skills/builtin/shell.py`
**问题:** `patch_tools.py` L85-90 的 `tool_patch_reject` 直接拼接 `f"# Rejected: {reason or 'no reason given'}"` 到文件内容，不验证用户输入。如果 `reason` 包含特殊字符（如 `#` 换行），不会造成注入但会导致内容不干净。**不是高危注入**，但验证不足。

### 🟠 SEC-03: `web.py` — SSL 绕过机制全局共享状态
**文件:** `skills/builtin/web.py`
**行号:** L17-28
```python
_SSL_CTX = None if _SSL_VERIFY else _ssl.create_default_context()
if not _SSL_VERIFY:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = _ssl.CERT_NONE
```
**问题:** 这是一个模块级全局变量。如果多个线程同时使用 `_SSL_CTX`（None 时代表系统验证，非 None 时代表不安全），存在并发问题。不过 `urllib` 的 `urlopen` 每次会调用 `_SSL_CTX` 创建新连接，所以不是真正的 race condition，更多是代码结构问题。
**严重级别:** 低 — 模块级单例不可变，但不符合最佳实践。

### 🟠 SEC-04: `shell.py` 危险命令检测不完整
**文件:** `skills/builtin/shell.py`
**行号:** L55-58 `is_dangerous_command`
**问题:** 当前仅检测 `config.py` 中列出的 8 个模式。在 Windows 上缺少：
- `format` 命令（`format C:`）
- `cipher /w`（安全擦除）
- `icacls` 权限修改
- `net user` 账户操作
- `sc` / `net stop` 服务操作
- Base64 编码的命令绕过（如 `powershell -enc <base64>`）
- 环境变量展开绕过（如 `rm %TEMP%\*`）
**影响:** 攻击者可通过不在黑名单中的命令执行危险操作。
**修复:** 增加上述模式 + 检测 Base64 编码的 PowerShell 命令。

### 🟠 SEC-05: `web.py` — URL 重定向跟随无限制
**文件:** `skills/builtin/web.py`
**行号:** `tool_fetch_url` L92, `tool_web_search` L133+
**问题:** `urllib.request.urlopen` 默认跟随 HTTP 重定向。没有跨域限制或重定向次数限制。理论上可以用于 SSRF（Server-Side Request Forgery）探测内网。
**影响:** 中等 — 如果 agent 被诱导访问恶意 URL，可能被重定向到内网地址（如 `http://169.254.169.254/` 云元数据端点）。
**修复:** 自定义 `HTTPRedirectHandler`，限制重定向次数（最多 5 次），禁止重定向到内网 IP。

### 🟠 SEC-06: `file_ops.py` — `tool_safe_delete` 的 TOCTOU 竞态
**文件:** `skills/builtin/file_ops.py`
**行号:** L142-152 `tool_safe_delete`
```python
if not target.exists():
    return f"Error: file not found: {target}"
...
shutil.move(str(target), str(dest))
```
**问题:** 在 `exists()` 检查和 `move()` 之间，另一进程/线程可能删除该文件，导致 `move()` 失败且没有适当错误信息。不过错误被外层 `except` 捕获，仅返回 generic error。这是一个经典的 TOCTOU (Time-of-check Time-of-use) 问题。
**严重级别:** 低 — 并发场景下概率很低。
**修复:** 直接 try `shutil.move`，捕获 `FileNotFoundError` 即可。

### 🟠 SEC-07: `file_ops.py` — `tool_read_many_files` 路径注入
**文件:** `skills/builtin/file_ops.py`
**行号:** L109-116
```python
raw_paths = [p.strip() for part in paths.splitlines() for p in part.split(",")]
```
**问题:** 将逗号作为路径分隔符，但未考虑路径中包含逗号的情况。Agent 传入 `"a.txt, ../../secret.txt"` 可能绕过检测？
**分析:** `_safe_workspace_path` 会做 `resolve()` + 路径约束检查，所以实际上不会绕过。但路径分隔符逻辑不够健壮。
**严重级别:** 低 — 有 `_safe_workspace_path` 作为第二层防护。

---

## 三、设计缺陷与代码质量问题

### 🟡 DES-01: `export.py` — `PAPER_CSS` 是死代码
**文件:** `skills/builtin/export.py`
**行号:** L15-106
**问题:** 定义了 92 行 CSS 常量 `PAPER_CSS`，但从未被任何函数使用。`tool_export_markdown_pdf` 内部重新定义了另一份 CSS 字符串。
**影响:** 约 2.7KB 死代码，增加维护负担。
**修复:** 要么删除 `PAPER_CSS`，要么让 `tool_export_markdown_pdf` 使用它。

### 🟡 DES-02: `file_ops.py` — `_safe_workspace_path` 的路径穿越防护有缺陷
**文件:** `skills/builtin/file_ops.py`
**行号:** L28-32
```python
def _safe_workspace_path(path: str, *, root: Path) -> Path:
    candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path must stay inside workspace: {root}")
    return candidate
```
**问题:** 
1. 检查 `root not in candidate.parents` — 但 `parents` 不包括 root 本身，当 `candidate == root` 时 `root not in candidate.parents` 是 `True`，依赖前面的 `candidate != root` 短路。逻辑正确但隐蔽。
2. 在 Windows 上，`resolve()` 可能因为符号链接/挂载点产生奇怪的路径。`Path("C:/workspace").resolve()` 和 `Path("C:/Workspace").resolve()` 的大小写可能不同，但没有做 `casefold()` 比较。
**影响:** 特定边界条件下（如短文件名、大小写差异）可能误判。
**修复:** 使用 `candidate.resolve().as_posix().casefold()` 与 `root.resolve().as_posix().casefold()` 比较。

### 🟡 DES-03: `export.py` — 异常静默吞没（Silent Exception Suppression）
**文件:** `skills/builtin/export.py`
**行号:** L221-224, L228-230
```python
    except ImportError as e:
        pass  # fall through
    except Exception as e:
        pass  # fall through
```
**问题:** `tool_export_markdown_pdf` 中 weasyprint 路径捕获 `ImportError` 和 `Exception` 后都 `pass`。这些异常可能是严重的运行时错误（如字体缺失、内存不足），用户无法知道 why 降级到了 reportlab。
**影响:** 调试困难，用户不知道 PDF 生成为什么质量差。
**修复:** 至少 log 或返回 warning 信息。

### 🟡 DES-04: `python_exec.py` — `safe_builtins` 不够安全
**文件:** `skills/builtin/python_exec.py`
**行号:** L22-45
```python
safe_builtins = {
    k: getattr(_bltin, k) for k in [
        'abs','all','any', ..., 'type', ..., 'NotImplemented',
    ]
}
```
**问题:**
1. 允许了 `type` — 可以用来动态创建类，这可能被滥用。
2. 允许了 `exec` 的 sandbox 内代码访问 `__builtins__` 字典本身（因为 `getattr`、`type` 都在白名单中），可以被用来逃逸沙箱或调用 `eval`。
3. 没有 `time` 模块 — Agent 无法做延时操作是好事（故意限制），但某些科学计算库可能需要 `time`。
4. **最重要:** `exec(code, {"__builtins__": safe_builtins}, {})` 创建了一个新的 global namespace。但如果代码中包含 `import os`，`os` 模块内部仍会使用真实的 builtins（因为模块的 `__builtins__` 来自它自己的 module-level dict），所以 `os.system("rm -rf /")` 可以执行。
**严重级别:** 中等 — 沙箱存在已知逃逸路径。
**修复:** 至少应：
- 移除 `type`, `getattr`, `hasattr` 等危险内置函数
- 添加 `import` 钩子阻止危险模块导入
- 考虑使用 `RestrictedPython` 或 `pypy-sandbox` 进行真正的沙箱化

### 🟡 DES-05: `charts.py` — 缺少输入边界检查
**文件:** `skills/builtin/charts.py`
**行号:** L42-60 `tool_chart_line`, `tool_chart_bar` 等
**问题:**
- `data_json` 可能包含任意数量的数据点 — 没有限制数组长度。传入 100 万个数据点会导致 OOM。
- `output_name` 可能包含路径分隔符 `/`、`\`，可能导致文件写入非预期位置。
**影响:** 中等 — 拒绝服务（DoS）。
**修复:** 
- 限制 series/items 数量上限（如 500）
- 对 `output_name` 做 `os.path.basename` 处理或使用 `re.sub(r'[<>:"/\\|?*]', '_', name)`

### 🟡 DES-06: `academic.py` — project_id 未验证
**文件:** `skills/builtin/academic.py`
**行号:** L43 `tool_academic_section_save`, L57 `tool_academic_markdown_save` 等
```python
proj = _project_dir(project_id)
if not proj.exists():
    return f"Error: project {project_id} not found"
```
**问题:** `project_id` 由用户传入，直接拼接到 `ACADEMIC_DIR / project_id`。如果传入 `"../../config"` 等路径穿越字符串，会在 `_project_dir` 中越界。
**分析:** `_project_dir` 只做了字符串拼接 `ACADEMIC_DIR / project_id`，没有 `resolve()` 检查。外部模块的 `_safe_workspace_path` 检查仅适用于 workspace 路径，不适用于 GENERATED_DIR。
**严重级别:** 中等 — 文件可能被写到 GENERATED_DIR 之外。
**修复:** 对 `project_id` 做 `re.fullmatch(r'[a-zA-Z0-9_-]+', project_id)` 验证。

### 🟡 DES-07: `contract_tools.py` — 缺少输入长度限制
**文件:** `skills/builtin/contract_tools.py`
**行号:** L14-18 `tool_contract_write`
**问题:** `content` 和 `run_id` 都没有长度限制。Agent 可能写入超大合同文件导致磁盘被填满。
**影响:** 低 — 但建议添加 max 500KB 限制。

### 🟡 DES-08: `academic.py` — `tool_academic_reference_add` 重复检测不精确
**文件:** `skills/builtin/academic.py`
**行号:** L98-108
```python
if cite_key in existing:
    return f"Reference '{cite_key}' already exists. Not duplicated."
```
**问题:** 使用简单的子串匹配 `cite_key in existing`。如果 cite_key="smith2020"，而 existing 中包含 "smith2020a"，会误判为重复。应该用正则匹配 `@\w+\{cite_key,\b`。

### 🟡 DES-09: `project_tools.py` — `skill_dependency_scan` 和 `skill_project_tree_summary` 与 `git_tools.py` 中的 `tool_dependency_scan` / `tool_project_tree_summary` 重复
**文件:** `skills/builtin/project_tools.py` vs `skills/builtin/git_tools.py`
**问题:** 两个模块各实现了一套功能相似但接口不同的 scan/summary 工具。`git_tools.py` 的版本是旧版（返回纯文本），`project_tools.py` 的版本是新版（返回 JSON/结构化文本）。这会导致：
- Agent 可能调用到旧版本
- 维护负担加倍
**修复:** 废弃 `git_tools.py` 中的旧版本或统一接口。

### 🟡 DES-10: `shell.py` — `detect_shell()` 有副作用
**文件:** `skills/builtin/shell.py`
**行号:** L23-41
```python
def detect_shell() -> str:
    # Check for Git Bash first
    try:
        r = subprocess.run(["bash", "--version"], capture_output=True, timeout=5)
        ...
    # Check for PowerShell
    try:
        r = subprocess.run(["powershell", "-Command", "echo test"], ...)
        ...
```
**问题:** 每次调用都执行 1-2 个子进程来检测 shell，而且 `timeout=5` 秒。如果用户机器上没有 bash 或 PowerShell（例如精简 Docker 容器），每次 tool 调用都会浪费 5-10 秒。
**影响:** 性能问题 — 每次 `tool_terminal` 调用（未指定 shell 时）都会先检测。
**修复:** 缓存检测结果到模块级变量，只检测一次。

### 🟡 DES-11: `python_exec.py` — `tool_run_tests` 递归委托给 shell
**文件:** `skills/builtin/python_exec.py`
**行号:** L88-90
```python
def tool_run_tests(command: str = "pytest", timeout_seconds: int = 120) -> str:
    from skills.builtin.shell import tool_terminal
    return tool_terminal(command, timeout_seconds=timeout_seconds)
```
**问题:** 
1. 默认命令 `"pytest"` 需要当前目录有 `pytest`，否则会执行失败且错误信息不友好（shell 的 "command not found"）。
2. **最大问题是** `tool_terminal` 签名使用 `timeout_seconds` 参数名，但 `tool_run_tests` 也使用 `timeout_seconds` — 虽然看起来一致，但如果将来 `tool_terminal` 改了参数名就会悄无声息地断掉（没有类型检查）。
**严重级别:** 低 — 功能正常但脆弱。

### 🟡 DES-12: `env_manager.py` — `tool_env_install` 只验证 package 名称，不验证来源
**文件:** `skills/builtin/env_manager.py`
**行号:** L52-57
```python
if any(c in name for c in [";", "&&", "||", "|", "`", "$"]):
    return "Error: package name contains unsafe characters"
```
**问题:** 黑名单不完整。`pip install` 支持 `-r`, `--index-url`, `-e` 等参数。Agent 传入 `"-r malicious_requirements.txt"` 作为 package 名即可绕过检测，安装任意包。
**影响:** 中等 — 任意包安装可能导致供应链攻击。
**修复:** 白名单模式 — 只允许 `^[a-zA-Z0-9_.-]+(==[a-zA-Z0-9_.*]+)?(\[.*\])?$`。

---

## 四、边界条件处理缺失

### 🟡 EDGE-01: `charts.py` — 空数据导致 matplotlib 崩溃
**文件:** `skills/builtin/charts.py`
**行号:** L36-45 `tool_chart_line`, L50-58 `tool_chart_bar`
```python
for s in series_list:
    ax.plot(s.get("x", []), s.get("y", []), ...)
```
**问题:** 如果 `series_list` 为空列表，会创建一个空图（无数据点），`savefig` 仍然会生成空白 PNG，但 matplotlib 可能会产生大量 warning。如果 `x=[]`, `y=[]` 导致 `plot()` 返回空列表（len(x) 和 len(y) 不匹配），也会报错。不过 `matplotlib` 对空数据会生成 empty plot 而不是 crash。
**严重级别:** 低 — 不会崩溃，但输出质量差。

### 🟡 EDGE-02: `academic.py` — `tool_academic_table_generate` rows 和 headers 长度不匹配
**文件:** `skills/builtin/academic.py`
**行号:** L83-94
```python
for row in rows:
    lines.append("| " + " | ".join(str(c) for c in row) + " |")
```
**问题:** 如果某行元素数量与 headers 不一致（多/少列），Markdown 表格会畸形渲染，但没有报错/警告。
**影响:** 低 — Markdown 解析器通常能容错。

### 🟡 EDGE-03: `web.py` — `tool_web_search` 当 DuckDuckGo 返回 403/429 时无重试和降级
**文件:** `skills/builtin/web.py`
**行号:** L133-180
**问题:** DuckDuckGo 对高频请求会返回 403。当前代码没有速率限制、没有指数退避重试、没有 User-Agent 轮换。Bing 也可能同样被限流。
**影响:** 中 — 短时间内多次搜索会全部失败。
**修复:** 添加简单的退避重试 +速率限制。

### 🟡 EDGE-04: `snapshot_tools.py` — `tool_conflict_check` 不处理空字符串
**文件:** `skills/builtin/snapshot_tools.py`
**行号:** L50-69
```python
norm_a = path_a.replace("\\", "/").strip("/")
norm_b = path_b.replace("\\", "/").strip("/")
```
**问题:** 如果 `path_a` 或 `path_b` 为空字符串，`strip("/")` 返回 `""`，然后 `if norm_a == norm_b` 为 True（两个空串相等），错误报告冲突。但没有提前检查空值。
**影响:** 低 — 不会崩溃，但返回误导性的冲突报告。

### 🟡 EDGE-05: `git_tools.py` — `tool_git_diff` 对未被 git 管理的目录行为
**文件:** `skills/builtin/git_tools.py`
**行号:** L27-44
**问题:** 如果 workspace 不在 git 仓库中，`git status` 和 `git diff` 会返回非零 exit code 并输出错误到 stderr。当前代码混合显示 stdout 和 stderr，输出会很难看。
**影响:** 低 — 不会崩溃，但错误信息不友好。

### 🟡 EDGE-06: `shell.py` — `tool_run_script` 对未知扩展名用 shell 执行
**文件:** `skills/builtin/shell.py`
**行号:** L86-110
```python
else:
    # Try shell execution
    return tool_terminal(f'"{full_path}"', timeout_seconds=timeout_seconds)
```
**问题:** 对未知扩展名的文件直接用 shell 执行，可能执行恶意文件（如 `.bat`, `.cmd`, `.vbs`）。在 Windows 上 `.bat`、`.cmd` 都不在已知列表中。
**影响:** 中 — 遗漏了 `.bat`、`.cmd` 等常见脚本扩展。

---

## 五、资源泄漏

### 🔵 RES-01: `web.py` — HTTP 连接可能未关闭
**文件:** `skills/builtin/web.py`
**行号:** L91-98 `tool_fetch_url`
```python
with _urlopen(req, timeout=20) as resp:
    ...
    raw = resp.read(2_000_000)
text = raw.decode("utf-8", errors="replace")
```
**问题:** 如果 `resp.read()` 抛出异常（如连接中断），`with` 语句会正确关闭连接。但如果 `raw.decode()` 异常，则可能在 with 块结束后才抛异常 — 这没问题，因为 with 的 `__exit__` 已在 read 后执行。实际上没有泄漏。
**分析:** 经过深入检查，所有 HTTP 操作都使用了 `with` 语句，没有连接泄漏。**这是误报。**

### 🔵 RES-02: `charts.py` — matplotlib figure 可能泄漏
**文件:** `skills/builtin/charts.py`
**行号:** 各 chart 函数
```python
fig, ax = plt.subplots(...)
...
return _save_plot(fig, output_name)
```
**问题:** `_save_plot` 内部调用 `plt.close(fig)`，但如果 `fig.savefig` 抛出异常，`plt.close` 不会执行，figure 泄漏。
**影响:** 中 — 多次失败会累积 figure 对象，消耗内存。
**修复:** 在 `_save_plot` 中使用 `try-finally`：
```python
def _save_plot(fig, name):
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / f"{name}_{uuid.uuid4().hex[:6]}.png"
    try:
        fig.savefig(str(path), dpi=150, bbox_inches="tight")
        import matplotlib.pyplot as plt
        return json.dumps({"path": str(path), "file": path.name}, ensure_ascii=False)
    finally:
        import matplotlib.pyplot as plt
        plt.close(fig)
```

### 🔵 RES-03: `export.py` — ZIP 文件句柄
**文件:** `skills/builtin/export.py`
**行号:** L285-288
```python
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for f in proj.rglob("*"):
        if f.is_file():
            zf.write(f, f.relative_to(proj))
```
**问题:** 使用了 `with` 语句，ZIP 文件正确关闭。**无泄漏。**

### 🔵 RES-04: `env_manager.py` — subprocess 管道泄漏
**文件:** `skills/builtin/env_manager.py`
**行号:** L60-70
```python
proc = subprocess.run(
    [sys.executable, "-m", "pip", "install", name],
    capture_output=True, text=True, timeout=120,
)
```
**问题:** `subprocess.run` 会等待进程结束并自动关闭管道。**无泄漏。**

---

## 六、返回值不一致

### 🟣 RET-01: 错误返回格式不一致
**跨文件问题:** 不同模块用不同格式返回错误：
- `"Error: xxx"` 字符串 — `file_ops.py`, `patch_tools.py` 等
- `f"Error: project {project_id} not found"` — `academic.py`
- `json.dumps({...}, ...)` 成功，`"Error: xxx"` 失败 — `export.py`

**问题:** Agent 需要根据返回值是否为 `"Error:"` 前缀来判断成功/失败，缺乏结构化标准。
**修复:** 统一使用 JSON 格式返回 `{"success": bool, "error": str/null, "data": ...}`。

### 🟣 RET-02: `git_tools.py` — `tool_project_tree_summary` 和 `project_tools.py` — `skill_project_tree_summary` 返回格式不同
**文件:** `skills/builtin/git_tools.py` L77-112 vs `skills/builtin/project_tools.py` L57-90
**问题:** 两个 "project tree summary" 函数返回格式不同（旧版返回纯文本树，新版返回结构化列表+文件大小）。如果 agent 调用旧版，可能解析失败。

---

## 七、其他问题汇总

### ⚪ MISC-01: `config.py` — `RUNTIME_DIRS` 包含 `PROJECT_ROOT` 很奇怪
**文件:** `config.py`
**行号:** L29-34
```python
RUNTIME_DIRS = [
    UPLOADS_DIR, GENERATED_DIR, RUNS_DIR,
    CONTRACTS_DIR, HANDOFFS_DIR, DIFFS_DIR, PATCHES_DIR,
    AVATARS_DIR,
    # DB dir stays in project root
    PROJECT_ROOT,
]
```
**问题:** 注释说 "DB dir stays in project root"，但 `PROJECT_ROOT` 是整个项目根目录，不光是 DB。如果 `RUNTIME_DIRS` 被用于自动创建目录，整个 PROJECT_ROOT 不应该列在其中（它已经存在了）。这可能是个设计 bug。
**严重级别:** 低 — 取决于 `RUNTIME_DIRS` 的使用方式。

### ⚪ MISC-02: `app.py` — 缺少错误边界
**文件:** `app.py`
**行号:** L15-22
```python
from data.database import init_db
init_db()
from skills import register_all_skills
register_all_skills()
```
**问题:** 如果 `init_db()` 或 `register_all_skills()` 抛出异常，Streamlit 启动失败但没有明显的错误页面。没有 try-except 包裹关键初始化代码。
**影响:** 中 — 启动失败时用户体验差（直接 Traceback）。
**修复:** 添加 try-except 并在 Streamlit UI 中显示友好的错误消息。

### ⚪ MISC-03: `python_exec.py` — `tool_json_parse` 返回值不一致
**文件:** `skills/builtin/python_exec.py`
**行号:** L63-77
```python
if isinstance(data, list):
    return f"JSON array, ... Keys: {list(data[0].keys()) if data and isinstance(data[0], dict) else 'N/A'}"
```
**问题:** 当数组第一个元素不是 dict 时返回 `"Keys: N/A"` — 但没有展示数组的实际内容。Agent 不知道数组里是什么。
**影响:** 低 — 信息不足但不会出错。

### ⚪ MISC-04: `export.py` — `tool_export_markdown_pdf` 的 weasyprint 路由忽略 `output_name` 参数
**文件:** `skills/builtin/export.py`
**检查:** 是否在所有路径都使用了 `output_name`...
- Weasyprint 路径: 使用 `dest = EXPORTS_DIR / f"{name}_{uuid.uuid4().hex[:6]}.pdf"` 其中 `name = output_name or src.stem` — ✓ 正确
- Reportlab 路径: 同样 — ✓ 正确
**无问题。**

### ⚪ MISC-05: `academic.py` — `tool_academic_project_create` 的返回值 stringify 问题
**文件:** `skills/builtin/academic.py`
**行号:** L35
```python
return json.dumps({"project_id": pid, "path": str(proj_dir)}, ensure_ascii=False, indent=2)
```
**问题:** `str(proj_dir)` 在 Windows 上返回 `E:\...\academic\abc123`（反斜杠路径）。`json.dumps` 会转义反斜杠为 `\\`，返回 `"E:\\...\\academic\\abc123"`。Agent 解析后可能需要手动 unescape。
**影响:** 低 — `json.loads` 能正确处理。

---

## 八、审计总结

| 类别 | 数量 | 关键发现 |
|------|------|----------|
| 🔴 严重 Bug | 1 | `project_tools.py` 导入不存在的函数 `_clip`, `_workspace_root` |
| 🟠 安全隐患 | 7 | 路径穿越、patch 注入、SSL 绕过共享状态、危险命令检测不完整、沙箱逃逸、SSRF 风险 |
| 🟡 设计缺陷 | 12 | 死代码、异常静默吞没、重复工具、性能问题、沙箱不完整等 |
| 🟡 边界条件 | 6 | 空数据、路径穿越、限流无重试等 |
| 🔵 资源泄漏 | 1 | matplotlib figure 在异常路径下可能泄漏 |
| 🟣 返回不一致 | 2 | 错误格式不统一、同名函数返回格式不同 |
| ⚪ 其他 | 5 | 配置问题、缺少错误边界、返回值信息不足等 |

### 修复优先级

1. **立即修复:** BUG-01 (`project_tools.py` 导入错误) — 会导致模块崩溃
2. **高优先级:** SEC-01 (patch 路径穿越), DES-04 (沙箱逃逸), SEC-02 (patch 注入)
3. **中优先级:** SEC-05 (SSRF), DES-06 (project_id 路径穿越), RES-02 (figure 泄漏)
4. **低优先级:** 其余所有发现
