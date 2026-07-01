# Windows Installer Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Release-ready Windows installer that bundles the Python GUI app, all runtime dependencies, and a Windows `bader.exe` without including local workspaces or grouping data.

**Architecture:** Follow the DBand Studio release pattern: PyInstaller creates a one-directory frozen app, then Inno Setup recursively packages that directory into an installer. Frozen runtime paths resolve resources from the install directory, bundled Bader from `bader_engine/`, and user workspaces from `%LOCALAPPDATA%`.

**Tech Stack:** Python 3.12 Conda environment, PyInstaller, Inno Setup 6, PySide6, PyVista/VTK, pymatgen.

---

### Task 1: Frozen Runtime Paths

**Files:**
- Create: `core/runtime_paths.py`
- Modify: `core/workspace_manager.py`
- Modify: `gui/app_icon.py`
- Modify: `gui/main_window.py`
- Test: `tests/test_runtime_paths.py`

- [x] Add helpers for detecting frozen execution, resolving install-directory resources, finding bundled Bader candidates, and choosing a writable frozen workspace root.
- [x] Keep source-mode workspace behavior as `workspaces/`.
- [x] Use `%LOCALAPPDATA%\Bader Charge Analyzer\workspaces` only when frozen.
- [x] Update app icon and Bader lookup to use install-directory-aware paths.
- [x] Verify with targeted tests.

### Task 2: PyInstaller Bundle

**Files:**
- Create: `installer/bader_charge_analyzer.spec`

- [x] Build `dist/BaderChargeAnalyzer/BaderChargeAnalyzer.exe` in one-directory mode.
- [x] Include app source, `图标.png`, `assets/`, PySide6, PyVista, PyVistaQt, VTK, pymatgen, matplotlib, SciPy dynamic libraries, qtawesome, qdarktheme, requests, Pillow, and openpyxl.
- [x] Include only `installer/runtime/bader_engine/` for bundled Bader; do not add repository `workspaces/`.

### Task 3: Inno Setup Installer

**Files:**
- Create: `installer/setup.iss`

- [x] Package the full PyInstaller output directory recursively.
- [x] Use a default install path under `{autopf}` while keeping Inno's install location page available.
- [x] Create Start Menu and optional desktop shortcuts with `{app}` as the working directory.

### Task 4: Build Automation

**Files:**
- Create: `installer/build_windows.ps1`
- Modify: `.gitignore`
- Modify: `README.md`

- [x] Validate that the supplied Bader binary is a Windows PE executable.
- [x] Generate the installer icon from `图标.png`.
- [x] Copy `bader.exe` into ignored `installer/runtime/bader_engine/`.
- [x] Run PyInstaller, then Inno Setup.
- [x] Document build prerequisites, commands, and outputs.

### Task 5: Verification

**Commands:**

```powershell
& 'c:\Users\21483\.conda\envs\lis_sac_ml\python.exe' -m pytest tests/test_runtime_paths.py tests/test_workspace_manager_grouping.py --basetemp '.pytest_tmp_packaging' -q
& 'c:\Users\21483\.conda\envs\lis_sac_ml\python.exe' -m py_compile core\runtime_paths.py core\workspace_manager.py gui\app_icon.py gui\main_window.py
& 'c:\Users\21483\.conda\envs\lis_sac_ml\python.exe' -m PyInstaller --version
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_windows.ps1 -BaderExe bader
```

**Expected:**
- Runtime path and workspace tests pass.
- Python compile check exits 0.
- PyInstaller reports the installed version.
- The build script rejects the repository root Linux ELF `bader` and asks for a Windows `bader.exe`.
