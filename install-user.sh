#!/bin/sh

set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build_dir="$repo_dir/builddir"
install_prefix="$HOME/.local"

if [ -f "$build_dir/build.ninja" ]; then
    meson setup --reconfigure "$build_dir" --prefix="$install_prefix"
else
    meson setup "$build_dir" --prefix="$install_prefix"
fi

meson compile -C "$build_dir"

# A previous sudo or sandboxed install may leave Meson's generated log owned
# by another user. Preserve it under a backup name so Meson can create a new
# writable log; none of the actual build output is discarded.
install_log="$build_dir/meson-logs/install-log.txt"
if [ -e "$install_log" ] && [ ! -w "$install_log" ]; then
    mv "$install_log" "$install_log.previous.$$"
fi

meson install -C "$build_dir"

# Desktop sessions do not universally include ~/.local/bin in PATH. Use the
# absolute executable path so the launcher cannot accidentally open a distro
# or Flatpak version of Piper instead.
desktop_file="$install_prefix/share/applications/org.freedesktop.Piper.desktop"
if [ -f "$desktop_file" ]; then
    sed -i "s|^Exec=.*|Exec=$install_prefix/bin/piper|" "$desktop_file"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$install_prefix/share/applications"
fi

printf '\nPiper was installed for this user.\n'
printf 'Close any running Piper window, then open Piper from the application menu.\n'
printf 'Installed executable: %s/bin/piper\n' "$install_prefix"
