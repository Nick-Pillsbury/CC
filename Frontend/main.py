import sys
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage

class StreamWebPage(QWebEnginePage):
    def certificateError(self, certificateError):
        return True

class StreamOverlayApp(QMainWindow):
    def __init__(self, stream_url: str):
        super().__init__()
        self.setWindowTitle("Video Stream Overlay")
        self.resize(1024, 600)

        self.web_view = QWebEngineView()
        self.web_page = StreamWebPage(self.web_view)
        self.web_view.setPage(self.web_page)
        self.web_view.setUrl(QUrl(stream_url))
        self.setCentralWidget(self.web_view)

if __name__ == "__main__":
    sys.argv.append("--ignore-certificate-errors")
    sys.argv.append("--allow-running-insecure-content")

    app = QApplication(sys.argv)
    STREAM_URL = "https://10.0.0.51:8889/stream/"
    window = StreamOverlayApp(stream_url=STREAM_URL)
    window.show()
    sys.exit(app.exec())