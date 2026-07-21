# SPDX-License-Identifier: GPL-2.0-or-later

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from .ratbagd import RatbagdButton, RatbagdLed, RatbagdMacro, RatbagdProfile


FORMAT_VERSION = 1


class VirtualProfileError(Exception):
    """Raised when a virtual profile cannot be loaded or applied."""


class VirtualProfileStore:
    """Persistent, local snapshots of onboard profile settings."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def list_for_model(self, model: str) -> List[dict]:
        return [p for p in self._load() if p.get("device_model") == model]

    def save(self, name: str, model: str, profile: RatbagdProfile) -> dict:
        profiles = self._load()
        virtual_profile = {
            "id": str(uuid.uuid4()),
            "name": name,
            "device_model": model,
            "settings": snapshot_profile(profile),
        }
        profiles.append(virtual_profile)
        self._write(profiles)
        return virtual_profile

    def delete(self, profile_id: str) -> None:
        profiles = [p for p in self._load() if p.get("id") != profile_id]
        self._write(profiles)

    def _load(self) -> List[dict]:
        if not self.path.exists():
            return []

        try:
            with self.path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (OSError, json.JSONDecodeError) as error:
            raise VirtualProfileError(
                "The virtual profile file could not be read"
            ) from error

        if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
            raise VirtualProfileError(
                "The virtual profile file uses an unsupported format"
            )
        profiles = data.get("profiles")
        if not isinstance(profiles, list):
            raise VirtualProfileError("The virtual profile file is invalid")
        return profiles

    def _write(self, profiles: List[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": FORMAT_VERSION, "profiles": profiles}
        temporary_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                delete=False,
            ) as stream:
                temporary_path = stream.name
                json.dump(payload, stream, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary_path, self.path)
        except OSError as error:
            if temporary_path is not None:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass
            raise VirtualProfileError(
                "The virtual profile file could not be saved"
            ) from error


def snapshot_profile(profile: RatbagdProfile) -> dict:
    """Return the writable settings of a ratbagd profile as JSON-safe data."""
    resolutions = []
    for resolution in profile.resolutions:
        resolutions.append(
            {
                "resolution": list(resolution.resolution),
                "active": bool(resolution.is_active),
                "default": bool(resolution.is_default),
                "disabled": bool(resolution.is_disabled),
            }
        )

    buttons = []
    for button in profile.buttons:
        action_type = int(button.action_type)
        value = None
        if action_type == RatbagdButton.ActionType.BUTTON:
            value = int(button.mapping)
        elif action_type == RatbagdButton.ActionType.SPECIAL:
            value = int(button.special)
        elif action_type == RatbagdButton.ActionType.KEY:
            value = int(button.key)
        elif action_type == RatbagdButton.ActionType.MACRO:
            value = [list(event) for event in button.macro.keys]
        buttons.append({"action_type": action_type, "value": value})

    leds = []
    for led in profile.leds:
        leds.append(
            {
                "mode": int(led.mode),
                "color": [int(channel) for channel in led.color],
                "brightness": int(led.brightness),
                "effect_duration": int(led.effect_duration),
            }
        )

    return {
        "report_rate": int(profile.report_rate),
        "angle_snapping": int(profile.angle_snapping),
        "debounce": int(profile.debounce),
        "resolutions": resolutions,
        "buttons": buttons,
        "leds": leds,
    }


def apply_snapshot(settings: dict, profile: RatbagdProfile) -> None:
    """Copy a snapshot into a physical profile without committing the device."""
    _validate_layout(settings, profile)

    report_rate = settings["report_rate"]
    if profile.report_rates and report_rate in profile.report_rates:
        profile.report_rate = report_rate
    angle_snapping = settings["angle_snapping"]
    if profile.angle_snapping != -1 and angle_snapping != -1:
        profile.angle_snapping = angle_snapping
    debounce = settings["debounce"]
    if profile.debounces and debounce in profile.debounces:
        profile.debounce = debounce

    for saved, resolution in zip(settings["resolutions"], profile.resolutions):
        updated = tuple(saved["resolution"])
        if resolution.resolution != updated:
            resolution.resolution = updated

    # Select the default and active stages before disabling any others. Some
    # devices reject a transaction that temporarily disables either one.
    for saved, resolution in zip(settings["resolutions"], profile.resolutions):
        if saved["default"]:
            resolution.set_default()
        if saved["active"]:
            resolution.set_active()
    for saved, resolution in zip(settings["resolutions"], profile.resolutions):
        if resolution.CAP_DISABLE in resolution.capabilities:
            disabled = (
                saved["disabled"]
                and not saved["active"]
                and not saved["default"]
            )
            if resolution.is_disabled != disabled:
                resolution.set_disabled(disabled)

    for saved, button in zip(settings["buttons"], profile.buttons):
        action_type = saved["action_type"]
        value = saved["value"]
        if action_type == RatbagdButton.ActionType.NONE:
            button.disable()
        elif action_type == RatbagdButton.ActionType.BUTTON:
            button.mapping = value
        elif action_type == RatbagdButton.ActionType.SPECIAL:
            button.special = value
        elif action_type == RatbagdButton.ActionType.KEY:
            button.key = value
        elif action_type == RatbagdButton.ActionType.MACRO:
            button.macro = RatbagdMacro.from_ratbag(value)

    for saved, led in zip(settings["leds"], profile.leds):
        mode = saved["mode"]
        if mode in led.modes and led.mode != mode:
            led.mode = mode
        if mode == RatbagdLed.Mode.OFF:
            continue
        if led.brightness != saved["brightness"]:
            led.brightness = saved["brightness"]
        if mode in (RatbagdLed.Mode.ON, RatbagdLed.Mode.BREATHING):
            color = tuple(saved["color"])
            if tuple(led.color) != color:
                led.color = color
        if mode in (RatbagdLed.Mode.CYCLE, RatbagdLed.Mode.BREATHING):
            if led.effect_duration != saved["effect_duration"]:
                led.effect_duration = saved["effect_duration"]


def _validate_layout(settings: dict, profile: RatbagdProfile) -> None:
    required = {
        "report_rate",
        "angle_snapping",
        "debounce",
        "resolutions",
        "buttons",
        "leds",
    }
    if not isinstance(settings, dict) or not required.issubset(settings):
        raise VirtualProfileError("This virtual profile is incomplete")

    layouts = (
        ("resolution", settings["resolutions"], profile.resolutions),
        ("button", settings["buttons"], profile.buttons),
        ("LED", settings["leds"], profile.leds),
    )
    for label, saved, available in layouts:
        if not isinstance(saved, list) or len(saved) != len(available):
            raise VirtualProfileError(
                f"This virtual profile has an incompatible {label} layout"
            )

    scalar_settings = ("report_rate", "angle_snapping", "debounce")
    if any(type(settings[key]) is not int for key in scalar_settings):
        raise VirtualProfileError("This virtual profile contains invalid settings")
    if profile.report_rates and settings["report_rate"] not in profile.report_rates:
        raise VirtualProfileError(
            "This virtual profile contains an unsupported report rate"
        )
    if profile.debounces and settings["debounce"] not in profile.debounces:
        raise VirtualProfileError(
            "This virtual profile contains an unsupported debounce time"
        )

    for saved, resolution in zip(settings["resolutions"], profile.resolutions):
        if not isinstance(saved, dict):
            raise VirtualProfileError(
                "This virtual profile contains invalid resolutions"
            )
        required_resolution = {"resolution", "active", "default", "disabled"}
        if not required_resolution.issubset(saved):
            raise VirtualProfileError(
                "This virtual profile contains invalid resolutions"
            )
        value = saved["resolution"]
        if (
            not isinstance(value, list)
            or len(value) != len(resolution.resolution)
            or any(type(dpi) is not int for dpi in value)
            # Some devices report a valid current DPI that is omitted from
            # libratbag's sampled list of suggested values. The G502, for
            # example, can report 2050 while advertising 2000 and 2100.
            or any(
                dpi < resolution.resolutions[0]
                or dpi > resolution.resolutions[-1]
                for dpi in value
            )
        ):
            raise VirtualProfileError(
                "This virtual profile contains an unsupported resolution"
            )
        if any(
            not isinstance(saved[key], bool)
            for key in ("active", "default", "disabled")
        ):
            raise VirtualProfileError(
                "This virtual profile contains invalid resolutions"
            )
        if (
            saved["disabled"]
            and resolution.CAP_DISABLE not in resolution.capabilities
        ):
            raise VirtualProfileError(
                "This virtual profile disables an unsupported resolution"
            )

    valid_actions = {int(action) for action in RatbagdButton.ActionType}
    for saved, button in zip(settings["buttons"], profile.buttons):
        if (
            not isinstance(saved, dict)
            or "action_type" not in saved
            or "value" not in saved
        ):
            raise VirtualProfileError(
                "This virtual profile contains an invalid button action"
            )
        action_type = saved.get("action_type")
        if (
            type(action_type) is not int
            or action_type not in valid_actions
            or action_type not in button.action_types
        ):
            raise VirtualProfileError(
                "This virtual profile contains an unsupported button action"
            )
        value = saved["value"]
        if action_type == RatbagdButton.ActionType.NONE:
            valid_value = value is None
        elif action_type == RatbagdButton.ActionType.MACRO:
            valid_value = isinstance(value, list) and all(
                isinstance(event, list)
                and len(event) == 2
                and all(type(item) is int for item in event)
                for event in value
            )
        else:
            valid_value = type(value) is int
        if not valid_value:
            raise VirtualProfileError(
                "This virtual profile contains an invalid button action"
            )

    for saved, led in zip(settings["leds"], profile.leds):
        if not isinstance(saved, dict):
            raise VirtualProfileError(
                "This virtual profile contains invalid LED settings"
            )
        required_led = {"mode", "color", "brightness", "effect_duration"}
        if not required_led.issubset(saved):
            raise VirtualProfileError(
                "This virtual profile contains invalid LED settings"
            )
        color = saved["color"]
        if (
            saved["mode"] not in led.modes
            or not isinstance(color, list)
            or len(color) != 3
            or any(
                type(channel) is not int or not 0 <= channel <= 255
                for channel in color
            )
            or type(saved["brightness"]) is not int
            or not 0 <= saved["brightness"] <= 255
            or type(saved["effect_duration"]) is not int
            or not 0 <= saved["effect_duration"] <= 10000
        ):
            raise VirtualProfileError(
                "This virtual profile contains invalid LED settings"
            )
