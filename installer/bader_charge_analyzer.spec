# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Bader Charge Analyzer.

Build:
  pyinstaller --clean --noconfirm installer/bader_charge_analyzer.spec

Output:
  dist/BaderChargeAnalyzer/BaderChargeAnalyzer.exe
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs


PROJECT_ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def collect_package(package_name):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    return package_datas, package_binaries, package_hiddenimports


datas = [
    (str(PROJECT_ROOT / "图标.png"), "."),
    (str(PROJECT_ROOT / "assets"), "assets"),
]
binaries = []
hiddenimports = [
    "core",
    "gui",
    "rendering",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.qt_compat",
    "numpy.core._methods",
    "numpy.lib.format",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "qtawesome",
    "qdarktheme",
    "qtpy",
    "vtk",
    "pyvista",
    "pyvistaqt",
    "pymatgen",
    "pymatgen.io",
    "pymatgen.io.vasp",
    "pymatgen.io.vasp.inputs",
    "pymatgen.io.vasp.outputs",
    "pymatgen.core",
    "pymatgen.core.structure",
    "pymatgen.core.composition",
    "pymatgen.core.periodic_table",
    "pymatgen.core.lattice",
    "pymatgen.analysis",
    "pymatgen.symmetry",
    "pymatgen.symmetry.analyzer",
    "openpyxl",
    "PIL",
    "requests",
]

for package_name in ("pymatgen", "pyvista", "pyvistaqt", "vtk", "qtpy", "qtawesome"):
    package_datas, package_binaries, package_hiddenimports = collect_package(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

datas += collect_data_files("matplotlib")
binaries += collect_dynamic_libs("scipy")

bader_runtime_dir = PROJECT_ROOT / "installer" / "runtime" / "bader_engine"
if bader_runtime_dir.exists():
    datas.append((str(bader_runtime_dir), "bader_engine"))

icon_path = PROJECT_ROOT / "installer" / "BaderChargeAnalyzer.ico"
icon_arg = str(icon_path) if icon_path.exists() else None

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "jupyter",
        "jupyter_client",
        "jupyter_core",
        "notebook",
        "ipykernel",
        "numba",
        "llvmlite",
        "torch",
        "torchvision",
        "torchaudio",
        "tensorboard",
        "tensorflow",
        "pyarrow",
        "boto3",
        "botocore",
        "s3fs",
        "fsspec",
        "zmq",
        "sqlalchemy",
        "sklearn",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "pytest",
        "tests",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BaderChargeAnalyzer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="BaderChargeAnalyzer",
)
