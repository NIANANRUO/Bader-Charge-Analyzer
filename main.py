import sys
from PySide6.QtWidgets import QApplication

def main():
    app = QApplication(sys.argv)
    
    # Import MainWindow after QApplication is created to avoid qtawesome warnings
    from gui.app_icon import load_app_icon
    from gui.main_window import MainWindow
    app.setWindowIcon(load_app_icon())
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
