#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from piper.profile_cli import (  # noqa: E402
    ProfileCliError,
    _parser,
    activate_profile,
    list_profiles,
    select_device,
)


class FakeProfile:
    def __init__(self, index, name=None, active=False):
        self.index = index
        self.name = name
        self.is_active = active
        self.dirty = False
        self.disabled = False
        self.capabilities = []
        self.report_rate = 0
        self.report_rates = []
        self.angle_snapping = -1
        self.debounce = 0
        self.debounces = []
        self.resolutions = []
        self.buttons = []
        self.leds = []
        self.activation_count = 0

    def set_active(self):
        self.is_active = True
        self.activation_count += 1


class FakeDevice:
    def __init__(self, name="Test Mouse", model="test:model"):
        self.name = name
        self.model = model
        self.id = "device-id"
        self.profiles = [FakeProfile(0, active=True), FakeProfile(1)]
        self.active_profile = self.profiles[0]
        self.commit_count = 0

    def commit(self):
        self.commit_count += 1


class FakeNames:
    def __init__(self, aliases=None):
        self.aliases = aliases or {}

    def get(self, _device, profile):
        return self.aliases.get(profile.index)

    def set(self, _device, profile, name):
        self.aliases[profile.index] = name


class FakeVirtualProfiles:
    def __init__(self, profiles=None):
        self.profiles = profiles or []

    def list_for_model(self, _model):
        return self.profiles


def virtual_profile(name):
    return {
        "name": name,
        "settings": {
            "report_rate": 0,
            "angle_snapping": -1,
            "debounce": 0,
            "resolutions": [],
            "buttons": [],
            "leds": [],
        },
    }


class ProfileCliTest(unittest.TestCase):
    def test_selects_onboard_profile_by_local_name(self):
        device = FakeDevice()
        names = FakeNames({1: "Gaming"})

        message = activate_profile(
            device, "Gaming", names, FakeVirtualProfiles()
        )

        self.assertEqual(device.profiles[1].activation_count, 1)
        self.assertEqual(device.commit_count, 1)
        self.assertEqual(message, "Activated onboard profile 'Gaming'")

    def test_loads_virtual_profile_into_active_slot(self):
        device = FakeDevice()
        names = FakeNames()

        message = activate_profile(
            device,
            "My Game",
            names,
            FakeVirtualProfiles([virtual_profile("My Game")]),
            virtual_only=True,
        )

        self.assertEqual(names.aliases[0], "My Game")
        self.assertEqual(device.commit_count, 1)
        self.assertEqual(message, "Loaded virtual profile 'My Game' into slot 1")

    def test_onboard_profile_wins_name_collision_by_default(self):
        device = FakeDevice()
        names = FakeNames({1: "Gaming"})
        virtual = FakeVirtualProfiles([virtual_profile("Gaming")])

        message = activate_profile(device, "Gaming", names, virtual)

        self.assertEqual(device.profiles[1].activation_count, 1)
        self.assertEqual(device.commit_count, 1)
        self.assertEqual(message, "Activated onboard profile 'Gaming'")

    def test_commits_active_profile_left_dirty_by_previous_switch(self):
        device = FakeDevice()
        device.profiles[0].dirty = True

        activate_profile(device, "1", FakeNames(), FakeVirtualProfiles())

        self.assertEqual(device.commit_count, 1)

    def test_multiple_devices_require_selector(self):
        devices = [FakeDevice("First"), FakeDevice("Second")]

        with self.assertRaisesRegex(ProfileCliError, "More than one mouse"):
            select_device(devices)
        self.assertIs(select_device(devices, "Second"), devices[1])

    def test_list_marks_active_profile_and_virtual_names(self):
        output = list_profiles(
            FakeDevice(),
            FakeNames({0: "Desktop"}),
            FakeVirtualProfiles([virtual_profile("My Game")]),
        )

        self.assertIn("* 1: Desktop", output)
        self.assertIn("My Game", output)

    def test_parser_keeps_steam_command_after_separator(self):
        args = _parser().parse_args(
            ["--profile", "Gaming", "--", "/path/to/game", "--fullscreen"]
        )

        self.assertEqual(args.command, ["--", "/path/to/game", "--fullscreen"])


if __name__ == "__main__":
    unittest.main()
