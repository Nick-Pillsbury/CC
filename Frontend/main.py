import sys
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QStackedLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

class StreamWebPage(QWebEnginePage):
    def certificateError(self, certificateError):
        # Allow self-signed SSL certificates typical on local LAN HTTPS feeds
        return True

class StreamOverlayApp(QMainWindow):
    def __init__(self, stream_url: str):
        super().__init__()
        self.setWindowTitle("Video Stream Overlay")
        self.resize(1024, 600)

        # Base layout container allowing multiple visual planes to stack
        container = QWidget()
        self.stack_layout = QStackedLayout(container)
        self.stack_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.setCentralWidget(container)

        # Layer 0: Embedded Chromium Web View
        self.web_view = QWebEngineView()
        self.web_page = StreamWebPage(self.web_view)
        self.web_view.setPage(self.web_page)
        self.web_view.setUrl(QUrl(stream_url))
        self.stack_layout.addWidget(self.web_view)

        # Layer 1: Overlay Canvas
        self.overlay_widget = QWidget()
        self.overlay_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.stack_layout.addWidget(self.overlay_widget)

if __name__ == "__main__":
    sys.argv.append("--ignore-certificate-errors")
    sys.argv.append("--allow-running-insecure-content")

    app = QApplication(sys.argv)
    STREAM_URL = "https://10.0.0.51:8889/stream/"
    window = StreamOverlayApp(stream_url=STREAM_URL)
    window.show()
    sys.exit(app.exec())