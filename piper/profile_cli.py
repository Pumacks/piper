# SPDX-License-Identifier: GPL-2.0-or-later

"""Command-line profile switching for launchers such as Steam."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from gi.repository import GLib

from .profilenames import ProfileNameStore
from .ratbagd import (
    Ratbagd,
    RatbagdDBusTimeoutError,
    RatbagdIncompatibleError,
    RatbagdProfile,
    RatbagdUnavailableError,
    RatbagError,
)
from .virtualprofiles import (
    VirtualProfileError,
    VirtualProfileStore,
    apply_snapshot,
)


class ProfileCliError(Exception):
    """A user-facing profile selection or activation error."""


def _profile_name(device, profile, names: ProfileNameStore) -> str:
    return (
        names.get(device, profile)
        or profile.name
        or f"Profile {profile.index + 1}"
    )


def select_device(devices, selector: Optional[str] = None):
    if not devices:
        raise ProfileCliError("No supported mouse was found")
    if selector:
        needle = selector.casefold()
        matches = [
            device
            for device in devices
            if any(
                needle in str(value).casefold()
                for value in (device.name, device.model, device.id)
            )
        ]
        if not matches:
            raise ProfileCliError(f"No device matches {selector!r}")
        if len(matches) > 1:
            raise ProfileCliError(f"More than one device matches {selector!r}")
        return matches[0]
    if len(devices) > 1:
        choices = ", ".join(f"{device.name} ({device.model})" for device in devices)
        raise ProfileCliError(
            f"More than one mouse is available: {choices}. Use --device to choose one"
        )
    return devices[0]


def _matching_onboard_profiles(device, selector: str, names: ProfileNameStore):
    if selector.isdecimal():
        index = int(selector) - 1
        return [profile for profile in device.profiles if profile.index == index]
    needle = selector.casefold()
    return [
        profile
        for profile in device.profiles
        if _profile_name(device, profile, names).casefold() == needle
    ]


def _matching_virtual_profiles(device, selector: str, store: VirtualProfileStore):
    needle = selector.casefold()
    return [
        profile
        for profile in store.list_for_model(device.model)
        if isinstance(profile.get("name"), str)
        and profile["name"].casefold() == needle
    ]


def activate_profile(
    device,
    selector: str,
    names: ProfileNameStore,
    virtual_profiles: VirtualProfileStore,
    *,
    virtual_only: bool = False,
    slot: Optional[int] = None,
) -> str:
    onboard = [] if virtual_only else _matching_onboard_profiles(
        device, selector, names
    )
    virtual = _matching_virtual_profiles(device, selector, virtual_profiles)
    if len(onboard) > 1 or len(virtual) > 1:
        raise ProfileCliError(
            f"Profile {selector!r} is ambiguous; rename it or use --virtual"
        )

    if onboard:
        profile = onboard[0]
        changed = False
        if profile.disabled:
            if RatbagdProfile.CAP_DISABLE not in profile.capabilities:
                raise ProfileCliError(f"Profile {selector!r} cannot be enabled")
            profile.disabled = False
            changed = True
        if not profile.is_active:
            profile.set_active()
            changed = True
        if changed or profile.dirty:
            device.commit()
        return f"Activated onboard profile {_profile_name(device, profile, names)!r}"

    if not virtual:
        raise ProfileCliError(f"Profile {selector!r} was not found")
    if slot is None:
        target = device.active_profile or device.profiles[0]
    else:
        if not 1 <= slot <= len(device.profiles):
            raise ProfileCliError(
                f"Slot must be between 1 and {len(device.profiles)}"
            )
        target = device.profiles[slot - 1]
    virtual_profile = virtual[0]
    try:
        apply_snapshot(virtual_profile["settings"], target)
        names.set(device, target, virtual_profile["name"])
        if not target.is_active:
            target.set_active()
        device.commit()
    except (
        GLib.Error,
        KeyError,
        OSError,
        RatbagdDBusTimeoutError,
        RatbagError,
        ValueError,
        VirtualProfileError,
    ) as error:
        raise ProfileCliError(
            f"Could not load virtual profile {selector!r}: {error}"
        ) from error
    return (
        f"Loaded virtual profile {virtual_profile['name']!r} into slot "
        f"{target.index + 1}"
    )


def list_profiles(device, names, virtual_profiles) -> str:
    lines = [f"Device: {device.name} ({device.model})", "Onboard profiles:"]
    for profile in device.profiles:
        marker = "*" if profile.is_active else " "
        lines.append(
            f"  {marker} {profile.index + 1}: {_profile_name(device, profile, names)}"
        )
    lines.append("Virtual profiles:")
    virtual = virtual_profiles.list_for_model(device.model)
    if virtual:
        lines.extend(f"    {profile['name']}" for profile in virtual)
    else:
        lines.append("    (none)")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="piper-profile",
        description="Switch a Piper profile, optionally before launching a command.",
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--profile", help="Onboard slot number or profile name")
    action.add_argument("--list", action="store_true", help="List available profiles")
    parser.add_argument(
        "--virtual", action="store_true", help="Only match a virtual profile"
    )
    parser.add_argument("--slot", type=int, help="Onboard slot for a virtual profile")
    parser.add_argument("--device", help="Substring of the device name, model, or ID")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Do not launch the command when profile switching fails",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(ratbagd_api_version: int, argv=None) -> int:
    args = _parser().parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    config_dir = Path(GLib.get_user_config_dir()) / "piper"
    try:
        ratbag = Ratbagd(ratbagd_api_version)
        device = select_device(ratbag.devices, args.device)
        names = ProfileNameStore()
        virtual_profiles = VirtualProfileStore(config_dir / "virtual_profiles.json")
        if args.list:
            print(list_profiles(device, names, virtual_profiles))
        else:
            message = activate_profile(
                device,
                args.profile,
                names,
                virtual_profiles,
                virtual_only=args.virtual,
                slot=args.slot,
            )
            print(message, file=sys.stderr)
    except (
        ProfileCliError,
        RatbagdIncompatibleError,
        RatbagdDBusTimeoutError,
        RatbagdUnavailableError,
        RatbagError,
        VirtualProfileError,
        GLib.Error,
    ) as error:
        print(f"piper-profile: {error}", file=sys.stderr)
        if args.strict or not command:
            return 1

    if command:
        try:
            os.execvp(command[0], command)
        except OSError as error:
            print(
                f"piper-profile: could not launch {command[0]!r}: {error}",
                file=sys.stderr,
            )
            return 1
    return 0
