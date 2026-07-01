from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                               QLabel, QFrame)
from PySide6.QtCore import Qt, QSize
import qtawesome as qta

class CollapsiblePanel(QFrame):
    def __init__(self, title="", is_expanded=True, parent=None):
        super().__init__(parent)
        self.is_expanded = is_expanded
        
        self.setObjectName("CollapsiblePanel")
        
        # --- Header ---
        self.header_widget = QWidget()
        self.header_widget.setCursor(Qt.PointingHandCursor)
        self.header_widget.mousePressEvent = self.toggle_panel
        self.header_widget.setObjectName("CollapsibleHeader")
        
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(15, 12, 15, 12)
        
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.btn_toggle = QPushButton()
        self.btn_toggle.setFlat(True)
        self.btn_toggle.setIconSize(QSize(16, 16))
        self.btn_toggle.setStyleSheet("background: transparent; border: none;")
        self.btn_toggle.clicked.connect(self.toggle_panel)
        
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_toggle)
        
        # --- Content ---
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(15, 0, 15, 15)
        self.content_layout.setSpacing(10)
        
        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        main_layout.addWidget(self.header_widget)
        main_layout.addWidget(self.content_area)
        
        self._update_ui()
        
    def toggle_panel(self, event=None):
        self.is_expanded = not self.is_expanded
        self._update_ui()
        
    def _update_ui(self):
        if self.is_expanded:
            self.btn_toggle.setIcon(qta.icon('fa5s.chevron-up', color="#666666"))
            self.content_area.setVisible(True)
        else:
            self.btn_toggle.setIcon(qta.icon('fa5s.chevron-down', color="#666666"))
            self.content_area.setVisible(False)

    def set_expanded(self, expanded: bool):
        """Programmatically expand or collapse the panel."""
        self.is_expanded = expanded
        self._update_ui()

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)
        
    def addLayout(self, layout):
        self.content_layout.addLayout(layout)
