import sys
from PyQt6.QtWidgets import QApplication, QMainWindow

class StreamOverlayApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Stream Overlay")
        self.resize(1024, 600)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StreamOverlayApp()
    window.show()
    sys.exit(app.exec())
