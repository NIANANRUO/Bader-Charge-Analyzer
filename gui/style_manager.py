import qdarktheme

def get_app_stylesheet(is_dark=False):
    theme = "dark" if is_dark else "light"
    
    # Custom colors to match the modern mockup
    custom_colors = {
        "[light]": {
            "primary": "#198754", # Modern green accent
            "background": "#F8F9FA",
            "border": "#E0E0E0",
        },
        "[dark]": {
            "primary": "#20c997",
            "background": "#121212",
            "border": "#333333",
        }
    }
    
    # Load base stylesheet from qdarktheme
    base_style = qdarktheme.load_stylesheet(theme)
    
    # Global font setting to sans-serif
    font_family = "Microsoft YaHei, Arial, sans-serif"
    
    # Custom tweaks on top of qdarktheme
    custom_css = f"""
    QWidget {{
        font-family: {font_family};
    }}
    
    /* Top Header Bar */
    QWidget#HeaderBar {{
        background-color: {"#FFFFFF" if not is_dark else "#1E1E1E"};
        border-bottom: 1px solid {"#E0E0E0" if not is_dark else "#333333"};
    }}
    
    /* Top Navigation Tabs */
    QTabBar#NavTabs::tab {{
        padding: 15px 20px;
        background: transparent;
        border: none;
        border-bottom: 3px solid transparent;
        font-weight: bold;
        color: {"#666666" if not is_dark else "#AAAAAA"};
    }}
    QTabBar#NavTabs::tab:selected {{
        color: {"#198754" if not is_dark else "#20c997"};
        border-bottom: 3px solid {"#198754" if not is_dark else "#20c997"};
    }}
    QTabBar#NavTabs::tab:hover {{
        background: {"#F0F0F0" if not is_dark else "#2A2A2A"};
    }}
    QTabWidget::pane#NavPane {{
        border: none;
    }}
    
    /* Left Sidebar */
    QWidget#LeftSidebar {{
        background-color: {"#FFFFFF" if not is_dark else "#1E1E1E"};
        border-right: 1px solid {"#E0E0E0" if not is_dark else "#333333"};
    }}
    QWidget#LeftSidebar QLabel {{
        color: {"#333333" if not is_dark else "#E6E6E6"};
    }}
    QWidget#LeftSidebar QTreeWidget,
    QWidget#LeftSidebar QListWidget {{
        background-color: transparent;
        color: {"#333333" if not is_dark else "#E6E6E6"};
        border: none;
    }}
    QWidget#LeftSidebar QTreeWidget::item:selected,
    QWidget#LeftSidebar QListWidget::item:selected {{
        background-color: {"#DDEBFF" if not is_dark else "#284A63"};
        color: {"#1F2933" if not is_dark else "#FFFFFF"};
    }}
    
    /* Right Sidebar */
    QWidget#RightSidebar {{
        background-color: {"#FFFFFF" if not is_dark else "#1E1E1E"};
        border-left: 1px solid {"#E0E0E0" if not is_dark else "#333333"};
    }}
    QWidget#RightSidebar QLabel {{
        color: {"#333333" if not is_dark else "#E6E6E6"};
    }}
    QTableWidget, QTableView {{
        background-color: {"#FFFFFF" if not is_dark else "#181818"};
        alternate-background-color: {"#F7F9FA" if not is_dark else "#202020"};
        color: {"#222222" if not is_dark else "#E6E6E6"};
        gridline-color: {"#E0E0E0" if not is_dark else "#333333"};
    }}
    QHeaderView::section {{
        background-color: {"#F8F9FA" if not is_dark else "#252525"};
        color: {"#333333" if not is_dark else "#E6E6E6"};
        border: 1px solid {"#E0E0E0" if not is_dark else "#333333"};
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {"#FFFFFF" if not is_dark else "#242424"};
        color: {"#222222" if not is_dark else "#E6E6E6"};
        border: 1px solid {"#D8DEE4" if not is_dark else "#3A3A3A"};
        border-radius: 4px;
        padding: 4px 6px;
    }}
    
    /* Toolbar / Settings Bar above Canvas */
    QWidget#ContentToolbar {{
        background-color: {"#FFFFFF" if not is_dark else "#1E1E1E"};
        border-bottom: 1px solid {"#E0E0E0" if not is_dark else "#333333"};
    }}
    
    /* Collapsible GroupBox Styling */
    QGroupBox.CollapsiblePanel {{
        border: 1px solid {"#E0E0E0" if not is_dark else "#333333"};
        border-radius: 6px;
        margin-top: 15px;
        padding-top: 25px;
        background-color: {"#FFFFFF" if not is_dark else "#1E1E1E"};
    }}
    QGroupBox.CollapsiblePanel::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 5px 10px;
        background-color: transparent;
        font-weight: bold;
    }}
    
    /* Primary Button */
    QPushButton#PrimaryButton {{
        background-color: {"#198754" if not is_dark else "#20c997"};
        color: {"#FFFFFF" if not is_dark else "#000000"};
        font-weight: bold;
        border-radius: 4px;
        padding: 8px 15px;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {"#157347" if not is_dark else "#1ab385"};
    }}
    QPushButton#PrimaryButton:disabled {{
        background-color: {"#A0A0A0" if not is_dark else "#555555"};
    }}
    """
    return base_style + custom_css
