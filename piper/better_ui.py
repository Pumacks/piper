# SPDX-License-Identifier: GPL-2.0-or-later

"""GTK 4/libadwaita foundation for Piper's next-generation interface.

This module intentionally has no dependency on the existing GTK 3 page
widgets. GTK 3 and GTK 4 cannot share a process, so the device model is reused
first while individual configuration pages are ported incrementally.
"""

from gettext import gettext as _
from pathlib import Path
from typing import Dict, Optional

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Rsvg", "2.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Rsvg  # noqa

from .ratbagd import (
    Ratbagd,
    RatbagdButton,
    RatbagdDevice,
    RatbagdIncompatibleError,
    RatbagError,
    RatbagdProfile,
    RatbagdUnavailableError,
)
from .svg import get_svg
from .virtualprofiles import (
    VirtualProfileError,
    VirtualProfileStore,
    apply_snapshot,
)


class BetterUiApplication(Adw.Application):
    """An experimental GTK 4/libadwaita shell backed by ratbagd."""

    def __init__(self, ratbagd_api_version: int) -> None:
        super().__init__(
            application_id="org.freedesktop.Piper.BetterUi",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._required_ratbagd_version = ratbagd_api_version
        self._ratbag: Optional[Ratbagd] = None
        self._window: Optional[Adw.ApplicationWindow] = None
        self._toast_overlay: Optional[Adw.ToastOverlay] = None
        self._apply_button: Optional[Gtk.Button] = None
        self._selected_device: Optional[RatbagdDevice] = None
        self._selected_profile: Optional[RatbagdProfile] = None
        self._draft = {}
        self._virtual_profiles = VirtualProfileStore(
            Path(GLib.get_user_config_dir()) / "piper" / "virtual_profiles.json"
        )
        self._device_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self._device_rows: Dict[str, Gtk.ListBoxRow] = {}
        self._content_page = Adw.NavigationPage.new(
            self._status_page(
                _("Connect a supported mouse"),
                _("Piper Next will display its profiles here."),
            ),
            _("Piper Next"),
        )

    def do_activate(self) -> None:
        if self._window is None:
            self._window = self._build_window()
            self._connect_ratbagd()
        self._window.present()

    def _build_window(self) -> Adw.ApplicationWindow:
        window = Adw.ApplicationWindow(application=self)
        window.set_default_size(1160, 760)
        window.set_icon_name("org.freedesktop.Piper")

        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title="Piper Next"))
        self._apply_button = Gtk.Button(label=_("Apply"))
        self._apply_button.add_css_class("suggested-action")
        self._apply_button.set_sensitive(False)
        self._apply_button.connect("clicked", self._on_apply_clicked)
        header_bar.pack_end(self._apply_button)
        toolbar_view.add_top_bar(header_bar)

        sidebar = Gtk.ScrolledWindow()
        sidebar.set_child(self._device_list)
        self._device_list.connect("row-selected", self._on_device_selected)
        sidebar_page = Adw.NavigationPage.new(sidebar, _("Devices"))

        split_view = Adw.NavigationSplitView()
        split_view.set_sidebar(sidebar_page)
        split_view.set_content(self._content_page)
        split_view.set_min_sidebar_width(220)
        split_view.set_max_sidebar_width(320)
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(split_view)
        toolbar_view.set_content(self._toast_overlay)
        window.set_content(toolbar_view)
        return window

    def _connect_ratbagd(self) -> None:
        try:
            self._ratbag = Ratbagd(self._required_ratbagd_version)
        except RatbagdUnavailableError:
            self._show_error(
                _("Cannot connect to ratbagd"),
                _("Make sure ratbagd is running and your user can access it."),
            )
            return
        except RatbagdIncompatibleError as error:
            self._show_error(
                _("Incompatible ratbagd version"),
                _("Piper and libratbag need compatible D-Bus API versions."),
            )
            return

        self._ratbag.connect("device-added", self._on_devices_changed)
        self._ratbag.connect("device-removed", self._on_devices_changed)
        self._ratbag.connect("daemon-disappeared", self._on_daemon_disappeared)
        self._refresh_devices()

    def _refresh_devices(self) -> None:
        self._device_rows.clear()
        row = self._device_list.get_first_child()
        while row is not None:
            self._device_list.remove(row)
            row = self._device_list.get_first_child()

        if self._ratbag is None or not self._ratbag.devices:
            self._content_page.set_child(
                self._status_page(
                    _("No supported mouse found"),
                    _("Connect a device supported by libratbag."),
                )
            )
            return

        for device in self._ratbag.devices:
            row = self._make_device_row(device)
            self._device_rows[device.id] = row
            self._device_list.append(row)

        first_row = self._device_list.get_first_child()
        assert isinstance(first_row, Gtk.ListBoxRow)
        self._device_list.select_row(first_row)

    def _make_device_row(self, device: RatbagdDevice) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.device = device  # type: ignore[attr-defined]
        label = Gtk.Label(
            label=device.name,
            xalign=0,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12,
        )
        row.set_child(label)
        return row

    def _on_device_selected(
        self, _listbox: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]
    ) -> None:
        if row is None:
            return
        device = row.device  # type: ignore[attr-defined]
        self._selected_device = device
        self._selected_profile = device.active_profile or device.profiles[0]
        self._draft = self._make_draft(self._selected_profile)
        self._show_device(device)

    def _device_page(self, device: RatbagdDevice) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_margin_top(12)
        page.set_margin_bottom(12)
        page.set_margin_start(18)
        page.set_margin_end(18)

        stack = Gtk.Stack(
            vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE
        )
        switcher = Gtk.StackSwitcher(stack=stack, halign=Gtk.Align.CENTER)
        page.append(switcher)
        page.append(stack)

        profiles_page = Adw.PreferencesPage()
        profiles_page.set_title(_("Profiles"))
        profiles_page.set_icon_name("avatar-default-symbolic")

        details = Adw.PreferencesGroup(title=_("Device"))
        details.add(Adw.ActionRow(title=device.name, subtitle=device.model))
        profiles_page.add(details)

        profiles = Adw.PreferencesGroup(title=_("Onboard profiles"))
        selector = Adw.ComboRow(title=_("Editing profile"))
        selector.set_model(
            Gtk.StringList.new(
                [
                    profile.name or _("Profile {}").format(profile.index + 1)
                    for profile in device.profiles
                ]
            )
        )
        assert self._selected_profile is not None
        selector.set_selected(self._selected_profile.index)
        selector.connect("notify::selected", self._on_profile_selected, device)
        profiles.add(selector)

        if RatbagdProfile.CAP_WRITABLE_NAME in self._selected_profile.capabilities:
            name_row = Adw.EntryRow(title=_("Profile name"))
            name_row.set_text(self._draft["name"])
            name_row.connect("notify::text", self._on_profile_name_changed)
            profiles.add(name_row)

        for profile in device.profiles:
            name = profile.name or _("Profile {}").format(profile.index + 1)
            subtitle = _("Disabled") if profile.disabled else _("Available")
            if profile.is_active:
                subtitle = _("Active")
            row = Adw.ActionRow(title=name, subtitle=subtitle)
            activate_button = Gtk.Button(label=_("Activate"))
            activate_button.set_valign(Gtk.Align.CENTER)
            activate_button.set_sensitive(
                not profile.disabled and not profile.is_active
            )
            activate_button.connect(
                "clicked", self._on_activate_profile_clicked, device, profile
            )
            row.add_suffix(activate_button)
            profiles.add(row)
        profiles_page.add(profiles)
        profiles_page.add(self._virtual_profiles_group(device))
        stack.add_titled(profiles_page, "profiles", _("Profiles"))

        sensitivity_page = Adw.PreferencesPage()
        sensitivity_page.set_title(_("Sensitivity"))
        sensitivity_page.set_icon_name("preferences-system-symbolic")
        sensitivity_page.add(self._resolution_group())
        advanced = self._advanced_group()
        if advanced is not None:
            sensitivity_page.add(advanced)
        stack.add_titled(sensitivity_page, "sensitivity", _("Sensitivity"))

        buttons_page = self._buttons_page(device)
        stack.add_titled(buttons_page, "buttons", _("Buttons"))
        return page

    def _buttons_page(self, device: RatbagdDevice) -> Gtk.Box:
        assert self._selected_profile is not None
        page = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        page.set_homogeneous(True)
        page.set_margin_top(12)

        picture = self._mouse_picture(device)
        picture.set_hexpand(True)
        picture.set_vexpand(True)
        page.append(picture)

        controls = Gtk.Grid(
            column_spacing=12,
            row_spacing=10,
            margin_top=12,
            margin_bottom=12,
        )
        controls.set_hexpand(True)
        heading = Gtk.Label(label=_("Button assignments"), xalign=0)
        heading.add_css_class("title-3")
        controls.attach(heading, 0, 0, 2, 1)
        for row_index, button in enumerate(self._selected_profile.buttons, start=1):
            label = Gtk.Label(
                label=_("Button {}").format(button.index + 1), xalign=0
            )
            actions = self._button_actions(button)
            if actions:
                dropdown = Gtk.DropDown.new_from_strings(
                    [action[2] for action in actions]
                )
                dropdown.set_hexpand(True)
                dropdown.set_selected(self._selected_button_action(button, actions))
                dropdown.connect(
                    "notify::selected", self._on_button_action_changed, button, actions
                )
            else:
                dropdown = Gtk.Label(label=_("Not configurable"), xalign=0)
            controls.attach(label, 0, row_index, 1, 1)
            controls.attach(dropdown, 1, row_index, 1, 1)
        page.append(controls)
        return page

    @staticmethod
    def _mouse_picture(device: RatbagdDevice) -> Gtk.Widget:
        try:
            svg_data = get_svg(device.model)
            assert svg_data is not None
            handle = Rsvg.Handle.new_from_data(svg_data)
            assert handle is not None
            pixbuf = handle.get_pixbuf_sub("#Device")
            if pixbuf is None:
                raise ValueError("Mouse SVG does not contain a device image")
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        except (FileNotFoundError, GLib.Error, ValueError):
            return Adw.StatusPage(
                icon_name="input-mouse-symbolic",
                title=_("Mouse illustration unavailable"),
            )
        picture = Gtk.Picture.new_for_paintable(texture)
        picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        picture.set_size_request(420, 480)
        return picture

    @staticmethod
    def _button_actions(button: RatbagdButton) -> list:
        actions = []
        if RatbagdButton.ActionType.BUTTON in button.action_types:
            actions.extend(
                (
                    RatbagdButton.ActionType.BUTTON,
                    index + 1,
                    _("Mouse button {}").format(index + 1),
                )
                for index in range(16)
            )
        if RatbagdButton.ActionType.SPECIAL in button.action_types:
            actions.extend(
                (RatbagdButton.ActionType.SPECIAL, special, _(description))
                for special, description in RatbagdButton.SPECIAL_DESCRIPTION.items()
                if special
                not in (
                    RatbagdButton.ActionSpecial.INVALID,
                    RatbagdButton.ActionSpecial.UNKNOWN,
                )
            )
        if RatbagdButton.ActionType.NONE in button.action_types:
            actions.append((RatbagdButton.ActionType.NONE, None, _("Disabled")))
        return actions

    @staticmethod
    def _selected_button_action(button: RatbagdButton, actions: list) -> int:
        value = None
        if button.action_type == RatbagdButton.ActionType.BUTTON:
            value = button.mapping
        elif button.action_type == RatbagdButton.ActionType.SPECIAL:
            value = button.special
        for index, (action_type, action_value, _label) in enumerate(actions):
            if action_type == button.action_type and action_value == value:
                return index
        return 0

    def _resolution_group(self) -> Adw.PreferencesGroup:
        assert self._selected_profile is not None
        group = Adw.PreferencesGroup(
            title=_("DPI stages"),
            description=_("Choose from the DPI values supported by this mouse."),
        )
        active_index = self._draft["active_resolution"]
        for index, resolution in enumerate(self._selected_profile.resolutions):
            dpi_values = list(resolution.resolutions)
            current_value = self._draft["resolutions"][index]
            # A few devices, including the G502, can report a valid current
            # DPI that is missing from libratbag's advertised suggestions.
            # Keep it selectable instead of failing device discovery.
            if current_value not in dpi_values:
                dpi_values.append(current_value)
                dpi_values.sort()
            dpi_row = Adw.ComboRow(title=_("DPI stage {}").format(index + 1))
            dpi_row.set_model(Gtk.StringList.new([str(value) for value in dpi_values]))
            dpi_row.set_selected(dpi_values.index(current_value))
            if index == active_index:
                dpi_row.set_subtitle(_("Active DPI"))
            dpi_row.connect("notify::selected", self._on_dpi_changed, index, dpi_values)

            active_button = Gtk.Button(label=_("Use"))
            active_button.set_valign(Gtk.Align.CENTER)
            active_button.set_sensitive(index != active_index)
            active_button.connect("clicked", self._on_active_dpi_clicked, index)
            dpi_row.add_suffix(active_button)
            group.add(dpi_row)
        return group

    def _advanced_group(self) -> Optional[Adw.PreferencesGroup]:
        assert self._selected_profile is not None
        profile = self._selected_profile
        if (
            not profile.report_rates
            and not profile.debounces
            and profile.angle_snapping == -1
        ):
            return None

        group = Adw.PreferencesGroup(title=_("Advanced"))
        if profile.report_rates:
            rate_row = Adw.ComboRow(title=_("Polling rate"))
            rate_row.set_model(
                Gtk.StringList.new([str(rate) for rate in profile.report_rates])
            )
            rate_row.set_selected(
                profile.report_rates.index(self._draft["report_rate"])
            )
            rate_row.connect("notify::selected", self._on_report_rate_changed)
            group.add(rate_row)
        if profile.debounces:
            debounce_row = Adw.ComboRow(title=_("Debounce time"))
            debounce_row.set_model(
                Gtk.StringList.new(
                    [_("{} ms").format(value) for value in profile.debounces]
                )
            )
            debounce_row.set_selected(profile.debounces.index(self._draft["debounce"]))
            debounce_row.connect("notify::selected", self._on_debounce_changed)
            group.add(debounce_row)
        if profile.angle_snapping != -1:
            angle_row = Adw.SwitchRow(title=_("Angle snapping"))
            angle_row.set_active(self._draft["angle_snapping"] == 1)
            angle_row.connect("notify::active", self._on_angle_snapping_changed)
            group.add(angle_row)
        return group

    def _virtual_profiles_group(self, device: RatbagdDevice) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title=_("Virtual profiles"),
            description=_("Stored locally; loading one replaces this onboard slot."),
        )
        save_row = Adw.EntryRow(title=_("Save current profile as"))
        save_row.set_text(self._draft["name"])
        save_button = Gtk.Button(label=_("Save"))
        save_button.set_valign(Gtk.Align.CENTER)
        save_button.connect("clicked", self._on_save_virtual_profile_clicked, save_row)
        save_row.add_suffix(save_button)
        group.add(save_row)

        try:
            virtual_profiles = self._virtual_profiles.list_for_model(device.model)
        except VirtualProfileError as error:
            group.add(
                Adw.ActionRow(
                    title=_("Could not read virtual profiles"), subtitle=str(error)
                )
            )
            return group

        for virtual_profile in virtual_profiles:
            name = virtual_profile.get("name")
            if not isinstance(name, str):
                name = _("Invalid virtual profile")
            row = Adw.ActionRow(title=name)
            load_button = Gtk.Button(label=_("Load"))
            load_button.set_valign(Gtk.Align.CENTER)
            load_button.connect(
                "clicked", self._on_load_virtual_profile_clicked, virtual_profile
            )
            delete_button = Gtk.Button.new_from_icon_name("user-trash-symbolic")
            delete_button.set_valign(Gtk.Align.CENTER)
            delete_button.set_tooltip_text(_("Delete virtual profile"))
            delete_button.connect(
                "clicked", self._on_delete_virtual_profile_clicked, virtual_profile
            )
            row.add_suffix(load_button)
            row.add_suffix(delete_button)
            group.add(row)
        return group

    @staticmethod
    def _make_draft(profile: RatbagdProfile) -> dict:
        active_index = 0
        for index, resolution in enumerate(profile.resolutions):
            if resolution.is_active:
                active_index = index
                break
        return {
            "name": profile.name or _("Profile {}").format(profile.index + 1),
            "resolutions": [
                resolution.resolution[0] for resolution in profile.resolutions
            ],
            "active_resolution": active_index,
            "report_rate": profile.report_rate,
            "debounce": profile.debounce,
            "angle_snapping": profile.angle_snapping,
        }

    def _on_devices_changed(self, *_args) -> None:
        self._refresh_devices()

    def _on_profile_selected(self, selector, _pspec, device: RatbagdDevice) -> None:
        selected = selector.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            return
        self._selected_profile = device.profiles[selected]
        self._draft = self._make_draft(self._selected_profile)
        self._set_apply_sensitive(False)
        self._show_device(device)

    def _on_profile_name_changed(self, row, _pspec) -> None:
        self._draft["name"] = row.get_text()
        self._set_apply_sensitive(True)

    def _on_dpi_changed(self, row, _pspec, index: int, dpi_values: list) -> None:
        selected = row.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            return
        self._draft["resolutions"][index] = dpi_values[selected]
        self._set_apply_sensitive(True)

    def _on_button_action_changed(self, dropdown, _pspec, button, actions) -> None:
        selected = dropdown.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            return
        action_type, value, _label = actions[selected]
        try:
            if action_type == RatbagdButton.ActionType.BUTTON:
                button.mapping = value
            elif action_type == RatbagdButton.ActionType.SPECIAL:
                button.special = value
            elif action_type == RatbagdButton.ActionType.NONE:
                button.disable()
        except (GLib.Error, RatbagError, ValueError):
            self._add_toast(_("Could not change button assignment"))
            return
        self._set_apply_sensitive(True)

    def _on_active_dpi_clicked(self, _button, index: int) -> None:
        self._draft["active_resolution"] = index
        self._set_apply_sensitive(True)
        assert self._selected_device is not None
        self._show_device(self._selected_device)

    def _on_report_rate_changed(self, row, _pspec) -> None:
        assert self._selected_profile is not None
        self._draft["report_rate"] = self._selected_profile.report_rates[
            row.get_selected()
        ]
        self._set_apply_sensitive(True)

    def _on_debounce_changed(self, row, _pspec) -> None:
        assert self._selected_profile is not None
        self._draft["debounce"] = self._selected_profile.debounces[row.get_selected()]
        self._set_apply_sensitive(True)

    def _on_angle_snapping_changed(self, row, _pspec) -> None:
        self._draft["angle_snapping"] = 1 if row.get_active() else 0
        self._set_apply_sensitive(True)

    def _on_save_virtual_profile_clicked(self, _button, row) -> None:
        assert self._selected_device is not None
        assert self._selected_profile is not None
        name = row.get_text().strip()
        if not name:
            self._add_toast(_("Enter a virtual profile name"))
            return
        try:
            self._virtual_profiles.save(
                name, self._selected_device.model, self._selected_profile
            )
        except VirtualProfileError as error:
            self._add_toast(str(error))
            return
        self._add_toast(_("Virtual profile saved"))
        self._show_device(self._selected_device)

    def _on_load_virtual_profile_clicked(self, _button, virtual_profile: dict) -> None:
        assert self._selected_device is not None
        assert self._selected_profile is not None
        try:
            name = virtual_profile["name"]
            if not isinstance(name, str) or not name.strip():
                raise VirtualProfileError("This virtual profile has an invalid name")
            apply_snapshot(virtual_profile["settings"], self._selected_profile)
        except (
            KeyError,
            TypeError,
            ValueError,
            VirtualProfileError,
            GLib.Error,
        ) as error:
            self._add_toast(str(error))
            return
        self._draft = self._make_draft(self._selected_profile)
        self._draft["name"] = name
        self._set_apply_sensitive(True)
        self._add_toast(
            _("Virtual profile loaded; press Apply to write it to the mouse")
        )
        self._show_device(self._selected_device)

    def _on_delete_virtual_profile_clicked(
        self, _button, virtual_profile: dict
    ) -> None:
        try:
            self._virtual_profiles.delete(virtual_profile["id"])
        except (KeyError, VirtualProfileError) as error:
            self._add_toast(str(error))
            return
        assert self._selected_device is not None
        self._add_toast(_("Virtual profile deleted"))
        self._show_device(self._selected_device)

    def _on_activate_profile_clicked(self, button, device, profile) -> None:
        button.set_sensitive(False)
        profile.set_active_async(
            lambda _result, error: self._on_profile_activated(device, error)
        )

    def _on_profile_activated(self, device: RatbagdDevice, error) -> None:
        if error is not None:
            self._add_toast(_("Could not activate profile"))
        else:
            self._add_toast(_("Profile activated"))
        self._show_device(device)

    def _show_device(self, device: RatbagdDevice) -> None:
        self._content_page.set_child(self._device_page(device))
        self._content_page.set_title(device.name)

    def _on_apply_clicked(self, _button) -> None:
        assert self._selected_device is not None
        assert self._selected_profile is not None
        profile = self._selected_profile
        try:
            if (
                RatbagdProfile.CAP_WRITABLE_NAME in profile.capabilities
                and self._draft["name"] != profile.name
            ):
                profile.name = self._draft["name"]
            for value, resolution in zip(
                self._draft["resolutions"], profile.resolutions
            ):
                if len(resolution.resolution) == 1:
                    resolution.resolution = (value,)
                else:
                    resolution.resolution = (value, value)
            profile.resolutions[self._draft["active_resolution"]].set_active()
            if profile.report_rates:
                profile.report_rate = self._draft["report_rate"]
            if profile.debounces:
                profile.debounce = self._draft["debounce"]
            if profile.angle_snapping != -1:
                profile.angle_snapping = self._draft["angle_snapping"]
            self._selected_device.commit()
        except (GLib.Error, RatbagError, ValueError):
            self._add_toast(_("Could not apply changes"))
            return

        self._set_apply_sensitive(False)
        self._add_toast(_("Changes applied"))

    def _set_apply_sensitive(self, sensitive: bool) -> None:
        if self._apply_button is not None:
            self._apply_button.set_sensitive(sensitive)

    def _add_toast(self, title: str) -> None:
        if self._toast_overlay is not None:
            self._toast_overlay.add_toast(Adw.Toast.new(title))

    def _on_daemon_disappeared(self, *_args) -> None:
        self._show_error(
            _("ratbagd disconnected"),
            _("Restart Piper after ratbagd is available again."),
        )

    def _show_error(self, title: str, description: str) -> None:
        self._content_page.set_child(self._status_page(title, description))
        self._content_page.set_title(_("Piper Next"))

    @staticmethod
    def _status_page(title: str, description: str) -> Adw.StatusPage:
        page = Adw.StatusPage()
        page.set_icon_name("org.freedesktop.Piper-symbolic")
        page.set_title(title)
        page.set_description(description)
        return page
