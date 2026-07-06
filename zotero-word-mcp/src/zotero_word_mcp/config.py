from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional


APP_NAME = "zotero-word-mcp"


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def default_log_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or Path.home())
    return ensure_parent(base / APP_NAME / "zotero_word_bridge.log")


def _iter_existing(paths: Iterable[Path]) -> Iterable[Path]:
    seen = set()
    for path in paths:
        norm = str(path).lower()
        if norm in seen:
            continue
        seen.add(norm)
        if path.exists():
            yield path


def _zotero_prefs_path() -> Optional[Path]:
    candidate = Path.home() / "AppData" / "Roaming" / "Zotero" / "Zotero"
    if not candidate.exists():
        return None
    profiles_ini = candidate / "profiles.ini"
    if not profiles_ini.exists():
        return None
    text = profiles_ini.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"^Path=(.+)$", text, flags=re.M)
    if not match:
        return None
    relative = match.group(1).strip().replace("/", "\\")
    prefs = candidate / relative / "prefs.js"
    return prefs if prefs.exists() else None


def discover_zotero_data_dir() -> Optional[Path]:
    env_value = os.getenv("ZOTERO_DATA_DIR")
    if env_value:
        path = Path(env_value)
        if path.exists():
            return path

    prefs_path = _zotero_prefs_path()
    if prefs_path:
        text = prefs_path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'user_pref\("extensions\.zotero\.dataDir",\s*"(.+?)"\);', text)
        if match:
            raw = match.group(1).encode("utf-8").decode("unicode_escape")
            path = Path(raw)
            if path.exists():
                return path

    candidates = [
        Path(r"D:\Zotero\ZoteroFile"),
        Path.home() / "Zotero",
    ]
    return next(iter(_iter_existing(candidates)), None)


def discover_zotero_sqlite() -> Path:
    env_value = os.getenv("ZOTERO_SQLITE_PATH")
    if env_value:
        path = Path(env_value)
        if path.exists():
            return path

    data_dir = discover_zotero_data_dir()
    if data_dir:
        sqlite_path = data_dir / "zotero.sqlite"
        if sqlite_path.exists():
            return sqlite_path

    raise FileNotFoundError(
        "未找到 zotero.sqlite。可通过环境变量 ZOTERO_SQLITE_PATH 或 ZOTERO_DATA_DIR 显式指定。"
    )


def discover_word_integration_dll() -> Path:
    env_value = os.getenv("ZOTERO_WORD_DLL")
    if env_value:
        path = Path(env_value)
        if path.exists():
            return path

    data_dir = discover_zotero_data_dir()
    candidates = [
        Path(r"D:\Zotero\integration\word-for-windows\libzoteroWinWordIntegration.dll"),
        (data_dir / "integration" / "word-for-windows" / "libzoteroWinWordIntegration.dll") if data_dir else None,
        Path.home() / "Zotero" / "integration" / "word-for-windows" / "libzoteroWinWordIntegration.dll",
    ]
    existing = list(_iter_existing([p for p in candidates if p is not None]))
    if existing:
        return existing[0]
    raise FileNotFoundError(
        "未找到 libzoteroWinWordIntegration.dll。可通过环境变量 ZOTERO_WORD_DLL 显式指定。"
    )
