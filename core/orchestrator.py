"""Orchestrator — round-robin, free, and parallel runners for multi-agent execution."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import MultiModalMessage, TextMessage
from autogen_core import Image as AGImage

try:
    from autogen_agentchat.messages import ToolCallRequestEvent, ToolCallExecutionEvent
except ImportError:
    ToolCallRequestEvent = None  # type: ignore
    ToolCallExecutionEvent = None  # type: ignore

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None

from config import MAX_GUARD_RETRIES
from core.enums import ChatStyle, PermissionMode
from core.schemas import AgentStageResult, CommandResult, StageState, TestStatus
from core.agent_factory import create_agents_for_team
from core.context import (
    _clip_output,
    _is_tool_event_chunk,
    _split_tool_events,
    compact_history,
    history_for_model_context,
)
from core.contract import create_contract, get_contract_path
from core.handoff import generate_handoff
from core.guard import enhanced_guard_check
from core.permission import check_file_write_conflict
from skills.registry import get_registry


# ── Utility ───────────────────────────────────────────

def _summarize_stage_outputs(stage_name: str, results: dict[str, dict]) -> str:
    """Summarize parallel stage results for the next stage context."""
    structured_payloads = {
        name: payload for name, payload in results.items()
        if payload.get("structured")
    }
    if not structured_payloads:
        return f"## Stage {stage_name}: no structured results"

    lines = [f"## Stage Output Summary: {stage_name}", "", "### Overall Status"]
    passed = sum(
        1 for p in structured_payloads.values()
        if (guard := p.get("guard")) and guard and guard.decision and getattr(guard.decision, "value", None) == "pass"
    )
    lines.extend([
        f"- Agent count: {len(structured_payloads)}",
        f"- Passed Guard: {passed}",
        "",
        "### Agent Results",
    ])

    next_context: list[str] = []
    for agent_name, payload in structured_payloads.items():
        result = payload["structured"]
        guard = payload.get("guard")
        lines.append(f"#### {agent_name}")
        lines.append(f"- Status: {result.status.value}")
        if guard:
            lines.append(f"- Guard: {guard.decision.value} / {guard.score}")
        if result.files_changed:
            lines.append("- Files changed: " + ", ".join(result.files_changed))
        if result.tests:
            lines.append("- Tests: " + "; ".join(
                f"{t.command or '(unnamed)'} => {t.result.value}" for t in result.tests
            ))
        lines.append("- Handoff summary: " + (result.handoff_summary or result.summary or "(none)"))
        if result.handoff_summary or result.summary:
            next_context.append(f"{agent_name}: {result.handoff_summary or result.summary}")

    if next_context:
        lines.append("")
        lines.append("### Context for next stage")
        lines.extend(f"- {item}" for item in next_context)

    return _clip_output("\n".join(lines), 7000)


# ── Task Building ─────────────────────────────────────

def _build_task_payload(history: list, agent_display: str, user_name: str) -> Any:
    """Build a text or multimodal task payload for an agent."""
    lines = ["## Multi-role Conversation Log\n"]
    for h in history:
        src = h.get("source", "?")
        lines.append(f"[{src}]: {h['content']}")
        lines.append("")
    lines.append("---")
    lines.append(f"Now reply as **{agent_display}**.")
    lines.append("")
    lines.append("***CRITICAL RULES (these override everything else):***")
    lines.append("1. **Search budget**: You may make AT MOST 3 web_search calls total. Be efficient.")
    lines.append("2. **When you have enough information, STOP searching and START producing.**")
    lines.append("3. Your reply MUST contain the actual deliverable (text/file/content), not just a summary of what you plan to do.")
    lines.append("4. If you need to save content, use the appropriate tool (write_file, academic_section_save, etc.).")
    lines.append("5. After calling a tool that produces output, show the result in your reply.")
    task = "\n".join(lines)

    # Check for image attachments
    images = []

    if PILImage:
        from config import DATA_DIR
        for h in history:
            for att in h.get("attachments", []) or []:
                if att.get("kind") != "image":
                    continue
                try:
                    from pathlib import Path
                    img_path = (DATA_DIR / att["path"]).resolve()
                    # Defend against path traversal: ensure resolved path is within DATA_DIR
                    if DATA_DIR.resolve() not in img_path.parents and img_path != DATA_DIR.resolve():
                        import logging
                        logging.warning("Skipping image outside DATA_DIR: %s", img_path)
                        continue
                    pil_img = PILImage.open(img_path).convert("RGB")
                    images.append(AGImage(pil_img))
                except Exception:
                    pass

    if images:
        return MultiModalMessage(source=user_name, content=[task, *images])
    return task
def _build_paper_task_payload(
    history: list,
    agent_display: str,
    user_name: str,
    project_id: str = "",
    paper_title: str = "",
) -> Any:
    """Build task payload specifically for paper writing with project context."""
    lines = ["## Multi-role Conversation Log\n"]
    for h in history:
        src = h.get("source", "?")
        lines.append(f"[{src}]: {h['content']}")
        lines.append("")
    lines.append("---")
    lines.append(f"Now reply as **{agent_display}**.")
    
    if project_id:
        lines.append(f"\n**IMPORTANT CONTEXT:**")
        lines.append(f"- Current paper project_id: `{project_id}`")
        lines.append(f"- Paper title: {paper_title}")
        lines.append(f"- Use this project_id in ALL academic tool calls.")
        lines.append(f"- You MUST produce actual output — use tools to write files, not just read.")
        lines.append(f"- After completing your task, VERIFY the file was saved by calling paper_assets_list.")
    
    lines.append("")
    lines.append("Output only what you want to say. Your response should include a summary of what you actually produced.")
    
    return "\n".join(lines)



def _build_parallel_task_payload(
    history: list,
    agent_display: str,
    user_name: str,
    stage_name: str,
    run_id: str = "",
) -> Any:
    """Build a task payload for parallel execution with contract/guard instructions."""
    compact = compact_history(history)
    contract_note = ""
    if run_id:
        contract_path = get_contract_path(run_id)
        if contract_path.exists():
            contract_note = f"""
You must follow the contract in generated/contracts/{run_id}_contract.md.
Do not modify forbidden files (app.py, config.py, etc., unless you are integration_agent).
"""
    compact.append({
        "source": "Galaxy",
        "content": f"""You are running parallel stage: {stage_name}
{contract_note}
Work like Codex / Claude Code:
1. Read project structure and key files before making changes.
2. After modifying Python files, run code_compile to self-check.
3. Do not paste full long files into your reply.
4. When writing files, always specify the path and rationale.

Your final output MUST begin with a JSON object:
{{
  "status": "done | needs_retry | blocked | failed",
  "role": "{agent_display}",
  "task_scope": "your responsibility scope",
  "summary": "summary of what you accomplished",
  "files_read": [],
  "files_changed": [],
  "commands_run": [],
  "tests": [],
  "risks": [],
  "handoff_summary": "brief handoff for next stage"
}}
You may add brief Markdown after the JSON.
If you did not modify files, files_changed must be empty.
If you did not run tests, set result = "not_run" in tests and explain why.
""",
    })
    return _build_task_payload(compact, agent_display, user_name)


# ── Streaming ─────────────────────────────────────────

async def _run_streaming(agent: AssistantAgent, task: str) -> Any:
    """Stream agent response, yielding incremental text chunks."""
    prev_len = 0
    first = True
    seen_tools: set[str] = set()
    try:
        async for msg in agent.run_stream(task=task):
            if ToolCallRequestEvent is not None and isinstance(msg, ToolCallRequestEvent):
                calls = getattr(msg, "content", []) or []
                names = [getattr(c, "name", "") for c in calls if getattr(c, "name", "")]
                marker = "request:" + ",".join(names)
                if names and marker not in seen_tools:
                    seen_tools.add(marker)
                    yield f"\n[TOOL] Calling: {', '.join(names)}\n"
            elif ToolCallExecutionEvent is not None and isinstance(msg, ToolCallExecutionEvent):
                results = getattr(msg, "content", []) or []
                names = []
                for r in results:
                    name = getattr(r, "name", "")
                    ok = not bool(getattr(r, "is_error", False))
                    if name:
                        names.append(f"{name}{' OK' if ok else ' ERROR'}")
                marker = "result:" + ",".join(names)
                if names and marker not in seen_tools:
                    seen_tools.add(marker)
                    yield f"[TOOL] Result: {', '.join(names)}\n"
            if isinstance(msg, TextMessage) and msg.source == agent.name:
                content = str(msg.content)
                if len(content) > prev_len:
                    chunk = content[prev_len:]
                    prev_len = len(content)
                    if first:
                        first = False
                        yield content
                    else:
                        yield chunk
    except Exception as e:
        yield f"\n[Error: {e}]"
    if prev_len == 0:
        yield "(no response)"


def _sync_stream(agent: AssistantAgent, task: str, max_tool_calls: int = 15):
    """Sync wrapper for streaming generator. Limits tool calls to prevent loops."""
    if asyncio.get_event_loop_policy().__class__.__name__ == "WindowsProactorEventLoopPolicy":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tool_call_count = 0
    try:
        gen = _run_streaming(agent, task)
        while True:
            try:
                chunk = loop.run_until_complete(gen.__anext__())
                # Count tool calls
                if isinstance(chunk, str) and chunk.startswith("[TOOL]"):
                    tool_call_count += 1
                    if tool_call_count > max_tool_calls:
                        yield "\n[Tool limit reached. Produce your final output NOW. Do not call more tools.]"
                        # Force agent to stop by sending a system message
                        break
                yield chunk
            except StopAsyncIteration:
                break
    finally:
        loop.close()


# ── Manual tool protocol ──────────────────────────────

def _manual_tool_specs(skill_ids: list[str]) -> str:
    registry = get_registry()
    if not hasattr(registry, "build_tool_specs"):
        return "(tool specs unavailable)"
    return registry.build_tool_specs(skill_ids)


def _extract_manual_tool_calls(text: str) -> list[dict]:
    import re as _re
    raw = (text or "").strip()
    if not raw:
        return []
    raw = _re.sub(r"^```(?:json)?\s*", "", raw, flags=_re.IGNORECASE | _re.MULTILINE)
    raw = _re.sub(r"\s*```$", "", raw, flags=_re.MULTILINE)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start:end + 1]
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict):
        calls = data.get("tool_calls") or data.get("tools") or data.get("calls")
        if isinstance(calls, list):
            return [c for c in calls if isinstance(c, dict)]
        if data.get("name") and isinstance(data.get("arguments"), dict):
            return [data]
    return []


def _execute_manual_tool_call(call: dict) -> dict:
    registry = get_registry()
    name = str(call.get("name", "")).strip()
    arguments = call.get("arguments") or {}
    skill = registry.get(name)
    if not skill:
        return {"name": name, "ok": False, "result": f"Unknown tool: {name}"}
    if not isinstance(arguments, dict):
        return {"name": name, "ok": False, "result": "arguments must be an object"}
    try:
        result = skill.fn(**arguments)
        return {"name": name, "ok": not str(result).startswith("Error:"),
                "result": _clip_output(str(result), 8000)}
    except Exception as e:
        return {"name": name, "ok": False, "result": f"Error: {e}"}


async def _run_manual_tool_protocol(agent_info: dict, task: Any):
    """DeepSeek manual tool protocol — text-based tool calling."""
    try:
        from openai import AsyncOpenAI
    except Exception as e:
        yield f"[Error: openai package unavailable: {e}]"
        return

    cfg = agent_info["model_cfg"]
    mid = agent_info.get("model_id", cfg.get("id", "")) if isinstance(agent_info.get("model_id"), str) else ""
    from data.model_store import get_model_api_key
    api_key = get_model_api_key(mid) if mid else cfg.get("api_key", "")
    client = AsyncOpenAI(api_key=api_key, base_url=cfg.get("base_url") or None)
    skill_ids = agent_info.get("role_config", {}).get("skills", [])

    system = f"""{agent_info.get("system_prompt", "")}

## DeepSeek Compatible Tool Protocol
You can use local tools, but do NOT use OpenAI function_call/tool_call.
When you need a tool, output ONLY a JSON object, no Markdown:
{{"tool_calls":[{{"name":"calculator","arguments":{{"expression":"2+2"}}}}]}}
I will execute the tool and send the results back to you.
If you still need tools after getting results, output JSON again.
If you have enough info, output your final answer.

Available tools:
{_manual_tool_specs(skill_ids)}
"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": str(task)},
    ]
    yielded_status = False
    previous_calls_key = ""
    repeated_calls = 0

    try:
        for _ in range(10):
            resp = await client.chat.completions.create(
                model=cfg.get("model", ""),
                messages=messages,
                temperature=0.2,
                max_tokens=8192,
                timeout=120,
            )
            content = resp.choices[0].message.content or ""
            calls = _extract_manual_tool_calls(content)
            if not calls:
                yield content or "(no response)"
                return

            if not yielded_status:
                yield "[TOOL] DeepSeek compatible tool mode activated...\n"
                yielded_status = True

            calls_key = json.dumps(calls, ensure_ascii=False, sort_keys=True)
            repeated_calls = repeated_calls + 1 if calls_key == previous_calls_key else 0
            previous_calls_key = calls_key

            # Limit tool calls per turn to prevent abuse / token exhaustion
            results = [_execute_manual_tool_call(call) for call in calls[:20]]
            if len(calls) > 20:
                results.append({"name": "_system", "ok": False,
                                "result": f"Too many tool calls ({len(calls)}), limited to 20"})
            names = ", ".join(r["name"] for r in results)
            yield f"[TOOL] Executed: {names}\n"

            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": "Tool results (JSON):\n" + json.dumps(results, ensure_ascii=False, indent=2)
                           + "\nContinue based on these results. If no more tools needed, output final answer.",
            })

            if repeated_calls >= 2 or all(not r.get("ok") for r in results):
                messages.append({
                    "role": "user",
                    "content": "Your repeated tool calls produced no actionable results. "
                               "Stop outputting tool_calls JSON and give a final answer based on existing results.",
                })

        final_resp = await client.chat.completions.create(
            model=cfg.get("model", ""),
            messages=messages + [{
                "role": "user",
                "content": "Max tool protocol iterations reached. Do NOT output tool_calls JSON. Give final answer.",
            }],
            temperature=0.2,
            max_tokens=8192,
            timeout=120,
        )
        final_content = final_resp.choices[0].message.content or ""
        yield final_content or "[Error: manual tool protocol exceeded max iterations]"
    except Exception as e:
        yield f"\n[Error: {e}]"
    finally:
        try:
            await client.close()
        except Exception:
            pass


def _sync_agent_stream(agent_info: dict, task: Any):
    """Sync wrapper that picks the right streaming method."""
    if not agent_info.get("manual_tools"):
        yield from _sync_stream(agent_info["agent"], task)
        return
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        gen = _run_manual_tool_protocol(agent_info, task)
        while True:
            try:
                chunk = loop.run_until_complete(gen.__anext__())
                yield chunk
            except StopAsyncIteration:
                break
            except (concurrent.futures.TimeoutError, asyncio.TimeoutError):
                yield f"\n[Error: agent timed out]"
                break
    finally:
        loop.close()


# ── Agent Runner ──────────────────────────────────────

def _run_agent_to_text(agent_info: dict, task: Any) -> str:
    """Run agent and collect output, logging tool calls to database."""
    chunks = []
    agent_name = str(agent_info.get("display_name", "unknown"))
    run_id = str(agent_info.get("run_id", ""))
    tool_calls_logged: list[tuple[str, str]] = []

    for chunk in _sync_agent_stream(agent_info, task):
        chunks.append(chunk)
        # Log detected tool call markers from streaming output
        if isinstance(chunk, str) and chunk.startswith("[TOOL]"):
            tool_calls_logged.append(("stream_marker", chunk[:120]))

    # Persist tool call log entries
    if tool_calls_logged:
        try:
            from data.database import get_db
            conn = get_db()
            now = datetime.now().isoformat(timespec="seconds")
            for tool_name, args_preview in tool_calls_logged:
                conn.execute(
                    "INSERT INTO tool_logs (run_id, agent_name, tool_name, args_preview, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (run_id, agent_name, tool_name, args_preview, now),
                )
            conn.commit()
        except Exception:
            pass  # best-effort logging, never crash the orchestrator

    return "".join(chunks).strip()


def run_agent_with_guard(
    agent_info: dict,
    task: Any,
    original_task: str,
    stage_name: str,
    workspace_root: Any = None,
    forbidden_paths: list[str] | None = None,
) -> dict:
    """Run an agent and apply guard checks with retries."""
    from config import DATA_DIR

    if workspace_root is None:
        from pathlib import Path as _Path
        workspace_root = _Path(DATA_DIR)

    retry_count = 0
    raw = _run_agent_to_text(agent_info, task)
    clean, events = _split_tool_events(raw)

    import importlib
    structured_module = importlib.import_module("core.structured_output")
    structured = structured_module.parse_agent_stage_result(clean, agent_info["display_name"])
    guard = enhanced_guard_check(
        structured,
        workspace_root=workspace_root,
        run_id=agent_info.get("run_id", ""),
        forbidden_paths=forbidden_paths,
    )
    raw_outputs = [raw]

    while guard.decision.value == "retry" and retry_count < MAX_GUARD_RETRIES:
        retry_count += 1
        import json as _json_for_safe
        safe_name = _json_for_safe.dumps(agent_info["display_name"])
        retry_prompt = f"""Your previous stage result did not pass Galaxy Guard.

Original task: {original_task}
Current stage: {stage_name}
Your role: {safe_name}
Previous output: {_clip_output(clean, 6000)}

Guard decision: {guard.decision.value}
Guard score: {guard.score}
Guard warnings: {guard.warnings}
Guard blocking issues: {guard.blocking_issues}
Guard retry instruction: {guard.retry_instruction}

Fix ONLY the Guard issues, do not expand scope.
Your final output MUST begin with structured JSON:
{{
  "status": "done | needs_retry | blocked | failed",
  "role": {safe_name},
  "task_scope": "...",
  "summary": "...",
  "files_read": [],
  "files_changed": [],
  "commands_run": [],
  "tests": [],
  "risks": [],
  "handoff_summary": "..."
}}
If no tests were run, set result = "not_run" in tests and explain why.
If files were changed, files_changed must list the paths.
"""
        retry_raw = _run_agent_to_text(agent_info, retry_prompt)
        retry_clean, retry_events = _split_tool_events(retry_raw)
        raw_outputs.append(retry_raw)
        clean = retry_clean
        events.extend(retry_events)
        structured = structured_module.parse_agent_stage_result(
            clean, agent_info["display_name"]
        )
        guard = enhanced_guard_check(
            structured,
            workspace_root=workspace_root,
            run_id=agent_info.get("run_id", ""),
            forbidden_paths=forbidden_paths,
        )

    return {
        "content": clean,
        "events": events,
        "structured": structured,
        "guard": guard,
        "retry_count": retry_count,
        "raw_outputs": raw_outputs,
    }


# ── Orchestrator Entry Points ─────────────────────────

def run_round_robin_stream(
    agent_infos: list[dict],
    history: list[dict],
    user_name: str,
    max_turns: int,
) -> Any:
    """Generator: yield one agent's streaming response at a time.
    Yields: (agent_info, chunk_generator) tuples.
    The caller iterates over chunk_generator to stream each agent's reply.
    """
    remaining_turns = max_turns
    cur_history = list(history)
    role_names = [a["display_name"] for a in agent_infos]
    prior_turns = sum(1 for h in cur_history if h.get("source") in role_names)
    remaining_turns = max(0, max_turns - prior_turns)

    for _pass in range(1):
        for ainfo in agent_infos:
            if remaining_turns <= 0:
                break
            task_history = history_for_model_context(
                cur_history, ainfo.get("context_length", 128000)
            )
            task = _build_task_payload(task_history, ainfo["display_name"], user_name)
            yield (ainfo, task, cur_history)
            remaining_turns -= 1


def run_parallel_stages(
    team: dict,
    history: list[dict],
    user_name: str,
    max_turns: int,
    workspace_root: Any = None,
    run_id: str = "",
    on_stage_complete: Callable | None = None,
) -> list[dict]:
    """Run all parallel stages (blocking). Returns list of stage result dicts.

    Prefer run_parallel_stages_stream() for live UI rendering.
    """
    return list(run_parallel_stages_stream(
        team, history, user_name, max_turns,
        workspace_root=workspace_root, run_id=run_id,
        on_stage_complete=on_stage_complete,
    ))


def run_parallel_stages_stream(
    team: dict,
    history: list[dict],
    user_name: str,
    max_turns: int,
    workspace_root: Any = None,
    run_id: str = "",
    on_stage_complete: Callable | None = None,
):
    """Generator: run parallel stages, yielding (agent_info, payload, stage_name)
    tuples as each agent completes. Gives the UI streaming-like responsiveness.
    
    Yields: (agent_info_dict, payload_dict, stage_name_str)
    After all agents in a stage complete, yields (None, stage_summary_dict, stage_name).
    """
    from config import DATA_DIR
    if workspace_root is None:
        from pathlib import Path as _Path
        workspace_root = _Path(DATA_DIR)

    agent_infos = create_agents_for_team(team, run_id=run_id)
    agents_by_name = {a["display_name"]: a for a in agent_infos}
    stages = _get_parallel_stages(team)
    handoff_history = compact_history(history)

    # Generate contract
    if run_id:
        create_contract(run_id, str(history[-1]["content"]) if history else "", team)

    remaining_turns = max_turns
    stage_results_list = []

    for stage in stages:
        if remaining_turns <= 0:
            break

        batch_agents = [
            agents_by_name[name]
            for name in stage.get("roles", [])
            if name in agents_by_name
        ][:remaining_turns]

        if not batch_agents:
            continue

        stage_name = stage.get("name", "Parallel Stage")
        tasks = {
            a["display_name"]: _build_parallel_task_payload(
                handoff_history, a["display_name"], user_name, stage_name, run_id,
            )
            for a in batch_agents
        }

        parallel_results: dict[str, dict] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(batch_agents), 8)) as executor:
            future_map = {
                executor.submit(
                    run_agent_with_guard,
                    ainfo,
                    tasks[ainfo["display_name"]],
                    str(history[-1]["content"]) if history else "",
                    stage_name,
                    workspace_root=workspace_root,
                    forbidden_paths=["app.py", "config.py"]
                    if ainfo["display_name"] not in ("integration_agent", "integration")
                    else [],
                ): ainfo
                for ainfo in batch_agents
            }
            for future in concurrent.futures.as_completed(future_map):
                ainfo = future_map[future]
                agent_name = ainfo["display_name"]
                try:
                    payload = future.result(timeout=300)
                except (concurrent.futures.TimeoutError, Exception) as e:
                    if isinstance(e, concurrent.futures.TimeoutError):
                        clean = f"[Error: agent {agent_name} timed out after 300s]"
                    else:
                        clean = f"[Error: {e}]"
                    import importlib
                    sm = importlib.import_module("core.structured_output")
                    structured = sm.parse_agent_stage_result(clean, agent_name)
                    guard = enhanced_guard_check(structured, workspace_root=workspace_root)
                    payload = {
                        "content": clean, "events": [],
                        "structured": structured, "guard": guard,
                        "retry_count": 0,
                    }
                parallel_results[agent_name] = payload
                # 🔥 Yield immediately so the UI can render this agent NOW
                yield (ainfo, payload, stage_name)

        # Generate handoff
        if run_id:
            generate_handoff(run_id, stage_name, parallel_results)

        # Update handoff history for next stage
        stage_summary = _summarize_stage_outputs(stage_name, parallel_results)
        handoff_history.append({
            "source": f"{stage_name} Output Summary",
            "content": stage_summary,
            "avatar": "docs",
        })

        stage_data = {
            "stage_name": stage_name,
            "results": parallel_results,
        }
        stage_results_list.append(stage_data)

        if on_stage_complete:
            on_stage_complete(stage_name, parallel_results)

        # Yield stage completion marker so UI can update handoff context
        yield (None, stage_data, stage_name)

        remaining_turns -= len(batch_agents)

    # Attach final stage list for external consumers
    if stage_results_list:
        stage_results_list[-1]["_all_stages"] = stage_results_list


def _get_parallel_stages(team: dict) -> list[dict]:
    roles = [r.get("name", "") for r in team.get("roles", []) if r.get("name")]
    stages = team.get("parallel_stages") or []
    normalized = []
    for idx, stage in enumerate(stages):
        selected = [r for r in stage.get("roles", []) if r in roles]
        if selected:
            normalized.append({"name": stage.get("name") or f"Stage {idx + 1}", "roles": selected})
    return normalized or [{"name": "Stage 1", "roles": roles}]


def verify_agent_output(agent_name: str, expected_files: list[str], workspace_root=None) -> dict:
    """Verify that an agent actually produced the expected files.
    Returns {ok: bool, found: list[str], missing: list[str]}."""
    from pathlib import Path
    if workspace_root is None:
        from config import DATA_DIR
        workspace_root = DATA_DIR
    root = Path(workspace_root)
    found = []
    missing = []
    for pattern in expected_files:
        matches = list(root.glob(pattern))
        if matches:
            found.extend([str(m.relative_to(root)) for m in matches])
        else:
            missing.append(pattern)
    return {
        "ok": len(missing) == 0,
        "agent": agent_name,
        "found": found,
        "missing": missing,
    }


def run_paper_pipeline(
    team: dict,
    run_id: str,
    task: str,
    user_name: str = "boss",
    history: list = None,
) -> dict:
    """Run the full paper writing pipeline with verification.
    
    Stages: PM (plan) -> DevA+DevB (parallel write) -> Integration (merge+export) -> Tester (verify)
    Returns {ok: bool, project_id: str, outputs: dict, errors: list}.
    """
    import uuid
    from core.agent_factory import create_agents_for_team
    from core.context import compact_history
    
    if history is None:
        history = []
    
    agents = create_agents_for_team(team, run_id=run_id)
    amap = {a['display_name']: a for a in agents}
    errors = []
    outputs = {}
    
    # Stage 1: PM creates project and outline
    pm = amap.get('pm')
    project_id = ""
    if pm:
        pm_task = _build_task_payload(
            history + [{"source": user_name, "content": task + "\nStart by creating the paper project and outline.", "avatar": ""}],
            "pm", user_name
        )
        try:
            result = _run_agent_to_text(pm, pm_task)
            outputs['pm'] = result
            # Extract project_id from PM output (prefer explicit output over filesystem side-channel).
            # PM should call tool_academic_project_create which returns
            # {"project_id": "xxx", ...} — try to extract that from the output text.
            import re as _re
            pid_match = _re.search(
                r'"project_id"\s*:\s*"([a-zA-Z0-9_-]+)"',
                result
            )
            if pid_match:
                project_id = pid_match.group(1)
            else:
                # Fallback: filesystem scan (last resort, may be wrong under concurrency)
                from config import DATA_DIR as _ws_data_dir
                ws = str(_ws_data_dir)
                acad_dir = Path(ws) / 'generated' / 'academic'
                if acad_dir.exists():
                    dirs = sorted([d for d in acad_dir.iterdir() if d.is_dir()],
                                 key=lambda d: d.stat().st_mtime, reverse=True)
                    if dirs:
                        project_id = dirs[0].name
            history.append({"source": "pm", "content": result, "avatar": ""})
        except Exception as e:
            errors.append(f"PM failed: {e}")
    
    if not project_id:
        errors.append("No project_id found after PM stage")
        return {"ok": False, "project_id": "", "outputs": outputs, "errors": errors}
    
    outputs['project_id'] = project_id
    
    # Stage 2: Parallel writing (DevA and DevB)
    dev_stages = [
        ("api_dev_a", "Introduction and Geography", (
            "Write the following sections for paper project {pid}:\n"
            "1. Chapter 1: Introduction (research background, significance, methodology)\n"
            "2. Chapter 2: Geographical Environment Analysis\n"
            "Use web_search for research, academic_section_save to save EACH section.\n"
            "Minimum 500 words per section. Add references with academic_reference_add."
        )),
        ("api_dev_b", "Resources and Economy", (
            "Write the following sections for paper project {pid}:\n"
            "1. Chapter 3: Tourism Resources Analysis (natural + cultural resources)\n"
            "2. Chapter 4: Tourism Economic Impact Analysis\n"
            "Use web_search, academic_table_generate for data tables, chart_bar for charts.\n"
            "Minimum 500 words per section. Add references with academic_reference_add."
        )),
    ]
    
    # Run in parallel with ThreadPoolExecutor
    import concurrent.futures
    
    def run_writer(agent_name, section_title, task_template):
        agent = amap.get(agent_name)
        if not agent:
            return {"agent": agent_name, "result": "Agent not found", "verified": False}
        
        actual_task = task_template.replace('{pid}', project_id)
        payload = _build_paper_task_payload(
            compact_history(history + [{"source": user_name, "content": actual_task, "avatar": ""}]),
            agent_name, user_name,
            project_id=project_id
        )
        raw = _run_agent_to_text(agent, payload)
        
        # Verify output
        v = verify_agent_output(agent_name, [
            f'generated/academic/{project_id}/sections/*.md',
        ])
        return {"agent": agent_name, "result": raw, "verified": v['ok'], "verification": v}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        for name, title, tmpl in dev_stages:
            futures.append(executor.submit(run_writer, name, title, tmpl))
        
        for f in concurrent.futures.as_completed(futures, timeout=600):
            try:
                r = f.result(timeout=300)
                outputs[r['agent']] = r
                if not r.get('verified'):
                    errors.append(f"{r['agent']}: output verification failed - {r.get('verification',{})}")
                history.append({"source": r['agent'], "content": r['result'], "avatar": ""})
            except concurrent.futures.TimeoutError:
                errors.append("Parallel writer timed out")
    
    # Stage 3: Integration — merge and export
    integ = amap.get('integration_agent')
    if integ:
        integ_task = f"""Merge all sections and export the paper.
Project ID: {project_id}
Steps:
1. paper_assets_list to check all files
2. academic_markdown_save to create complete paper
3. export_markdown_pdf to generate PDF
4. export_docx to generate DOCX
5. text_stats to count total words
"""
        payload = _build_paper_task_payload(
            compact_history(history + [{"source": user_name, "content": integ_task, "avatar": ""}]),
            "integration_agent", user_name,
            project_id=project_id
        )
        result = _run_agent_to_text(integ, payload)
        outputs['integration_agent'] = result
        
        v = verify_agent_output('integration_agent', [
            f'generated/exports/*.pdf',
            f'generated/academic/{project_id}/paper.md',
        ])
        if not v['ok']:
            errors.append(f"Integration: output verification failed - {v}")
        history.append({"source": 'integration_agent', "content": result, "avatar": ""})
    
    # Stage 4: Tester verification
    tester = amap.get('tester')
    if tester:
        test_task = f"""Verify the paper quality.
Project ID: {project_id}
Steps:
1. paper_assets_list
2. citation_check
3. text_stats for word count
Report: total words, sections count, references count, any issues found.
"""
        payload = _build_paper_task_payload(
            compact_history(history + [{"source": user_name, "content": test_task, "avatar": ""}]),
            "tester", user_name,
            project_id=project_id
        )
        result = _run_agent_to_text(tester, payload)
        outputs['tester'] = result
    
    return {
        "ok": len(errors) == 0,
        "project_id": project_id,
        "outputs": outputs,
        "errors": errors,
    }


def direct_paper_export(project_id: str, workspace_root=None) -> dict:
    """Directly merge and export a paper without going through an agent.
    Returns {"pdf": path, "docx": path, "paper_md": path, "word_count": int}."""
    import subprocess, sys
    
    if workspace_root is None:
        from config import DATA_DIR
        workspace_root = str(DATA_DIR)
    
    ws = Path(workspace_root)
    
    # 1. Auto-merge
    from core.merge import auto_merge_paper
    paper_path, merge_msg = auto_merge_paper(project_id, ws)
    if not paper_path:
        return {"error": merge_msg}
    
    # 2. Read merged paper
    paper_text = paper_path.read_text(encoding='utf-8', errors='replace')
    cjk_count = len(re.findall(r'[\u4e00-\u9fff]', paper_text))
    
    # 3. Export PDF using weasyprint
    from skills.builtin.export import tool_export_markdown_pdf as export_markdown_pdf
    pdf_result = export_markdown_pdf(str(paper_path))
    
    # 4. Export DOCX
    from skills.builtin.export import tool_export_docx as export_docx
    docx_result = export_docx(str(paper_path))
    
    return {
        "paper_md": str(paper_path),
        "pdf": pdf_result,
        "docx": docx_result,
        "word_count": cjk_count,
        "merge_msg": merge_msg,
    }

