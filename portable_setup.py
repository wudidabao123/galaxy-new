"""First-run configuration for a Galaxy New portable package."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent
os.environ.setdefault("GALAXY_PORTABLE", "1")
os.environ.setdefault("GALAXY_DATA_DIR", str(ROOT / "workspace"))


def _init_runtime() -> None:
    from config import ensure_runtime_dirs
    from data.database import init_db

    ensure_runtime_dirs()
    init_db()


def _save_default_model(api_key: str, model_name: str, base_url: str) -> str:
    from data.model_store import save_model

    display = {
        "deepseek-chat": "DeepSeek V3",
        "deepseek-reasoner": "DeepSeek R1",
        "deepseek-v4-pro": "DeepSeek V4 Pro",
        "gpt-4o": "OpenAI GPT-4o",
        "gpt-4o-mini": "OpenAI GPT-4o mini",
    }.get(model_name, model_name)
    return save_model(
        "default",
        display,
        model_name,
        base_url,
        api_key,
        context_length=128000,
        capabilities={"vision": False, "function_calling": True, "streaming": True},
        is_default=True,
    )


def _seed_teams(default_model_id: str) -> int:
    from data.team_store import get_team, save_team
    from presets.teams import PARALLEL_PROJECT_SQUAD_V2, PRESET_TEAMS

    count = 0

    def bind_and_save(team: dict, category: str | None = None) -> None:
        nonlocal count
        tid = team.get("id") or team.get("name")
        if not tid or get_team(tid):
            return
        item = dict(team)
        item["id"] = tid
        if category and not item.get("category"):
            item["category"] = category
        item["chat_style"] = (item.get("chat_style") or item.get("mode") or "round").replace(
            "round_robin", "round"
        )
        for role in item.get("roles", []):
            role.setdefault("model_id", default_model_id)
            if not role.get("model_id"):
                role["model_id"] = default_model_id
            role.setdefault("skills", [])
            role.setdefault("advanced", {})
            role.setdefault("avatar", "")
        save_team(item)
        count += 1

    for category, teams in PRESET_TEAMS.items():
        for team in teams:
            bind_and_save(team, category)

    squad = dict(PARALLEL_PROJECT_SQUAD_V2)
    squad.setdefault("id", "parallel_project_squad_v2")
    bind_and_save(squad, squad.get("category") or "Parallel Work")
    return count


def configure(args: argparse.Namespace) -> None:
    _init_runtime()

    print()
    print("Galaxy New portable setup")
    print("=" * 32)
    print(f"App folder : {ROOT}")
    print(f"Workspace  : {ROOT / 'workspace'}")
    print()

    model_name = args.model or input("Model name [deepseek-chat]: ").strip() or "deepseek-chat"
    base_url = args.base_url or input("Base URL [https://api.deepseek.com]: ").strip() or "https://api.deepseek.com"
    api_key = args.api_key
    if api_key is None:
        api_key = getpass.getpass("API key (leave blank to configure later in UI): ").strip()

    model_id = ""
    if api_key:
        model_id = _save_default_model(api_key, model_name, base_url)
        print(f"Saved default model: {model_name} ({model_id})")
    else:
        print("Skipped model key. You can add it later in the Models tab.")
        model_id = "default"

    seeded = _seed_teams(model_id)
    print(f"Imported preset teams: {seeded}")

    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text(
            "GALAXY_PORTABLE=1\n"
            "GALAXY_DATA_DIR=workspace\n"
            "GALAXY_LOG_LEVEL=INFO\n",
            encoding="utf-8",
        )
        print("Created .env")

    print()
    print("Setup complete. Use start.bat for local access or start_public.bat for a public tunnel.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--model", default="")
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()
    configure(args)


if __name__ == "__main__":
    main()
