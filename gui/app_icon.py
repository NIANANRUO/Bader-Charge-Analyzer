# -*- coding: utf-8 -*-
from pathlib import Path

from PySide6.QtGui import QIcon


APP_ICON_FILENAME = "图标.png"


def app_icon_path() -> Path:
    return Path(__file__).resolve().parent.parent / APP_ICON_FILENAME


def load_app_icon() -> QIcon:
    path = app_icon_path()
    return QIcon(str(path)) if path.exists() else QIcon()
