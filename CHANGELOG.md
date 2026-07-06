# Changelog

All notable changes to this project are documented in this file.
The format is loosely based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — 2026-07-07

### Added
- **Cross-platform support (macOS / Linux)** alongside Windows. Opening a previewed
  file now dispatches per-OS (`start` / `open` / `xdg-open`), and extraction uses the
  system temp directory instead of a hard-coded `D:\temp`.
- **Configurable preview / extraction directory.** Pick any folder or drive
  (e.g. `D:\`, `/Volumes/USB`) via **设置 → 预览提取目录…**. The choice is validated
  (directory created + write-tested) and persisted to
  `~/.ios_housearrest_explorer.json`; a bottom status bar shows the current directory,
  and **打开当前预览目录** opens it in the file manager.
- `requirements.txt` pinning `pymobiledevice3>=7,<8`.
- `CHANGELOG.md` and `.gitignore`.

### Fixed
- **Broken on fresh installs.** A plain `pip install pymobiledevice3` now resolves a
  9.x release whose services moved to an async/await API this GUI does not use, so
  `afc.pull(...)` returns an un-awaited coroutine and silently downloads nothing while
  reporting success. Pinned to the last synchronous line (7.x; last release 7.8.3).
- **UI froze during device I/O.** Mounting an app sandbox and listing / expanding
  directories ran on the Tk main thread. All AFC I/O now runs on background threads
  and the tree is built on the main thread from the fetched data.
- **AFC socket corruption under concurrency.** The single AFC socket could be accessed
  by several threads at once (e.g. previewing a file while a batch export was running).
  A lock now serializes all AFC reads / writes and the connection close.
- **Batch export overwrote same-named files** coming from different directories. Files
  now retain their remote folder hierarchy beneath the chosen export root.
- **Batch export nested exported folders one level too deep** (`root/name/name`):
  `afc.pull` already appends the source basename, so the export root is passed directly.
- **Path-traversal hardening** for extraction paths via `os.path.commonpath`, which also
  fixes containment checks for drive-root bases such as `D:\`.
- **App-switch races.** Stale background results are discarded via a token guard, and the
  previously mounted app's AFC connection is now closed to avoid socket leaks.
- **App-list load failures** are surfaced to the user instead of leaving the dropdown
  stuck on "loading".
- The batch-export progress bar now reaches 100% on completion.

### Changed
- README documents cross-platform prerequisites (macOS ships usbmuxd; Linux needs the
  `usbmuxd` package) and the pinned dependency.
