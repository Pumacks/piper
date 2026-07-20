# SPDX-License-Identifier: GPL-2.0-or-later

"""Persistent local names for onboard profiles."""

import json
from pathlib import Path
from typing import Optional

from gi.repository import GLib


class ProfileNameStore:
    """Store profile aliases for devices that cannot persist names in firmware."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path or (
            Path(GLib.get_user_config_dir()) / "piper" / "profile_names.json"
        )

    @staticmethod
    def _key(device, profile) -> str:
        device_name = getattr(device, "name", "unknown-device")
        return f"{device_name}:{profile.index}"

    def get(self, device, profile) -> Optional[str]:
        value = self._load().get(self._key(device, profile))
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def set(self, device, profile, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Profile name cannot be empty")

        aliases = self._load()
        aliases[self._key(device, profile)] = name
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as aliases_file:
            json.dump(aliases, aliases_file, indent=2, sort_keys=True)

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as aliases_file:
                aliases = json.load(aliases_file)
        except (OSError, json.JSONDecodeError):
            return {}
        return aliases if isinstance(aliases, dict) else {}
