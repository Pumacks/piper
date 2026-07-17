# Repository Guidelines

## Project Structure & Module Organization

Piper is a Python/GTK 3 frontend for the `ratbagd` system D-Bus service. Application code lives in `piper/`; UI pages generally pair a Python module such as `mouseperspective.py` with a GtkBuilder template in `data/ui/`. Images, desktop metadata, and compiled-resource inputs are under `data/`; translations are under `po/`. Tests and repository checks live in `tests/`, while formatting helpers live in `tools/`.

The local virtual-profile feature is implemented in `piper/virtualprofiles.py`, `piper/virtualprofilerow.py`, and `piper/mouseperspective.py`. Virtual profiles are model-specific JSON snapshots stored in the user's Piper configuration directory. Loading one updates the selected onboard slot but does not write the device until **Apply** is pressed.

## Build, Test, and Development Commands

- `meson setup builddir --prefix=/usr` configures a new build.
- `ninja -C builddir` rebuilds code, translations, and GTK resources.
- `./builddir/piper.devel` runs from the source tree; `ratbagd` must be available on the system bus.
- `meson test -C builddir --print-errorlogs` runs all checks and tests.
- `ninja -C builddir python-black-check` and `ninja -C builddir python-ruff-check` run focused style checks.
- `./install-user.sh` rebuilds and installs this fork under `~/.local`, then refreshes its desktop launcher.

## Coding Style & Naming Conventions

Use four-space indentation and Black-compatible Python formatting. Ruff settings are defined in `pyproject.toml`. Follow existing conventions: `snake_case` for functions and modules, `PascalCase` for GTK/GObject classes, and leading underscores for private callbacks or state. Keep GtkBuilder object IDs and callback names descriptive and aligned with their Python template declarations.

## Testing Guidelines

Add regression tests for behavior changes. Python test scripts use the `*-test.py` naming pattern and are registered in `meson.build`; shell-based repository checks use `check-*.sh`. Device-independent logic should use fakes, as in `tests/virtual-profiles-test.py`, rather than requiring physical hardware. Run the complete Meson suite before submitting.

## Commit & Pull Request Guidelines

Recent history favors short imperative subjects, often with a scope, for example `data: add SVG...`, `build: update Ruff...`, or `feat: added virtual profiles`. Keep each commit focused. Pull requests should explain user-visible behavior, list verification commands, link relevant issues, and include screenshots for GTK UI changes. Call out required `libratbag` versions or hardware-specific assumptions.
