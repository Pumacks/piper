#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from piper.better_ui import BetterUiApplication  # noqa: E402


class FakeProfile:
    def __init__(self, dirty=False):
        self.dirty = dirty


class FakeDevice:
    def __init__(self, profiles, active_profile=None):
        self.profiles = profiles
        self.active_profile = active_profile
        self.connected = None
        self.disconnected = None

    def connect(self, signal, callback):
        self.connected = (signal, callback)
        return 42

    def disconnect(self, handler):
        self.disconnected = handler


class FakeApplication:
    def __init__(self, device=None):
        self._selected_device = device
        self._selected_profile = None
        self._profile_signal_device = None
        self._profile_signal_handler = None
        self._draft = None
        self.apply_sensitive = None
        self.shown_device = None

    def _on_active_profile_changed(self, device, profile):
        BetterUiApplication._on_active_profile_changed(self, device, profile)

    @staticmethod
    def _make_draft(profile):
        return {"profile": profile}

    def _set_apply_sensitive(self, sensitive):
        self.apply_sensitive = sensitive

    def _show_device(self, device):
        self.shown_device = device


class BetterUiProfileTest(unittest.TestCase):
    def test_current_profile_uses_device_active_profile(self):
        first = FakeProfile()
        active = FakeProfile()
        device = FakeDevice([first, active], active)

        self.assertIs(BetterUiApplication._current_profile(device), active)

    def test_current_profile_falls_back_to_first_slot(self):
        first = FakeProfile()
        device = FakeDevice([first], None)

        self.assertIs(BetterUiApplication._current_profile(device), first)

    def test_active_profile_change_opens_that_profile(self):
        old = FakeProfile()
        active = FakeProfile(dirty=True)
        device = FakeDevice([old, active], active)
        app = FakeApplication(device)

        BetterUiApplication._on_active_profile_changed(app, device, active)

        self.assertIs(app._selected_profile, active)
        self.assertEqual(app._draft, {"profile": active})
        self.assertTrue(app.apply_sensitive)
        self.assertIs(app.shown_device, device)

    def test_active_profile_watch_moves_to_new_device(self):
        first = FakeDevice([FakeProfile()])
        second = FakeDevice([FakeProfile()])
        app = FakeApplication()

        BetterUiApplication._watch_active_profile(app, first)
        BetterUiApplication._watch_active_profile(app, second)

        self.assertEqual(first.connected[0], "active-profile-changed")
        self.assertEqual(first.disconnected, 42)
        self.assertEqual(second.connected[0], "active-profile-changed")
        self.assertIs(app._profile_signal_device, second)
        self.assertEqual(app._profile_signal_handler, 42)


if __name__ == "__main__":
    unittest.main()
