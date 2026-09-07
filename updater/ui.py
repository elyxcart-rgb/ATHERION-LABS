"""SONIC AI — Update Popup UI.

Polished PyQt6 notification for available updates.
Shows: version info, release notes, progress bar, download status.
"""
from __future__ import annotations

import logging
import sys
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QProgressBar, QTextEdit, QFrame,
)

from version import APP_VERSION, APP_NAME
from updater import UpdateManager, UpdateManifest, UpdateState, get_update_manager

logger = logging.getLogger("UPDATER")


class _DownloadThread(QThread):
    """Background thread for download + verify + install."""
    progress = pyqtSignal(float, int, int)   # percent, downloaded, total
    finished = pyqtSignal(bool, str)         # success, message

    def __init__(self, manager: UpdateManager, manifest: UpdateManifest) -> None:
        super().__init__()
        self._manager = manager
        self._manifest = manifest

    def run(self) -> None:
        def on_progress(p):
            self.progress.emit(p.percent, p.downloaded_bytes, p.total_bytes)

        self._manager.register_callback(on_progress)
        try:
            # Download
            zip_path = self._manager.download_update(self._manifest)
            if not zip_path:
                self.finished.emit(False, "Download failed")
                return

            # Verify
            if not self._manager.verify_integrity(zip_path, self._manifest.sha256):
                self.finished.emit(False, "Integrity check failed")
                return

            # Backup
            backup = self._manager.create_backup()
            if not backup:
                self.finished.emit(False, "Backup failed")
                return

            # Install
            if not self._manager.install_update(zip_path, backup):
                self.finished.emit(False, "Failed to install update")
                return

            self.finished.emit(True, "Update installed. Restarting...")
        except Exception as e:
            logger.error("[UPDATER] Update thread error: %s", e)
            self.finished.emit(False, str(e))
        finally:
            self._manager.unregister_callback(on_progress)


class UpdatePopup(QDialog):
    """Modal update notification dialog."""

    def __init__(self, manifest: UpdateManifest, parent=None) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self._manager = get_update_manager()
        self._thread: _DownloadThread | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle(f"{APP_NAME} Update Available")
        self.setFixedSize(480, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog { background: #0d1117; }
            QLabel { color: #c9d1d9; }
            QPushButton { border-radius: 6px; padding: 8px 20px; font-weight: bold; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)

        # Header
        header = QLabel(f"{APP_NAME} UPDATE AVAILABLE")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.setStyleSheet("color: #00d4ff;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # Version info
        ver_layout = QHBoxLayout()
        cur_lbl = QLabel(f"Current: v{APP_VERSION}")
        cur_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
        new_lbl = QLabel(f"New: v{self.manifest.version}")
        new_lbl.setStyleSheet("color: #3fb950; font-size: 11px; font-weight: bold;")
        ver_layout.addStretch()
        ver_layout.addWidget(cur_lbl)
        ver_layout.addSpacing(20)
        ver_layout.addWidget(new_lbl)
        ver_layout.addStretch()
        layout.addLayout(ver_layout)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #21262d;")
        layout.addWidget(sep)

        # Title
        if self.manifest.title:
            title = QLabel(self.manifest.title)
            title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            title.setStyleSheet("color: #f0f6fc;")
            layout.addWidget(title)

        # Summary / Release notes
        notes = self.manifest.summary or self.manifest.release_notes
        if notes:
            notes_box = QTextEdit()
            notes_box.setPlainText(notes)
            notes_box.setReadOnly(True)
            notes_box.setMaximumHeight(140)
            notes_box.setStyleSheet("""
                QTextEdit {
                    background: #161b22;
                    color: #8b949e;
                    border: 1px solid #21262d;
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 11px;
                }
            """)
            layout.addWidget(notes_box)

        # Release notes link
        if self.manifest.release_notes_url:
            link = QLabel(f'<a href="{self.manifest.release_notes_url}" style="color:#58a6ff;">View full release notes</a>')
            link.setOpenExternalLinks(True)
            link.setStyleSheet("font-size: 10px;")
            layout.addWidget(link)

        # Progress section (hidden initially)
        self._progress_frame = QFrame()
        p_layout = QVBoxLayout(self._progress_frame)
        p_layout.setContentsMargins(0, 0, 0, 0)

        self._progress_label = QLabel("Preparing download...")
        self._progress_label.setStyleSheet("color: #c9d1d9; font-size: 11px;")
        p_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedHeight(20)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background: #161b22;
                border: 1px solid #21262d;
                border-radius: 6px;
                text-align: center;
                color: #c9d1d9;
                font-size: 10px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d4ff, stop:1 #0099cc);
                border-radius: 5px;
            }
        """)
        p_layout.addWidget(self._progress_bar)

        self._progress_detail = QLabel("")
        self._progress_detail.setStyleSheet("color: #8b949e; font-size: 10px;")
        p_layout.addWidget(self._progress_detail)

        self._progress_frame.hide()
        layout.addWidget(self._progress_frame)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._later_btn = QPushButton("Later")
        self._later_btn.setStyleSheet("""
            QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
            QPushButton:hover { background: #30363d; }
        """)
        self._later_btn.clicked.connect(self._on_later)
        btn_layout.addWidget(self._later_btn)

        self._update_btn = QPushButton("Update Now")
        self._update_btn.setStyleSheet("""
            QPushButton { background: #238636; color: #ffffff; border: none; }
            QPushButton:hover { background: #2ea043; }
            QPushButton:disabled { background: #21262d; color: #484f58; }
        """)
        self._update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(self._update_btn)

        layout.addLayout(btn_layout)

        # Mandatory update — disable "Later"
        if self.manifest.mandatory:
            self._later_btn.setEnabled(False)
            self._later_btn.setToolTip("This is a critical security update")
            header.setText(f"{APP_NAME} CRITICAL UPDATE REQUIRED")
            header.setStyleSheet("color: #f85149;")

    def _on_later(self) -> None:
        self.reject()

    def _on_update(self) -> None:
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Updating...")
        self._later_btn.setEnabled(False)
        self._progress_frame.show()

        self._thread = _DownloadThread(self._manager, self.manifest)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, percent: float, downloaded: int, total: int) -> None:
        self._progress_bar.setValue(int(percent))
        if total > 0:
            dl_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            self._progress_detail.setText(f"{dl_mb:.1f} MB / {total_mb:.1f} MB")
        if percent < 30:
            self._progress_label.setText("Downloading update...")
        elif percent < 60:
            self._progress_label.setText("Verifying integrity...")
        elif percent < 90:
            self._progress_label.setText("Creating backup...")
        else:
            self._progress_label.setText("Installing update...")

    def _on_finished(self, success: bool, message: str) -> None:
        if success:
            self._progress_label.setText("Update installed! Restarting...")
            self._progress_bar.setValue(100)
            self._progress_detail.setText("SONIC will restart in a moment...")
            # Close popup and let app handle restart
            QTimer.singleShot(1500, self._do_restart)
        else:
            self._progress_label.setText(f"Error: {message}")
            self._update_btn.setEnabled(True)
            self._update_btn.setText("Retry")
            self._later_btn.setEnabled(True)

    def _do_restart(self) -> None:
        """Accept the dialog and signal the main app to exit."""
        self.accept()
        # The main app should detect the update was installed and exit
        app = QApplication.instance()
        if app:
            app.quit()


class UpdateNotification(QFrame):
    """Inline notification banner (non-modal) for the main window."""

    def __init__(self, manifest: UpdateManifest, parent=None) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet("""
            QFrame {
                background: #161b22;
                border: 1px solid #00d4ff;
                border-radius: 8px;
                padding: 10px;
            }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        text = QLabel(
            f'<span style="color:#00d4ff; font-weight:bold;">Update Available</span> '
            f'<span style="color:#8b949e;"> — v{self.manifest.version}</span>'
        )
        text.setStyleSheet("background: transparent;")
        layout.addWidget(text)

        layout.addStretch()

        update_btn = QPushButton("Update")
        update_btn.setStyleSheet("""
            QPushButton { background: #238636; color: white; border: none;
                          border-radius: 4px; padding: 4px 12px; font-size: 11px; }
            QPushButton:hover { background: #2ea043; }
        """)
        update_btn.clicked.connect(self._on_update)
        layout.addWidget(update_btn)

        dismiss_btn = QPushButton("x")
        dismiss_btn.setFixedSize(24, 24)
        dismiss_btn.setStyleSheet("""
            QPushButton { background: transparent; color: #484f58; border: none;
                          font-size: 14px; }
            QPushButton:hover { color: #f85149; }
        """)
        dismiss_btn.clicked.connect(self.hide)
        layout.addWidget(dismiss_btn)

    def _on_update(self) -> None:
        popup = UpdatePopup(self.manifest, parent=self.window())
        popup.exec()
