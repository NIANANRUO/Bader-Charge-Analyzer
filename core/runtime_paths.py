import os
import sys
from pathlib import Path


APP_DIR_NAME = "Bader Charge Analyzer"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_base_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(*parts: str) -> Path:
    return app_base_dir().joinpath(*parts)


def user_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def default_workspace_root() -> Path:
    if is_frozen():
        return user_data_dir() / "workspaces"
    return Path("workspaces")


def bundled_bader_candidates():
    base = app_base_dir()
    return [
        base / "bader.exe",
        base / "bader",
        base / "bader_engine" / "bader.exe",
        base / "bader_engine" / "bader",
    ]
