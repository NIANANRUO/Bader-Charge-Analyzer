# -*- coding: utf-8 -*-
import os as _os
_os.environ.setdefault("QT_API", "pyside6")  # force pyvistaqt to use PySide6, not PyQt5

from pyvistaqt import QtInteractor
from PySide6.QtCore import QPoint, Signal, QTimer, QObject, QEvent, Qt
from PySide6.QtGui import QAction, QPainter, QColor, QCursor, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
    QMenu, QLabel, QFrame, QGridLayout, QApplication,
)
import qtawesome as qta

# Diagnostic logging — writes to stderr AND a module-level list that
# debug scripts can read.  Set PICK_DEBUG=1 env var to also popup
# a QMessageBox on each click (very noisy, only for diagnosis).
import sys as _sys
import traceback as _tb

_PICK_DEBUG = _os.environ.get("PICK_DEBUG", "") == "1"
_pick_log: list[str] = []


def _pick_log_msg(msg: str) -> None:
    """Append to pick log and write to stderr."""
    _pick_log.append(msg)
    print(f"[PICK] {msg}", file=_sys.stderr, flush=True)


# vtk is imported lazily inside _install_picking to avoid
# hard dependency at module load time; falls back gracefully if missing.

from core.bond_detector import BondDetector
from core.structure_model import Structure3D
from rendering.pyvista_structure_renderer import PyVistaStructureRenderer, RenderSettings
from rendering.scene_cache import AppearanceKey, GeometryKey, SceneCache


class _MouseEventFilter(QObject):
    """Qt event filter that intercepts mouse clicks on the QtInteractor
    widget for atom picking, bypassing VTK's unreliable observer system.

    - Left press: record position
    - Left release: if not a drag (≤5 px), pick atom and select
    - Right press: pick atom and show context menu, consume event

    All non-click events (drag for camera rotate, wheel for zoom, etc.)
    pass through to VTK untouched (``return False``).
    """

    def __init__(self, visualizer: "Visualizer3D"):
        super().__init__(visualizer)
        self._viz = visualizer
        self._left_press_pos: tuple[float, float] | None = None

    def eventFilter(self, obj, event):
        etype = event.type()

        if etype == QEvent.MouseButtonPress:
            btn = event.button()
            pos = (event.position().x(), event.position().y())
            if btn == Qt.MouseButton.LeftButton:
                _pick_log_msg(f"LEFT PRESS at qt={pos}")
                self._left_press_pos = pos
            elif btn == Qt.MouseButton.RightButton:
                _pick_log_msg(f"RIGHT PRESS at qt={pos}")
                self._viz._handle_right_click_qt(pos)
                return True  # consume

        elif etype == QEvent.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self._left_press_pos is not None:
                rx, ry = event.position().x(), event.position().y()
                px, py = self._left_press_pos
                self._left_press_pos = None
                moved = abs(rx - px) > 5 or abs(ry - py) > 5
                _pick_log_msg(f"LEFT RELEASE at ({rx},{ry}) moved={moved}")
                if not moved:
                    self._viz._handle_left_click_qt((rx, ry))
            return False

        return False


class _AtomInfoGlassPanel(QWidget):
    """Frosted-glass floating panel for atom information display.

    Replaces the plain QMenu right-click context menu with a modern
    translucent panel that shows atomic properties and provides quick
    action buttons.
    """

    def __init__(self, atom, visualizer, parent=None):
        super().__init__(parent)
        self._viz = visualizer
        self._atom = atom
        self._dismissed = False
        self._setup_window()
        self._build_ui(atom)
        self._try_acrylic_blur()
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._dismiss)

    # ---- window setup ----

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)

    def _try_acrylic_blur(self):
        """Try to enable Windows acrylic / Mica backdrop blur."""
        import sys as _sys
        if _sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi

            class MARGINS(ctypes.Structure):
                _fields_ = [
                    ("cxLeftWidth", ctypes.c_int),
                    ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int),
                    ("cyBottomHeight", ctypes.c_int),
                ]
            margins = MARGINS(-1, -1, -1, -1)
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))

            try:
                accent_struct = type(
                    "_ACCENT_POLICY",
                    (ctypes.Structure,),
                    {"_fields_": [
                        ("AccentState", ctypes.c_int),
                        ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint),
                        ("AnimationId", ctypes.c_int),
                    ]},
                )()
                accent_struct.AccentState = 3  # ACCENT_ENABLE_ACRYLICBLURBEHIND
                accent_struct.GradientColor = 0x99FFFFFF
                compdata_struct = type(
                    "_WINCOMPATTRDATA",
                    (ctypes.Structure,),
                    {"_fields_": [
                        ("Attribute", ctypes.c_int),
                        ("Data", ctypes.c_void_p),
                        ("SizeOfData", ctypes.c_size_t),
                    ]},
                )()
                compdata_struct.Attribute = 19  # WCA_ACCENT_POLICY
                compdata_struct.Data = ctypes.addressof(accent_struct)
                compdata_struct.SizeOfData = ctypes.sizeof(accent_struct)
                ctypes.windll.user32.SetWindowCompositionAttribute(
                    hwnd, ctypes.byref(compdata_struct)
                )
            except Exception:
                pass
        except Exception:
            pass

    # ---- UI construction ----

    def _build_ui(self, atom):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(0)

        # -- Header: element symbol + atom number --
        hdr = QHBoxLayout()
        elem_lbl = QLabel(atom.element)
        elem_lbl.setStyleSheet("font-size:28px; font-weight:700; color:#1a1a2e;")
        hdr.addWidget(elem_lbl)
        hdr.addStretch()
        id_lbl = QLabel(f"#{atom.atom_id}")
        id_lbl.setStyleSheet("font-size:15px; color:#777; font-weight:500;")
        hdr.addWidget(id_lbl)
        outer.addLayout(hdr)

        outer.addSpacing(4)
        outer.addWidget(self._hline())
        outer.addSpacing(10)

        # -- Data grid --
        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        charge = atom.charge
        raw_c = atom.raw_charge
        zval = atom.zval
        coord = self._viz._compute_coordination(atom.atom_id - 1)
        pos = atom.cart_coords

        row = 0
        self._grid_row(grid, row, "Bader 电荷",
                         f"{charge:+.4f} e", self._charge_color(charge), bold=True)
        row += 1
        self._grid_row(grid, row, "原始电荷", f"{raw_c:.4f}")
        row += 1
        self._grid_row(grid, row, "ZVAL", f"{zval:.1f}")
        row += 1
        self._grid_row(grid, row, "净转移",
                         f"{charge:+.4f} e", self._charge_color(charge), bold=True)
        row += 1
        self._grid_row(grid, row, "配位数", str(coord))
        row += 1
        self._grid_row(grid, row, "位  置",
                         f"[{pos[0]:.2f},  {pos[1]:.2f},  {pos[2]:.2f}]",
                         mono=True)

        outer.addLayout(grid)
        outer.addSpacing(10)
        outer.addWidget(self._hline())
        outer.addSpacing(10)

        # -- Action buttons --
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_defs = [
            ("fa5s.eye", "聚焦", "#198754", self._viz.focus_atom),
            ("fa5s.bullseye", "隔离", "#0D6EFD", self._viz.isolate_atom),
            ("fa5s.times-circle", "清除", "#dc3545", self._viz.clear_selection),
        ]
        for icon_name, text, color, func in btn_defs:
            btn = QPushButton(f" {text}")
            btn.setIcon(qta.icon(icon_name, color=color))
            btn.setStyleSheet(
                f"QPushButton{{background:rgba(0,0,0,0.04);border:1px solid "
                f"rgba(0,0,0,0.08);border-radius:6px;padding:6px 14px;"
                f"font-size:12px;color:#333;}}"
                f"QPushButton:hover{{background:rgba(0,0,0,0.09);}}"
                f"QPushButton:pressed{{background:rgba(0,0,0,0.14);}}"
            )
            btn.clicked.connect(lambda checked=False, f=func: (self._dismiss(), f()))
            btn_row.addWidget(btn)
        outer.addLayout(btn_row)
        outer.addSpacing(6)

        # -- Copy button --
        copy_btn = QPushButton(" 复制信息到剪贴板")
        copy_btn.setIcon(qta.icon("fa5s.copy", color="#888"))
        copy_btn.setStyleSheet(
            "QPushButton{background:rgba(0,0,0,0.02);border:1px dashed "
            "rgba(0,0,0,0.15);border-radius:6px;padding:6px 14px;"
            "font-size:12px;color:#666;}"
            "QPushButton:hover{background:rgba(0,0,0,0.06);color:#333;}"
        )
        copy_btn.clicked.connect(self._copy_info)
        outer.addWidget(copy_btn)

    # ---- helpers ----

    @staticmethod
    def _hline():
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:rgba(0,0,0,0.10);max-height:1px;")
        return line

    @staticmethod
    def _grid_row(grid, row, label_text, value_text,
                  color="#333", bold=False, mono=False):
        lbl = QLabel(label_text)
        lbl.setStyleSheet(
            f"font-size:13px;color:rgba(30,30,50,0.55);font-weight:500;"
        )
        grid.addWidget(lbl, row, 0, Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignTop)

        val = QLabel(value_text)
        fw = "font-weight:600;" if bold else ""
        ff = "font-family:'Cascadia Code','Consolas',monospace;" if mono else ""
        val.setStyleSheet(f"font-size:13px;color:{color};{fw}{ff}")
        grid.addWidget(val, row, 1, Qt.AlignmentFlag.AlignLeft)

    @staticmethod
    def _charge_color(charge):
        if charge > 0.001:
            return "#c62828"
        if charge < -0.001:
            return "#1565c0"
        return "#555"

    def _copy_info(self):
        atom = self._atom
        charge = atom.charge
        pos = atom.cart_coords
        coord = self._viz._compute_coordination(atom.atom_id - 1)
        text = "\n".join([
            f"{atom.element}#{atom.atom_id}",
            f"Bader 电荷: {charge:+.4f} e",
            f"CHARGE: {atom.raw_charge:.4f}",
            f"ZVAL: {atom.zval:.1f}",
            f"净转移: {charge:+.4f} e",
            f"配位数: {coord}",
            f"位置: [{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]",
        ])
        QApplication.clipboard().setText(text)
        self._dismiss()

    def _dismiss(self):
        if self._dismissed:
            return
        self._dismissed = True
        self.hide()
        if hasattr(self._viz, '_glass_panel') and self._viz._glass_panel is self:
            self._viz._glass_panel = None
        self.deleteLater()

    # ---- event overrides ----

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # translucent fill
        p.setBrush(QColor(255, 255, 255, 195))
        p.setPen(QColor(255, 255, 255, 120))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
        # subtle border
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QColor(0, 0, 0, 28))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
        p.end()

    def show_at(self, global_pos):
        """Position panel near *global_pos* and show it."""
        self.adjustSize()
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        sg = screen.availableGeometry()
        w, h = self.width(), self.height()
        x = global_pos.x() + 16
        y = global_pos.y() - 12
        if x + w > sg.right() - 8:
            x = global_pos.x() - w - 16
        if y + h > sg.bottom() - 8:
            y = sg.bottom() - h - 8
        if y < sg.top() + 8:
            y = sg.top() + 8
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event):
        # clicks on the panel itself should not dismiss it
        event.accept()

    def focusOutEvent(self, event):
        self._dismiss()

    def event(self, event):
        if event.type() == QEvent.WindowDeactivate:
            self._dismiss()
        return super().event(event)


class Visualizer3D(QWidget):
    """PyVista-based 3D atomistic structure viewer for VASP / Bader analysis."""

    atom_selected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.struct = None
        self.df = None
        self.structure_model = None
        self.chg_dict = {}
        self.charge_dict = {}
        self.zval_dict = {}

        self.render_settings = {
            "hide_bg": False,
            "show_labels": False,
            "show_bonds": True,
            "target_str": "",
            "label_target_str": "",
            "transparency": 10,
            "sphere_scale": 100,
            "ambient_light": 0,
            "bond_radius": 8,
            "show_cell": False,
            "show_axes_flag": False,
            "color_by": "Bader 电荷",
            "cmap": "RdBu_r",
            "cmap_gamma": 1.0,
            "cmap_range": "极值",
            "color_profile": "标准",
            "representation": "ball_stick",
        }

        self.is_dark_theme = False
        self.selected_atom_idx = -1
        self._is_isolated = False
        self._highlight_actor = None
        self._ground_actor = None
        self._lightkit_enabled = False
        self._glass_panel = None
        self._is_closing = False

        self.init_ui()
        self.renderer = PyVistaStructureRenderer(self.plotter)

        # --- Debounce machinery for render coalescing ---
        self._debounce_timer: QTimer | None = None
        self._debounce_ms = 80  # ms to wait before executing a pending render

        # --- Picking state (installed lazily in load_data) ---
        self._picking_installed = False
        self._vtk_module = None
        self._event_filter: _MouseEventFilter | None = None

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("ContentToolbar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(15, 5, 15, 5)

        btn_defs = [
            (" 重置", "fa5s.home", self.reset_camera),
            (" XY", "fa5s.border-all", lambda: self._safe_view(self.plotter.view_xy)),
            (" XZ", "fa5s.border-all", lambda: self._safe_view(self.plotter.view_xz)),
            (" YZ", "fa5s.border-all", lambda: self._safe_view(self.plotter.view_yz)),
            (" 等轴", "fa5s.cube", lambda: self._safe_view(self.plotter.view_isometric)),
            (" 正交/透视", "fa5s.eye", self.toggle_projection),
        ]
        for name, icon, func in btn_defs:
            btn = QPushButton(name)
            btn.setIcon(qta.icon(icon, color="#555"))
            btn.setFlat(True)
            btn.setStyleSheet("font-weight:bold;color:#555;padding:3px 6px;")
            btn.clicked.connect(func)
            top_layout.addWidget(btn)
        top_layout.addStretch()

        self.plotter = QtInteractor(self)
        self.plotter.set_background("white")
        self.plotter.camera.SetParallelProjection(False)
        self._restore_ground_grid()

        main_layout.addWidget(top_bar)
        main_layout.addWidget(self.plotter.interactor, 1)

        # Picking is installed lazily in load_data() once the renderer's
        # actor→atom_id map is available.  We use a Qt event filter on the
        # interactor widget instead of plotter.enable_mesh_picking to get
        # reliable actor resolution for both left-click (select) and
        # right-click (context menu).

    def _install_picking(self):
        if self._picking_installed:
            return
        self._picking_installed = True

        try:
            import vtk
        except ImportError:
            _pick_log_msg("ERROR: vtk module not available")
            return
        self._vtk_module = vtk

        self._event_filter = _MouseEventFilter(self)
        # IMPORTANT: install on the actual VTK interactor widget, NOT on
        # the QtInteractor (QFrame) container.  Mouse events are delivered
        # to the child widget under the cursor; a filter on the parent
        # would never see them.
        self.plotter.interactor.installEventFilter(self._event_filter)
        _pick_log_msg(
            f"Event filter installed on plotter.interactor "
            f"(type={type(self.plotter.interactor).__name__}, "
            f"size={self.plotter.interactor.size().width()}x{self.plotter.interactor.size().height()})"
        )

    # ------------------------------------------------------------------
    #  Qt-event-driven picking handlers
    # ------------------------------------------------------------------

    def _qt_to_vtk_coords(self, qt_pos: tuple[float, float]) -> tuple[int, int]:
        """Convert Qt widget coords (top-left origin) to VTK display
        coords (bottom-left origin, physical pixels).

        Must match the conversion in ``QVTKRenderWindowInteractor.
        _setEventInformation`` — Qt logical pixels × devicePixelRatio,
        Y-axis flipped — otherwise the picker fires at the wrong screen
        position on HiDPI displays.
        """
        dpr = self.plotter.interactor.devicePixelRatio()
        h = self.plotter.interactor.height()
        x = int(round(qt_pos[0] * dpr))
        y = int(round((h - qt_pos[1] - 1) * dpr))
        return (x, y)

    def _pick_atom_at(self, vtk_pos: tuple[int, int]) -> int | None:
        """Ray-cast from *vtk_pos* into the scene and return the atom_id.

        Uses ``vtkCellPicker.GetDataSet()`` + cell data lookup — the
        robust approach that does NOT depend on object identity.
        """
        if self._vtk_module is None:
            _pick_log_msg("  pick: vtk module is None")
            return None
        if self.structure_model is None:
            _pick_log_msg("  pick: structure_model is None")
            return None

        picker = self._vtk_module.vtkCellPicker()
        picker.SetTolerance(0.02)
        picker.Pick(vtk_pos[0], vtk_pos[1], 0, self.plotter.renderer)

        cell_id = picker.GetCellId()
        dataset = picker.GetDataSet()
        has_atom_id = False
        if dataset is not None:
            try:
                import pyvista as _pv
                pv_ds = _pv.wrap(dataset)
                has_atom_id = "atom_id" in pv_ds.cell_data
            except Exception:
                pass

        _pick_log_msg(
            f"  pick: vtk_pos={vtk_pos} -> cell_id={cell_id}, "
            f"dataset_is_none={dataset is None}, has_atom_id_data={has_atom_id}"
        )

        atom_id = self.renderer.atom_id_for_picked_cell(picker)
        _pick_log_msg(f"  pick: resolved atom_id={atom_id}")
        return atom_id

    def _handle_left_click_qt(self, qt_pos: tuple[float, float]) -> None:
        """Process a left-click (non-drag) from the Qt event filter."""
        _pick_log_msg(f"LEFT CLICK handler qt_pos={qt_pos}")
        if self.structure_model is None:
            _pick_log_msg("  -> structure_model is None, abort")
            return
        vtk_pos = self._qt_to_vtk_coords(qt_pos)
        dpr = self.plotter.interactor.devicePixelRatio()
        _pick_log_msg(f"  -> vtk_pos={vtk_pos}, dpr={dpr}, h={self.plotter.interactor.height()}")
        atom_id = self._pick_atom_at(vtk_pos)
        _pick_log_msg(f"  -> atom_id={atom_id}")
        self._handle_left_pick(atom_id)

    def _handle_right_click_qt(self, qt_pos: tuple[float, float]) -> None:
        """Process a right-click from the Qt event filter."""
        _pick_log_msg(f"RIGHT CLICK handler qt_pos={qt_pos}")
        if self.structure_model is None:
            _pick_log_msg("  -> structure_model is None, abort")
            return
        vtk_pos = self._qt_to_vtk_coords(qt_pos)
        _pick_log_msg(f"  -> vtk_pos={vtk_pos}, interactor.height={self.plotter.interactor.height()}")
        atom_id = self._pick_atom_at(vtk_pos)
        _pick_log_msg(f"  -> atom_id={atom_id}")
        if atom_id is None:
            _pick_log_msg("  -> no atom hit, no menu")
            return
        try:
            atom = self.structure_model.atom_by_id(atom_id)
        except KeyError:
            _pick_log_msg(f"  -> atom_id={atom_id} not in model (KeyError)")
            return
        _pick_log_msg(f"  -> showing menu for {atom.element}#{atom.atom_id}")

        self.selected_atom_idx = atom_id - 1
        self.atom_selected.emit(
            {
                "id": atom.atom_id,
                "element": atom.element,
                "charge": atom.charge,
                "bader_raw": atom.raw_charge,
                "zval": atom.zval,
                "coord": self._compute_coordination(self.selected_atom_idx),
                "pos": atom.cart_coords,
            }
        )
        self._update_selection_highlight()
        self._show_atom_context_menu(atom)

    def _handle_left_pick(self, atom_id: int | None) -> None:
        """Process a left-click pick result — select or deselect."""
        if atom_id is None or self.structure_model is None:
            self.selected_atom_idx = -1
            self.atom_selected.emit({})
            self._update_selection_highlight()
            return

        try:
            atom = self.structure_model.atom_by_id(atom_id)
        except KeyError:
            self.selected_atom_idx = -1
            self.atom_selected.emit({})
            self._update_selection_highlight()
            return

        self.selected_atom_idx = atom_id - 1
        self.atom_selected.emit(
            {
                "id": atom.atom_id,
                "element": atom.element,
                "charge": atom.charge,
                "bader_raw": atom.raw_charge,
                "zval": atom.zval,
                "coord": self._compute_coordination(self.selected_atom_idx),
                "pos": atom.cart_coords,
            }
        )
        self._update_selection_highlight()

    def load_data(self, struct, df):
        if self._is_closing:
            return
        self.struct = struct
        self.df = df
        self.selected_atom_idx = -1
        self._is_isolated = False

        if df is not None:
            self.chg_dict = dict(zip(df["Atom"].values, df["Bader_Charge"].values))
            self.charge_dict = dict(zip(df["Atom"].values, df["CHARGE"].values))
            self.zval_dict = dict(zip(df["Atom"].values, df["ZVAL"].values))
        else:
            self.chg_dict = {}
            self.charge_dict = {}
            self.zval_dict = {}

        if struct is None:
            self.structure_model = None
            self.renderer.clear()
            return

        model = Structure3D.from_pymatgen(struct, df)
        bonds = BondDetector().detect(struct, model.atoms)
        self.structure_model = model.with_bonds(bonds)
        self.render_scene_now()
        self.reset_camera()
        self._install_picking()

    def set_analysis_selection(self, selected_atom_ids):
        """Set the authoritative committed scope without scheduling a render."""
        ids = tuple(sorted(int(atom_id) for atom_id in selected_atom_ids))
        self.render_settings["target_str"] = ",".join(map(str, ids))
        self._is_isolated = False

    def update_appearance(self, df, selected_atom_ids):
        """Refresh charges and committed-scope coloring without rebuilding geometry."""
        if self._is_closing or self.structure_model is None:
            return
        self.df = df
        self.set_analysis_selection(selected_atom_ids)
        self.structure_model = self.structure_model.with_charges(df)
        if df is not None:
            self.chg_dict = dict(zip(df["Atom"].values, df["Bader_Charge"].values))
            self.charge_dict = dict(zip(df["Atom"].values, df["CHARGE"].values))
            self.zval_dict = dict(zip(df["Atom"].values, df["ZVAL"].values))
        self.renderer.update_appearance(self.structure_model, self._render_settings())
        self._highlight_actor = self.renderer._highlight_actor

    def set_render_state(
        self,
        hide_bg,
        show_labels,
        show_bonds,
        target_str,
        label_target_str,
        trans,
        scale,
        light,
        bond_radius=8,
        show_cell=True,
        show_axes_flag=True,
        color_by="Bader 电荷",
        cmap="RdBu_r",
        cmap_gamma=1.0,
        cmap_range="极值",
        color_profile="标准",
        representation="ball_stick",
        custom_colors=None,
    ):
        if self._is_closing:
            return
        previous = dict(self.render_settings)
        incoming_target = self.render_settings.get("target_str", "") if target_str is None else (target_str or "")
        if self._is_isolated and not incoming_target and self.render_settings.get("target_str"):
            incoming_target = self.render_settings["target_str"]
        else:
            self._is_isolated = False

        self.render_settings.update(
            {
                "hide_bg": hide_bg,
                "show_labels": show_labels,
                "show_bonds": show_bonds,
                "target_str": incoming_target,
                "label_target_str": label_target_str,
                "transparency": trans,
                "sphere_scale": scale,
                "ambient_light": light,
                "bond_radius": bond_radius,
                "show_cell": show_cell,
                "show_axes_flag": show_axes_flag,
                "color_by": color_by,
                "cmap": cmap,
                "cmap_gamma": cmap_gamma,
                "cmap_range": cmap_range,
                "color_profile": color_profile,
                "representation": representation,
                "custom_colors": custom_colors,
            }
        )
        if self.structure_model is None or self.render_settings == previous:
            return
        geometry_fields = {
            "show_bonds",
            "sphere_scale",
            "bond_radius",
            "show_cell",
            "show_axes_flag",
            "representation",
        }
        if any(previous.get(key) != self.render_settings.get(key) for key in geometry_fields):
            self._schedule_render()
        else:
            self.renderer.update_appearance(
                self.structure_model, self._render_settings()
            )
            self._highlight_actor = self.renderer._highlight_actor

    def render_scene(self):
        if self._is_closing:
            return
        if self.structure_model is None:
            self.renderer.clear()
            return

        if not self._lightkit_enabled:
            self.plotter.enable_lightkit()
            self._lightkit_enabled = True

        settings = self._render_settings()
        self.renderer.render(self.structure_model, settings)
        self._highlight_actor = self.renderer._highlight_actor
        self._restore_ground_grid()

    def _render_settings(self):
        rs = self.render_settings
        sphere_scale = rs["sphere_scale"] / 100.0
        background_opacity = 1.0 - (rs["transparency"] / 100.0) if rs["hide_bg"] else 1.0
        selected_atom_id = self.selected_atom_idx + 1 if self.selected_atom_idx >= 0 else None

        return RenderSettings(
            show_bonds=rs["show_bonds"],
            show_cell=rs.get("show_cell", True),
            show_axes=rs.get("show_axes_flag", True),
            show_labels=rs["show_labels"],
            fade_background=rs["hide_bg"],
            background_opacity=background_opacity,
            sphere_scale=sphere_scale,
            bond_radius=rs.get("bond_radius", 8) / 100.0 * sphere_scale,
            ambient_light=rs["ambient_light"] / 100.0,
            color_by=rs.get("color_by", "Bader 电荷"),
            cmap=rs.get("cmap", "coolwarm"),
            cmap_gamma=rs.get("cmap_gamma", 1.0),
            cmap_range=rs.get("cmap_range", "极值"),
            color_profile=rs.get("color_profile", "标准"),
            representation=rs.get("representation", "ball_stick"),
            selected_atom_id=selected_atom_id,
            visible_atom_ids=self._parse_target_str(rs["target_str"]),
            label_atom_ids=self._parse_target_str(rs.get("label_target_str", "")),
            custom_colors=rs.get("custom_colors"),
        )

    def _schedule_render(self, delay_ms: int | None = None) -> None:
        """Coalesce multiple render requests into one via a short timer.

        Call this instead of ``render_scene()`` from UI event handlers
        (sliders, checkboxes, deselection).  The actual render is deferred
        by *delay_ms* milliseconds; any new call during that window
        resets the clock so only the final state is rendered.
        """
        if self._is_closing:
            return
        ms = delay_ms if delay_ms is not None else self._debounce_ms
        QTimer.singleShot(ms, self._render_scene_if_alive)

    def _render_scene_if_alive(self):
        if not self._is_closing:
            self.render_scene()

    def render_scene_now(self) -> None:
        """Force an immediate render, bypassing debounce.

        Use this when visual feedback must be instantaneous
        (e.g. after loading data or selecting an atom).
        """
        if self._is_closing:
            return
        self.render_scene()

    def _update_selection_highlight(self) -> None:
        """Lightweight highlight-only update — no full scene rebuild.

        Removes the previous yellow wireframe sphere (if any) and adds
        a new one around the currently selected atom.  This avoids the
        flicker caused by ``render_scene_now()`` which clears and
        re-creates *all* geometry on every click.
        """
        # Remove old highlight actor (whether we created it or the
        # renderer did during a full render pass)
        old_actor = self._highlight_actor or getattr(self.renderer, '_highlight_actor', None)
        if old_actor is not None:
            try:
                self.plotter.remove_actor(old_actor)
            except Exception:
                pass
            self._highlight_actor = None
        self.renderer._highlight_actor = None

        if self.selected_atom_idx < 0 or self.structure_model is None:
            self.plotter.update()
            return

        atom_id = self.selected_atom_idx + 1
        try:
            atom = self.structure_model.atom_by_id(atom_id)
        except KeyError:
            self.plotter.update()
            return

        rs = self.render_settings
        sphere_scale = rs["sphere_scale"] / 100.0
        radius = self.renderer._atom_radius(atom, RenderSettings(sphere_scale=sphere_scale))

        import pyvista as pv
        mesh = pv.Sphere(
            radius=radius * 1.12,
            center=atom.cart_coords,
            theta_resolution=32,
            phi_resolution=32,
        )
        self._highlight_actor = self.plotter.add_mesh(
            mesh,
            color=(1.0, 0.9, 0.05),
            opacity=1.0,
            style="wireframe",
            line_width=3,
            ambient=rs["ambient_light"] / 100.0,
            pickable=False,
        )
        self.renderer._highlight_actor = self._highlight_actor
        self.plotter.update()

    def _show_atom_context_menu(self, atom):
        """Show a frosted-glass floating panel with atom info and actions."""
        # Close any previous panel
        if self._glass_panel is not None:
            try:
                self._glass_panel._dismiss()
            except RuntimeError:
                pass  # C++ object already deleted
            self._glass_panel = None

        panel = _AtomInfoGlassPanel(atom, self)
        self._glass_panel = panel
        panel.show_at(QCursor.pos())

    def focus_atom(self):
        if self.selected_atom_idx >= 0 and self.structure_model is not None:
            pos = self.structure_model.atom_by_id(self.selected_atom_idx + 1).cart_coords
            self.plotter.set_focus(pos)
            self.plotter.camera.zoom(1.8)
            self.plotter.update()

    def isolate_atom(self):
        if self.selected_atom_idx >= 0 and self.structure_model is not None:
            self.render_settings["target_str"] = str(self.selected_atom_idx + 1)
            self._is_isolated = True
            self._schedule_render()
            self.focus_atom()

    def clear_selection(self):
        self.selected_atom_idx = -1
        self._is_isolated = False
        self.render_settings["target_str"] = ""
        self._schedule_render()

    def reset_camera(self):
        if self.structure_model is not None:
            self.plotter.reset_camera()
            self.plotter.view_isometric()
            self.plotter.camera.SetParallelProjection(False)

    def toggle_projection(self):
        is_parallel = self.plotter.camera.GetParallelProjection()
        self.plotter.camera.SetParallelProjection(not is_parallel)
        self.plotter.update()

    def apply_theme(self, is_dark):
        if self._is_closing:
            return
        self.is_dark_theme = is_dark
        self.plotter.set_background("#1E1E1E" if is_dark else "#FFFFFF")
        self._schedule_render()

    def export_model(self, filepath):
        self.renderer.export_model(filepath)

    def _compute_coordination(self, atom_idx):
        if self.structure_model is None:
            return "无"

        atom_id = atom_idx + 1
        return sum(
            1
            for bond in self.structure_model.bonds
            if bond.atom_i == atom_id or bond.atom_j == atom_id
        )

    def _safe_view(self, view_func):
        if self.structure_model is not None:
            view_func()
            self.plotter.update()

    def _restore_ground_grid(self):
        # Disabled: show_grid() produces a large bounding-box coordinate grid
        # that obscures the structure. The small corner orientation axes
        # (add_axes, controlled by RenderSettings.show_axes) are sufficient.
        self._ground_actor = None

    def _parse_target_str(self, target_str):
        if not target_str:
            return None
        targets = []
        for part in target_str.replace(" ", "").split(","):
            if "-" in part:
                try:
                    start, end = map(int, part.split("-"))
                    targets.extend(range(start, end + 1))
                except ValueError:
                    pass
            else:
                try:
                    targets.append(int(part))
                except ValueError:
                    pass
        return set(targets)

    def cleanup(self):
        """Release VTK/OpenGL resources before Qt destroys native window handles."""
        if self._is_closing:
            return
        self._is_closing = True

        if self._glass_panel is not None:
            try:
                self._glass_panel._dismiss()
            except Exception:
                pass
            self._glass_panel = None

        if self._event_filter is not None:
            try:
                self.plotter.interactor.removeEventFilter(self._event_filter)
            except Exception:
                pass
            self._event_filter = None

        try:
            self.renderer.clear()
        except Exception:
            pass

        try:
            self.plotter.close()
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)


class MultiVisualizer3DPanel(QWidget):
    """Grid container that hosts one Visualizer3D per selected workspace."""

    atom_selected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = {}
        self.active_workspace = None
        self.maximized_workspace = None
        self._last_settings = None
        self._pending_workspace_loads = []
        self._load_timer_active = False
        self._load_generation = 0
        self._is_closing = False
        self._scene_cache = SceneCache(capacity=6, release=self._release_cached_tile)

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(6)

    @property
    def plotter(self):
        active = self._active_visualizer()
        return active.plotter if active is not None else None

    def set_workspaces_data(self, data_by_workspace, selected_names=None):
        if self._is_closing:
            return
        selected_names = list(selected_names or data_by_workspace.keys())
        keep = set(selected_names)
        self._pending_workspace_loads = []
        self._load_timer_active = False
        self._load_generation += 1

        # Tiles whose progressive geometry load never ran are not cache
        # entries and must not accumulate when selection changes quickly.
        for name, tile in list(self.tiles.items()):
            if name not in keep and tile.get("geometry_key") is None:
                self.tiles.pop(name, None)
                self._cleanup_tile(tile)
                tile["frame"].setParent(None)
                tile["frame"].deleteLater()
        self._scene_cache.set_visible(keep)
        if self.maximized_workspace not in keep:
            self.maximized_workspace = None

        for name in selected_names:
            data = data_by_workspace.get(name) or {}
            geometry_key = self._geometry_key(name, data)
            if name in self.tiles and self.tiles[name].get("geometry_key") != geometry_key:
                self._scene_cache.invalidate_workspace(name)
            if name not in self.tiles:
                self.tiles[name] = self._create_tile(name)
            tile = self.tiles[name]
            tile["data"] = data
            appearance_key = self._appearance_key(data)
            if tile.get("geometry_key") != geometry_key:
                self._pending_workspace_loads.append(
                    (name, data, geometry_key, appearance_key)
                )
            elif tile.get("appearance_key") != appearance_key:
                self._update_tile_appearance(name, data, appearance_key)

        if selected_names:
            self.active_workspace = self.active_workspace if self.active_workspace in keep else selected_names[0]
        else:
            self.active_workspace = None
        self._rebuild_grid(selected_names)
        self._start_progressive_loading()

    def load_data(self, struct, df):
        name = self.active_workspace or "\u5f53\u524d\u5de5\u4f5c\u533a"
        self.set_workspaces_data({name: {"struct": struct, "df": df}}, [name])

    def _create_tile(self, workspace):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 2, 0)
        title = QLabel(workspace)
        title.setStyleSheet("font-weight: bold;")
        btn_max = QPushButton()
        btn_max.setIcon(qta.icon("fa5s.expand-alt", color="#555"))
        btn_max.setFixedSize(26, 24)
        btn_max.clicked.connect(lambda checked=False, ws=workspace: self.toggle_maximize(ws))
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(btn_max)

        visualizer = Visualizer3D()
        visualizer.atom_selected.connect(
            lambda data, ws=workspace: self._emit_atom_selected(ws, data)
        )
        layout.addWidget(header)
        layout.addWidget(visualizer, 1)
        return {
            "frame": frame,
            "visualizer": visualizer,
            "button": btn_max,
            "geometry_key": None,
            "appearance_key": None,
            "data": None,
        }

    def _geometry_key(self, workspace, data):
        struct = data.get("struct")
        df = data.get("df")
        atom_count = data.get("atom_count")
        if atom_count is None:
            try:
                atom_count = len(struct)
            except TypeError:
                try:
                    atom_count = len(df) if df is not None else 0
                except TypeError:
                    atom_count = 0
        elements = data.get("element_sequence")
        if elements is None and df is not None and hasattr(df, "columns") and "Element" in df.columns:
            elements = tuple(df.sort_values("Atom")["Element"].astype(str))
        if elements is None:
            try:
                elements = tuple(site.specie.symbol for site in struct)
            except (TypeError, AttributeError):
                elements = ()
        fingerprint = data.get("structure_fingerprint") or data.get("structure_revision")
        if not fingerprint:
            fingerprint = f"memory:{id(struct)}"
        return GeometryKey(workspace, str(fingerprint), int(atom_count), tuple(elements))

    def _appearance_key(self, data):
        settings = data.get("render_settings", self._last_settings or {})
        frozen_settings = tuple(
            sorted((str(key), repr(value)) for key, value in dict(settings).items())
        )
        return AppearanceKey(
            int(data.get("analysis_revision", 0)),
            tuple(int(value) for value in data.get("selected_atom_ids", ())),
            str(data.get("source_revision", "")),
            str(data.get("charge_revision", data.get("source_revision", ""))),
            frozen_settings,
        )

    def _start_progressive_loading(self):
        if not self._pending_workspace_loads:
            return

        priority = self.active_workspace
        if priority:
            self._pending_workspace_loads.sort(
                key=lambda item: 0 if item[0] == priority else 1
            )

        self._load_next_pending_workspace(self._load_generation)

    def _load_next_pending_workspace(self, generation=None):
        if self._is_closing:
            return
        if generation is not None and generation != self._load_generation:
            return
        if not self._pending_workspace_loads:
            self._load_timer_active = False
            return

        name, data, geometry_key, appearance_key = self._pending_workspace_loads.pop(0)
        tile = self.tiles.get(name)
        if tile is not None and tile.get("geometry_key") != geometry_key:
            selected_ids = appearance_key.selected_atom_ids
            if hasattr(tile["visualizer"], "set_analysis_selection"):
                tile["visualizer"].set_analysis_selection(selected_ids)
            tile["visualizer"].load_data(data.get("struct"), data.get("df"))
            tile["geometry_key"] = geometry_key
            tile["appearance_key"] = appearance_key
            self._scene_cache.remember_geometry(geometry_key, tile)
            self._scene_cache.remember_appearance(name, appearance_key)
            if self._last_settings:
                self._apply_settings_to(tile["visualizer"], self._last_settings)

        if self._pending_workspace_loads:
            self._load_timer_active = True
            active_generation = self._load_generation
            QTimer.singleShot(80, lambda: self._load_next_pending_workspace(active_generation))
        else:
            self._load_timer_active = False

    def update_workspace_appearances(self, data_by_workspace, names=None):
        """Apply committed scope/charge revisions to existing scenes only."""
        complete = True
        for name in list(names or data_by_workspace):
            tile = self.tiles.get(name)
            data = data_by_workspace.get(name) or {}
            if tile is None or tile.get("geometry_key") != self._geometry_key(name, data):
                complete = False
                continue
            appearance_key = self._appearance_key(data)
            if tile.get("appearance_key") != appearance_key:
                tile["data"] = data
                self._update_tile_appearance(name, data, appearance_key)
        return complete

    def invalidate_workspace(self, workspace):
        self._scene_cache.invalidate_workspace(workspace)
        if self.active_workspace == workspace:
            self.active_workspace = None
        if self.maximized_workspace == workspace:
            self.maximized_workspace = None

    def _update_tile_appearance(self, name, data, appearance_key):
        tile = self.tiles[name]
        tile["visualizer"].update_appearance(
            data.get("df"), appearance_key.selected_atom_ids
        )
        tile["appearance_key"] = appearance_key
        self._scene_cache.remember_appearance(name, appearance_key)

    def _emit_atom_selected(self, workspace, data):
        self.active_workspace = workspace
        if data:
            data = dict(data)
            data["workspace"] = workspace
        self.atom_selected.emit(data)

    def _rebuild_grid(self, names):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        visible = [name for name in names if not self.maximized_workspace or name == self.maximized_workspace]
        count = max(len(visible), 1)
        cols = 1 if count == 1 else 2 if count <= 4 else 3
        for idx, name in enumerate(visible):
            tile = self.tiles[name]
            row, col = divmod(idx, cols)
            tile["button"].setIcon(
                qta.icon("fa5s.compress-alt" if self.maximized_workspace == name else "fa5s.expand-alt", color="#555")
            )
            self.grid.addWidget(tile["frame"], row, col)

    def toggle_maximize(self, workspace):
        self.maximized_workspace = None if self.maximized_workspace == workspace else workspace
        self._rebuild_grid(list(self.tiles.keys()))

    def _active_visualizer(self):
        if self.active_workspace in self.tiles:
            return self.tiles[self.active_workspace]["visualizer"]
        if self.tiles:
            first = next(iter(self.tiles))
            self.active_workspace = first
            return self.tiles[first]["visualizer"]
        return None

    def set_render_state(self, **settings):
        if self._is_closing:
            return
        self._last_settings = dict(settings)
        for tile in self.tiles.values():
            self._apply_settings_to(tile["visualizer"], settings)

    def _apply_settings_to(self, visualizer, settings):
        if self._is_closing:
            return
        visualizer.set_render_state(**settings)

    def focus_atom(self):
        active = self._active_visualizer()
        if active is not None:
            active.focus_atom()

    def isolate_atom(self):
        active = self._active_visualizer()
        if active is not None:
            active.isolate_atom()

    def clear_selection(self):
        if self._is_closing:
            return
        for tile in self.tiles.values():
            tile["visualizer"].clear_selection()

    def export_model(self, filepath):
        active = self._active_visualizer()
        if active is None:
            raise ValueError("No active 3D workspace.")
        active.export_model(filepath)

    def apply_theme(self, is_dark):
        if self._is_closing:
            return
        for tile in self.tiles.values():
            tile["visualizer"].apply_theme(is_dark)

    def _cleanup_tile(self, tile):
        visualizer = tile.get("visualizer") if tile else None
        if visualizer is None:
            return
        try:
            if hasattr(visualizer, "cleanup"):
                visualizer.cleanup()
            else:
                visualizer.close()
        except Exception:
            pass

    def _release_cached_tile(self, tile):
        for name, current in list(self.tiles.items()):
            if current is tile:
                self.tiles.pop(name, None)
                break
        self._cleanup_tile(tile)
        frame = tile.get("frame") if tile else None
        if frame is not None:
            frame.setParent(None)
            frame.deleteLater()

    def cleanup(self):
        """Stop pending 3D work and close child VTK render windows explicitly."""
        if self._is_closing:
            return
        self._is_closing = True
        self._load_generation += 1
        self._pending_workspace_loads = []
        self._load_timer_active = False
        for name in list(self.tiles):
            self._scene_cache.invalidate_workspace(name)
        for tile in list(self.tiles.values()):
            self._release_cached_tile(tile)
        self.tiles.clear()
        self.active_workspace = None
        self.maximized_workspace = None

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
