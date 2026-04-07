# Build Test Guide

This document describes how to build the Wails application into a Windows `.exe`, verify the NSIS installer, and confirm that the Python scraper is still callable after packaging.

## 1. Build the `.exe`

From `wails-app/` run:

```bash
wails build
```

Notes:

- The build target should produce a Windows executable when run on Windows.
- If you are cross-checking from another environment, verify the build output directory configured in `wails.json`.
- Make sure the embedded app icon, version metadata, and product name are correct before release.

## 2. NSIS installer configuration and verification

The installer is generated through the Wails build pipeline using the NSIS backend.

### What to verify

- Installer name matches the application name
- Version metadata matches `wails.json`
- Install and uninstall entries are present
- The installer bundles the app executable and required runtime assets

### Verification steps

1. Run `wails build`
2. Confirm the generated installer is created alongside the build output
3. Install the app on a clean Windows test machine
4. Launch the app from Start Menu or the installed shortcut
5. Uninstall the app
6. Confirm installed files and shortcuts are removed cleanly

## 3. Confirm Python scraper still works after packaging

The backend calls `src/scrapers/run_search.py` through a subprocess.

### What to check

- The packaged app can locate the Python interpreter
- The script path resolution still works after bundling
- `PythonSearch(code)` returns JSON stdout that the Go backend can parse

### Recommended validation

- Run the backend integration smoke test
- Trigger a search from the UI after packaging
- Confirm that:
  - stdout is valid JSON
  - stderr failures are reported clearly
  - timeout handling still works
  - JSON parse errors are classified separately

## 4. Packaged smoke test checklist

After building the `.exe`, verify the following:

- [ ] Application launches normally
- [ ] Scan directory works
- [ ] Search works
- [ ] Move file / batch move works
- [ ] Preferences can be read
- [ ] Preferences can be updated
- [ ] Preferences can be reset
- [ ] Operation history can be listed
- [ ] Rollback works
- [ ] Python scraper is callable from the packaged app
- [ ] Errors are reported with useful messages

## 5. Practical release gate

Before shipping, make sure these are all true:

- `wails build` succeeds
- Installer installs and uninstalls cleanly
- Backend integration tests pass
- The packaged app can still reach `run_search.py`
- Smoke checklist is fully green
