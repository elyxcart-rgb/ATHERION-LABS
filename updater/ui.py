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
    QPushButton, QWidget, QTextEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

if TYPE_CHECKING:
    from updater import UpdateManifest

logger = logging.getLogger("UPDATER")


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
        from apple_design import (
            Tokens, AppleButton, AppleCard, AppleProgressBar,
            create_shadow, fade_in,
        )

        self.setWindowTitle("SONIC Apex — Update")
        self.setFixedSize(460, 420)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Tokens.BG_PRIMARY};
                border: 1px solid {Tokens.BORDER_LIGHT};
                border-radius: {Tokens.R_XL}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(Tokens.XXL, Tokens.XXL, Tokens.XXL, Tokens.XL)

        # ── Title ─────────────────────────────────────────────────────────
        if self.manifest.mandatory:
            title = QLabel("UPDATE REQUIRED")
            title.setStyleSheet(f"""
                color: {Tokens.ERROR};
                font-size: 18px;
                font-weight: 700;
                letter-spacing: 1px;
                background: transparent;
                border: none;
            """)
        else:
            title = QLabel("New Version Available")
            title.setStyleSheet(f"""
                color: {Tokens.TEXT_PRIMARY};
                font-size: 18px;
                font-weight: 700;
                background: transparent;
                border: none;
            """)
        title.setFont(Tokens.font(18, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(Tokens.XL)

        # ── Version Info Card ─────────────────────────────────────────────
        from version import APP_VERSION

        ver_card = QWidget()
        ver_card.setStyleSheet(f"""
            QWidget {{
                background: {Tokens.BG_ELEVATED};
                border: 1px solid {Tokens.BORDER};
                border-radius: {Tokens.R_MD}px;
            }}
        """)
        ver_card_layout = QHBoxLayout(ver_card)
        ver_card_layout.setContentsMargins(Tokens.XL, Tokens.LG, Tokens.XL, Tokens.LG)
        ver_card_layout.setSpacing(Tokens.SM)
        ver_card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        old_ver = QLabel(f"v{APP_VERSION}")
        old_ver.setFont(Tokens.font(13, QFont.Weight.Medium))
        old_ver.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent; border: none;")

        arrow = QLabel("  →  ")
        arrow.setFont(Tokens.font(14, QFont.Weight.Bold))
        arrow.setStyleSheet(f"color: {Tokens.CYAN}; background: transparent; border: none;")

        new_ver = QLabel(f"v{self.manifest.version}")
        new_ver.setFont(Tokens.font(13, QFont.Weight.Bold))
        new_ver.setStyleSheet(f"color: {Tokens.CYAN}; background: transparent; border: none;")

        ver_card_layout.addWidget(old_ver)
        ver_card_layout.addWidget(arrow)
        ver_card_layout.addWidget(new_ver)

        layout.addWidget(ver_card)

        layout.addSpacing(Tokens.XL)

        # ── Release Notes Card ────────────────────────────────────────────
        if self.manifest.release_notes:
            notes_header = QLabel("What's New")
            notes_header.setFont(Tokens.font(11, QFont.Weight.SemiBold))
            notes_header.setStyleSheet(f"""
                color: {Tokens.TEXT_SECONDARY};
                letter-spacing: 1px;
                background: transparent;
                border: none;
            """)
            layout.addWidget(notes_header)

            layout.addSpacing(Tokens.SM)

            notes_card = QWidget()
            notes_card.setStyleSheet(f"""
                QWidget {{
                    background: {Tokens.SURFACE_1};
                    border: 1px solid {Tokens.BORDER};
                    border-radius: {Tokens.R_MD}px;
                }}
            """)
            notes_card_layout = QVBoxLayout(notes_card)
            notes_card_layout.setContentsMargins(Tokens.LG, Tokens.MD, Tokens.LG, Tokens.MD)

            notes = QTextEdit()
            notes.setPlainText(self.manifest.release_notes[:1500])
            notes.setReadOnly(True)
            notes.setMaximumHeight(80)
            notes.setFont(Tokens.font(12))
            notes.setStyleSheet(f"""
                QTextEdit {{
                    background: transparent;
                    color: {Tokens.TEXT_SECONDARY};
                    border: none;
                    padding: 0;
                    font-size: 12px;
                    line-height: 1.5;
                }}
            """)
            notes_card_layout.addWidget(notes)
            layout.addWidget(notes_card)

        layout.addSpacing(Tokens.XL)
        layout.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(Tokens.SM)

        update_btn = AppleButton("Download & Install", style="primary")
        update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(update_btn, 2)

        if not self.manifest.mandatory:
            later_btn = AppleButton("Later", style="secondary")
            later_btn.clicked.connect(self._on_later)
            btn_layout.addWidget(later_btn, 1)

        layout.addLayout(btn_layout)

        layout.addSpacing(Tokens.MD)

        # ── Release Page Link ─────────────────────────────────────────────
        if self.manifest.release_page_url:
            link = QLabel(f'<a href="{self.manifest.release_page_url}" '
                          f'style="color: {Tokens.TEXT_TERTIARY}; '
                          f'text-decoration: none; font-size: 11px;">'
                          f'View release page</a>')
            link.setOpenExternalLinks(True)
            link.setAlignment(Qt.AlignmentFlag.AlignCenter)
            link.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    border: none;
                    padding: 2px;
                }}
            """)
            layout.addWidget(link)

    def _on_update(self):
        self.accept()
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
        from apple_design import Tokens, AppleButton, AppleProgressBar

        self.setWindowTitle("SONIC Apex — Updating")
        self.setFixedSize(440, 260)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Tokens.BG_PRIMARY};
                border: 1px solid {Tokens.BORDER_LIGHT};
                border-radius: {Tokens.R_XL}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(Tokens.XXL, Tokens.XL, Tokens.XXL, Tokens.LG)

        # ── Status ────────────────────────────────────────────────────────
        self.status_label = QLabel(f"Downloading v{self.manifest.version}...")
        self.status_label.setFont(Tokens.font(16, QFont.Weight.SemiBold))
        self.status_label.setStyleSheet(f"""
            color: {Tokens.TEXT_PRIMARY};
            background: transparent;
            border: none;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addSpacing(Tokens.LG)

        # ── Progress Bar ──────────────────────────────────────────────────
        self.progress_bar = AppleProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        layout.addSpacing(Tokens.MD)

        # ── Detail Label ──────────────────────────────────────────────────
        self.detail_label = QLabel("Preparing...")
        self.detail_label.setFont(Tokens.font(12))
        self.detail_label.setStyleSheet(f"""
            color: {Tokens.TEXT_SECONDARY};
            background: transparent;
            border: none;
        """)
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail_label)

        layout.addStretch()

        # ── Buttons ───────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(Tokens.SM)

        self.cancel_btn = AppleButton("Cancel", style="secondary")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        self.retry_btn = AppleButton("Retry", style="ghost")
        self.retry_btn.clicked.connect(self._on_retry)
        self.retry_btn.setVisible(False)
        btn_layout.addWidget(self.retry_btn)

        self.install_btn = AppleButton("Install Now", style="primary")
        self.install_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Tokens.SUCCESS};
                color: #ffffff;
                border: none;
                border-radius: {Tokens.R_MD}px;
                padding: 0 24px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: #3ce068; }}
            QPushButton:pressed {{ background: #28b84c; }}
            QPushButton:disabled {{
                background: {Tokens.SURFACE_2};
                color: {Tokens.TEXT_DISABLED};
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
