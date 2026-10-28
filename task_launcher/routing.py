"""Generation of ``routing.md`` — the hard routing prompt appended to the agent.

The Skill mechanism alone is a soft, model-decided behaviour: an EDA plugin can
put a button in front of the user, but it cannot force the model to load a
Skill.  The launcher can, because it owns the agent command line: the routing
text below is injected with ``--append-system-prompt-file`` and the plugin is
mounted with ``--plugin-dir``.  That is the whole point of B1.

The five rules in :data:`REQUIRED_RULE_MARKERS` are normative and are asserted
by the tests.  Keep the wording stable when editing this file.
"""

from __future__ import annotations

from typing import Any

from . import REAL_EDA

#: Substrings that MUST appear in every generated routing.md.  Each tuple is
#: (rule id, marker).  Tests assert all of them; docs refer to the same ids.
REQUIRED_RULE_MARKERS = (
    ("rule-1-load-skill", "必须先加载 design-hardware Skill，不得跳过"),
    ("rule-2-read-only", "只读任务：不得修改/保存/导出 EDA 工程，不得调用任何写接口"),
    ("rule-3-tools", "未知/缺测必须如实报告，不得用默认值或猜测补全"),
    ("rule-4-verdicts", "离线检查 / 真实 EDA / 硬件实测"),
    ("rule-5-final-report", "读了哪些资料、跑了哪些工具、结果、未知项、未运行项"),
)

#: The only tools the agent may rely on for this PoC.
OFFLINE_TOOL_NAMES = (
    "offline_audit_capabilities",
    "offline_electrical_review",
    "offline_return_path_audit",
    "offline_delivery_inspect",
    "offline_delivery_audit",
)


def _context_lines(request: dict) -> list[str]:
    context = request.get("context") or {}
    project = context.get("project") or {}
    document = context.get("document") or {}
    page = context.get("page") or {}
    lines = [
        f"- 工程（只读副本标识）：{project.get('name', 'unknown')}"
        + (f" @ {project['revision']}" if project.get("revision") else ""),
        f"- 文档类型：{document.get('kind', 'unknown')}"
        + (f" / id={document['id']}" if document.get("id") else ""),
    ]
    if page.get("name"):
        lines.append(f"- 图页：{page['name']}")
    selection = context.get("selection") or []
    if selection:
        rendered = []
        for item in selection[:20]:
            label = item.get("designator") or item.get("id") or item.get("kind", "?")
            rendered.append(f"{item.get('kind', '?')}:{label}")
        suffix = "" if len(selection) <= 20 else f"（共 {len(selection)} 项，仅列前 20）"
        lines.append(f"- 用户选中对象：{', '.join(rendered)}{suffix}")
    snapshot = context.get("snapshot_sha256")
    lines.append(f"- 快照 SHA-256：{snapshot if snapshot else '未知（见 missing_fields）'}")
    missing = context.get("missing_fields") or []
    if missing:
        lines.append(f"- 已声明缺测字段（不要猜测）：{', '.join(missing)}")
    return lines


def build_routing_text(request: dict) -> str:
    """Return the full routing prompt for one task.

    The text is deliberately explicit and repetitive: this prompt is the hard
    mechanism, not documentation for a human.
    """

    goal = request.get("goal") or {}
    limits = request.get("limits") or {}
    timeout_s = limits.get("timeout_s", 180)
    lines = [
        "# 智构受控任务路由（由 task_launcher 注入，优先级高于模型自行判断）",
        "",
        "本任务由受控启动器启动；**必须先加载 design-hardware Skill，不得跳过。**",
        "Skill 已通过 `--plugin-dir` 挂载到本任务，不要假设客户全局安装过该 Skill，",
        "不要因为模型认为“不需要”而不加载。",
        "",
        "## 1. 只读边界（硬约束）",
        "",
        "只读任务：不得修改/保存/导出 EDA 工程，不得调用任何写接口。",
        "本任务没有写权限：不要运行写命令、不要尝试绕过权限模式、不要导出工程文件。",
        "任何需要写工程才能回答的问题，只报告需要什么写操作以及为什么，不实际执行。",
        "",
        "## 2. 可用工具面",
        "",
        "可用工具仅限：`offline_audit_capabilities`、`offline_electrical_review`、",
        "`offline_return_path_audit`、`offline_delivery_inspect`、",
        "`offline_delivery_audit`（MCP server `zhigou-offline-audit`），以及只读的",
        "Read/Glob/Grep 与 Skill 加载。",
        "未知/缺测必须如实报告，不得用默认值或猜测补全；工具返回 `pass_with_scope`",
        "只覆盖其声明的输入与规则，不是整板或硬件通过。",
        "",
        "## 3. 结论分层",
        "",
        "结论必须区分：离线检查 / 真实 EDA / 硬件实测；`pass_with_scope` 不是整板通过。",
        f"本任务的真实 EDA 状态是 `{REAL_EDA}`，eda_calls=0，project_writes=0，",
        "不允许把离线检查写成“已在 EDA 中验证”，也不允许声称完成了硬件实测。",
        "",
        "## 4. 任务结束时的必答清单",
        "",
        "任务结束时输出：读了哪些资料、跑了哪些工具、结果、未知项、未运行项。",
        "其中“结果”必须按上面的结论分层书写；“未运行项”必须显式列出，不能省略。",
        "",
        "## 5. 本次任务上下文（只读）",
        "",
        *_context_lines(request),
        "",
        "## 6. 用户目标",
        "",
        str(goal.get("user_prompt", "")).strip() or "（未提供）",
        "",
        "## 7. 执行限制",
        "",
        f"- 意图类别：{goal.get('intent', 'unknown')}",
        f"- 超时：{timeout_s} 秒；超时后启动器会终止进程树，不产生部分写入结论。",
        "- 不要访问网络，不要启动 EDA/daemon/connector，不要修改仓库或客户工程。",
        "- 输出使用中文，先给结论分层，再给证据与未运行项。",
        "",
    ]
    return "\n".join(lines)


def routing_markers() -> list[tuple[str, str]]:
    """Expose the normative markers (used by the acceptance matrix/tests)."""

    return list(REQUIRED_RULE_MARKERS)


def routing_summary(request: dict) -> dict[str, Any]:
    """Machine-readable summary of what was injected, stored with the task."""

    return {
        "rules": [rule_id for rule_id, _ in REQUIRED_RULE_MARKERS],
        "tools": list(OFFLINE_TOOL_NAMES),
        "mode": request.get("mode"),
        "real_eda": REAL_EDA,
    }
