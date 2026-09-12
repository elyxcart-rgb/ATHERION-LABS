"""SONIC AI — Update UI Components

UpdatePopup: Shows available update info with Update Now / Later buttons
DownloadProgressDialog: Shows download progress, verification, install trigger
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QProgressBar, QTextEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

if TYPE_CHECKING:
    from updater import UpdateManifest

logger = logging.getLogger("UPDATER")


# ═════════════════════════════════════════════════════════════════════════════
# Styles
# ═════════════════════════════════════════════════════════════════════════════

_BG = "#0a0d12"
_CARD = "#111820"
_BORDER = "#1e2a38"
_CYAN = "#00d4ff"
_TEXT = "#c8cdd4"
_DIM = "#6b7a8d"
_BTN_UPDATE = "background-color: #00d4ff; color: #000000; border: none; border-radius: 8px; padding: 12px 24px; font-weight: bold;"
_BTN_UPDATE_HOVER = "background-color: #00b8e0;"
_BTN_LATER = f"background-color: {_CARD}; color: {_DIM}; border: 1px solid {_BORDER}; border-radius: 8px; padding: 12px 24px;"
_BTN_LATER_HOVER = f"background-color: {_BORDER}; color: {_TEXT};"
_BTN_RETRY = f"background-color: {_CARD}; color: {_CYAN}; border: 1px solid {_CYAN}; border-radius: 8px; padding: 12px 24px;"


# ═════════════════════════════════════════════════════════════════════════════
# Download Worker Thread
# ═════════════════════════════════════════════════════════════════════════════

class _DownloadWorker(QThread):
    """Background download with progress signals."""
    progress = pyqtSignal(float, str)  # percent, message
    completed = pyqtSignal(str)  # file path
    failed = pyqtSignal(str)  # error message

    def __init__(self, manifest: "UpdateManifest"):
        super().__init__()
        self.manifest = manifest

    def run(self):
        from updater import get_update_manager
        manager = get_update_manager()

        def _on_progress(pct, msg):
            self.progress.emit(pct, msg)

        path = manager.download_update(self.manifest, progress_cb=_on_progress)
        if path:
            self.completed.emit(str(path))
        else:
            self.failed.emit("Download failed after multiple attempts")


# ═════════════════════════════════════════════════════════════════════════════
# Update Popup
# ═════════════════════════════════════════════════════════════════════════════

class UpdatePopup(QDialog):
    """Shows update available with version info and action buttons."""

    def __init__(self, manifest: "UpdateManifest", parent: QWidget = None):
        super().__init__(parent)
        self.manifest = manifest
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("SONIC AI — Update")
        self.setFixedSize(460, 400)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(f"QDialog {{ background-color: {_BG}; }}")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(28, 20, 28, 20)

        # SONIC branding
        brand = QLabel("SONIC AI")
        brand.setStyleSheet(f"color: {_CYAN}; font-size: 11px; font-weight: bold; letter-spacing: 4px; background: transparent; border: none;")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        # Divider
        div = QLabel()
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {_BORDER}; border: none;")
        layout.addWidget(div)

        # Title
        if self.manifest.mandatory:
            title = QLabel("UPDATE REQUIRED")
            title.setStyleSheet(f"color: #ff4444; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        else:
            title = QLabel("New Version Available")
            title.setStyleSheet(f"color: {_TEXT}; font-size: 18px; font-weight: bold; background: transparent; border: none;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Version info with arrow
        from version import APP_VERSION
        ver_layout = QHBoxLayout()
        ver_layout.setSpacing(8)
        ver_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        old_ver = QLabel(f"v{APP_VERSION}")
        old_ver.setStyleSheet(f"color: {_DIM}; font-size: 13px; background: transparent; border: none;")

        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {_CYAN}; font-size: 16px; font-weight: bold; background: transparent; border: none;")

        new_ver = QLabel(f"v{self.manifest.version}")
        new_ver.setStyleSheet(f"color: {_CYAN}; font-size: 13px; font-weight: bold; background: transparent; border: none;")

        ver_layout.addWidget(old_ver)
        ver_layout.addWidget(arrow)
        ver_layout.addWidget(new_ver)
        layout.addLayout(ver_layout)

        # Release notes
        if self.manifest.release_notes:
            notes_label = QLabel("What's New:")
            notes_label.setStyleSheet(f"color: {_DIM}; font-size: 10px; background: transparent; border: none;")
            layout.addWidget(notes_label)

            notes = QTextEdit()
            notes.setPlainText(self.manifest.release_notes[:1500])
            notes.setReadOnly(True)
            notes.setMaximumHeight(100)
            notes.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {_CARD};
                    color: {_DIM};
                    border: 1px solid {_BORDER};
                    border-radius: 8px;
                    padding: 10px;
                    font-size: 10px;
                }}
            """)
            layout.addWidget(notes)

        layout.addSpacing(4)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        update_btn = QPushButton("⬇  Download & Install")
        update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        update_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_CYAN};
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 14px 28px;
                font-weight: bold;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #00b8e0;
            }}
            QPushButton:pressed {{
                background-color: #009cc0;
            }}
        """)
        update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(update_btn)

        if not self.manifest.mandatory:
            later_btn = QPushButton("Later")
            later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            later_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {_CARD};
                    color: {_DIM};
                    border: 1px solid {_BORDER};
                    border-radius: 8px;
                    padding: 14px 24px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {_BORDER};
                    color: {_TEXT};
                }}
            """)
            later_btn.clicked.connect(self._on_later)
            btn_layout.addWidget(later_btn)

        layout.addLayout(btn_layout)

        layout.addLayout(btn_layout)

        # View release notes link
        if self.manifest.release_page_url:
            link = QLabel(f'<a href="{self.manifest.release_page_url}" style="color: {_DIM};">View release page</a>')
            link.setOpenExternalLinks(True)
            link.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(link)

    def _on_update(self):
        self.accept()
        # Open download progress dialog
        dlg = DownloadProgressDialog(self.manifest, parent=self.parentWidget())
        dlg.exec()

    def _on_later(self):
        self.reject()

    def closeEvent(self, event):
        self.reject()
        event.accept()


# ═════════════════════════════════════════════════════════════════════════════
# Download Progress Dialog
# ═════════════════════════════════════════════════════════════════════════════

class DownloadProgressDialog(QDialog):
    """Shows download progress, verification, and install button."""

    def __init__(self, manifest: "UpdateManifest", parent: QWidget = None):
        super().__init__(parent)
        self.manifest = manifest
        self.worker = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle("SONIC AI — Updating")
        self.setFixedSize(440, 240)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(f"QDialog {{ background-color: {_BG}; }}")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(28, 24, 28, 24)

        # SONIC branding
        brand = QLabel("SONIC AI")
        brand.setStyleSheet(f"color: {_CYAN}; font-size: 10px; font-weight: bold; letter-spacing: 4px; background: transparent; border: none;")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        # Status
        self.status_label = QLabel(f"Downloading v{self.manifest.version}...")
        self.status_label.setStyleSheet(f"color: {_TEXT}; font-size: 14px; font-weight: bold; background: transparent; border: none;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                text-align: center;
                color: {_TEXT};
                font-size: 10px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0099cc, stop:1 #00d4ff);
                border-radius: 7px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        # Detail label
        self.detail_label = QLabel("Preparing...")
        self.detail_label.setStyleSheet(f"color: {_DIM}; font-size: 11px; background: transparent; border: none;")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail_label)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_CARD};
                color: {_DIM};
                border: 1px solid {_BORDER};
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: {_BORDER};
                color: {_TEXT};
            }}
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        self.retry_btn = QPushButton("⟳  Retry")
        self.retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_CARD};
                color: {_CYAN};
                border: 1px solid {_CYAN};
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #0a1a2a;
            }}
        """)
        self.retry_btn.clicked.connect(self._on_retry)
        self.retry_btn.setVisible(False)
        btn_layout.addWidget(self.retry_btn)

        self.install_btn = QPushButton("✓  Install Now")
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #00cc44;
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 12px 28px;
                font-weight: bold;
                font-size: 11px;
            }}
            QPushButton:hover {{
                background-color: #00b83c;
            }}
        """)
        self.install_btn.clicked.connect(self._on_install)
        self.install_btn.setVisible(False)
        btn_layout.addWidget(self.install_btn)

        layout.addLayout(btn_layout)

    def showEvent(self, event):
        super().showEvent(event)
        self._start_download()

    def _start_download(self):
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Downloading v{self.manifest.version}...")
        self.detail_label.setText("Starting download...")
        self.cancel_btn.setVisible(True)
        self.retry_btn.setVisible(False)
        self.install_btn.setVisible(False)

        self.worker = _DownloadWorker(self.manifest)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_progress(self, pct: float, msg: str):
        self.progress_bar.setValue(int(pct))
        self.detail_label.setText(msg)

    def _on_completed(self, path: str):
        self.status_label.setText("Verifying download...")
        self.detail_label.setText("SHA-256 check...")
        self.progress_bar.setValue(100)

        from updater import get_update_manager
        manager = get_update_manager()

        if manager.verify_artifact(
            __import__("pathlib").Path(path),
            self.manifest.sha256,
        ):
            self.status_label.setText("Ready to install")
            self.detail_label.setText(f"New version v{self.manifest.version} verified")
            self.cancel_btn.setVisible(False)
            self.install_btn.setVisible(True)
            self._install_path = path
        else:
            self.status_label.setText("Verification failed")
            self.detail_label.setText("Hash mismatch — download may be corrupted")
            self.cancel_btn.setVisible(False)
            self.retry_btn.setVisible(True)

    def _on_failed(self, error: str):
        self.status_label.setText("Download failed")
        self.detail_label.setText(error)
        self.cancel_btn.setVisible(False)
        self.retry_btn.setVisible(True)

    def _on_install(self):
        from updater import get_update_manager
        manager = get_update_manager()
        self.status_label.setText("Installing...")
        self.detail_label.setText("Launching updater — SONIC will restart")
        self.install_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)

        # Install in background thread so UI doesn't freeze
        def _do_install():
            manager.install_update(
                __import__("pathlib").Path(self._install_path),
                self.manifest,
            )

        threading.Thread(target=_do_install, daemon=True).start()

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        self.reject()

    def _on_retry(self):
        self._start_download()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
        event.accept()
