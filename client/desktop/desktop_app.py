"""
VaultCall Desktop — Application native Windows/Linux/macOS
Encapsule l'interface web dans une fenêtre native via PyQt5 QWebEngineView.

Usage :
    python desktop_app.py [--port 8000]
"""

import argparse
import sys
import threading
import time
import webbrowser

try:
    from PyQt5.QtCore    import QUrl, Qt, QSize
    from PyQt5.QtGui     import QIcon, QColor, QPalette
    from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage

    HAS_PYQT5 = True
except ImportError:
    HAS_PYQT5 = False


def wait_for_server(url: str, timeout: float = 15.0):
    """Attend que le serveur FastAPI soit disponible."""
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


# ── Version PyQt5 (native) ────────────────────────────────────────────────────

class VaultCallWindow(QMainWindow):
    def __init__(self, url: str):
        super().__init__()
        self.setWindowTitle("VaultCall — Communication Chiffrée E2EE")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 760)
        self._set_dark_palette()

        self.browser = QWebEngineView()
        self.browser.load(QUrl(url))
        self.setCentralWidget(self.browser)

        # Titre dynamique depuis la page
        self.browser.titleChanged.connect(
            lambda t: self.setWindowTitle(f"VaultCall — {t}" if t else "VaultCall")
        )

    def _set_dark_palette(self):
        palette = QPalette()
        palette.setColor(QPalette.Window,          QColor("#0d0d12"))
        palette.setColor(QPalette.WindowText,      QColor("#f0f0f8"))
        palette.setColor(QPalette.Base,            QColor("#13131a"))
        palette.setColor(QPalette.AlternateBase,   QColor("#1a1a24"))
        palette.setColor(QPalette.Button,          QColor("#7c3aed"))
        palette.setColor(QPalette.ButtonText,      QColor("#ffffff"))
        self.setPalette(palette)


def run_pyqt(url: str):
    app = QApplication(sys.argv)
    app.setApplicationName("VaultCall")
    app.setOrganizationName("USTHB")

    splash = QLabel("⏳ Démarrage de VaultCall…")
    splash.setAlignment(Qt.AlignCenter)
    splash.setStyleSheet("background:#0d0d12; color:#a78bfa; font-size:18px; padding:40px;")
    splash.resize(400, 200)
    splash.setWindowFlags(Qt.FramelessWindowHint)
    splash.show()

    def _launch():
        ok = wait_for_server(url)
        if not ok:
            print("[VaultCall Desktop] Serveur non joignable.")
        splash.close()
        window = VaultCallWindow(url)
        window.show()

    threading.Thread(target=_launch, daemon=True).start()
    sys.exit(app.exec_())


# ── Fallback : ouvrir dans le navigateur par défaut ──────────────────────────

def run_browser_fallback(url: str):
    print(f"PyQt5/QWebEngine non disponible — ouverture dans le navigateur : {url}")
    ok = wait_for_server(url, timeout=20)
    if ok:
        webbrowser.open(url)
    else:
        print("Le serveur n'a pas démarré à temps. Lancez-le manuellement puis ouvrez :", url)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VaultCall Desktop")
    parser.add_argument("--port", type=int, default=8000, help="Port du serveur FastAPI")
    parser.add_argument("--browser", action="store_true", help="Forcer l'ouverture navigateur")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"

    if HAS_PYQT5 and not args.browser:
        run_pyqt(url)
    else:
        run_browser_fallback(url)


if __name__ == "__main__":
    main()
