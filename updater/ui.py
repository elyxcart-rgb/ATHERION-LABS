"""SONIC AI — Update UI Components (Apple-Level).

Two dialogs:
    - UpdatePopup:          shows available update info, "Download & Install" + "Later"
    - DownloadProgressDialog: download progress, verification, install trigger

Both are full QDialog subclasses, use Apple design tokens, and follow the
shared visual language used by bootstrap/ui.py and ui_wizard.py.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QTextEdit, QFrame, QGraphicsDropShadowEffect,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor

if TYPE_CHECKING:
    from updater import UpdateManifest

logger = logging.getLogger("UPDATER")


# ═════════════════════════════════════════════════════════════════════════════
# Download Worker Thread
# ═════════════════════════════════════════════════════════════════════════════

class _DownloadWorker(QThread):
    """Background download with progress signals."""
    progress = pyqtSignal(float, str)  # percent, message
    completed = pyqtSignal(str)        # file path
    failed = pyqtSignal(str)           # error message

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
# Base Dialog Shell — shared frame, shadow, title row
# ═════════════════════════════════════════════════════════════════════════════

class _BaseDialog(QDialog):
    """Shared frame used by both update dialogs — rounded, elevated, draggable."""

    def __init__(self, parent=None, *, title: str = "", subtitle: str = ""):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        from apple_design import Tokens
        self._drag_pos = None

        # Outer layout (transparent — the frame below is the visible body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # The actual visible window
        self._body = QFrame(self)
        self._body.setObjectName("UpdateBody")
        self._body.setStyleSheet(f"""
            QFrame#UpdateBody {{
                background: {Tokens.BG_ELEVATED};
                border: 1px solid {Tokens.BORDER_LIGHT};
                border-radius: {Tokens.R_XL}px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self._body)
        shadow.setBlurRadius(60)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 10)
        self._body.setGraphicsEffect(shadow)
        outer.addWidget(self._body)

        # Inner content layout
        self._content = QVBoxLayout(self._body)
        self._content.setContentsMargins(28, 22, 28, 22)
        self._content.setSpacing(0)

        # Optional title row (icon + title + subtitle)
        if title or subtitle:
            self._content.addLayout(self._build_title_row(title, subtitle))
            self._content.addSpacing(18)

    def _build_title_row(self, title: str, subtitle: str):
        from apple_design import Tokens, _AppleDialogIcon

        row = QHBoxLayout()
        row.setSpacing(14)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Determine icon variant from title text
        tl = title.lower()
        if "required" in tl:
            variant = "error"
        elif "update" in tl:
            variant = "info"
        else:
            variant = "info"
        icon = _AppleDialogIcon(variant, self._body)
        icon.setFixedSize(36, 36)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(Tokens.font(15, QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(
            f"color: {Tokens.TEXT_PRIMARY}; background: transparent;"
        )
        col.addWidget(title_lbl)

        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setFont(Tokens.font(12))
            sub_lbl.setStyleSheet(
                f"color: {Tokens.TEXT_SECONDARY}; background: transparent;"
            )
            col.addWidget(sub_lbl)

        row.addLayout(col, 1)
        return row

    # ── Drag support (only on the title area / body) ──────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


# ═════════════════════════════════════════════════════════════════════════════
# Update Popup
# ═════════════════════════════════════════════════════════════════════════════

class UpdatePopup(_BaseDialog):
    """Shows update available with version info and action buttons."""

    def __init__(self, manifest: "UpdateManifest", parent: QWidget = None):
        super().__init__(parent,
                         title=("Update Required" if manifest.mandatory
                                else "Update Available"),
                         subtitle="A new version of SONIC Apex is ready.")
        self.manifest = manifest
        self.setWindowTitle("SONIC Apex — Update")
        self.setFixedSize(520, 460)
        self._build_content()

    def _build_content(self):
        from apple_design import Tokens, AppleButton
        # ── Version Info Card ─────────────────────────────────────────────
        from version import APP_VERSION

        ver_card = QFrame()
        ver_card.setObjectName("VersionCard")
        ver_card.setStyleSheet(f"""
            QFrame#VersionCard {{
                background: {Tokens.SURFACE_1};
                border: 1px solid {Tokens.BORDER};
                border-radius: {Tokens.R_MD}px;
            }}
        """)
        ver_layout = QHBoxLayout(ver_card)
        ver_layout.setContentsMargins(20, 16, 20, 16)
        ver_layout.setSpacing(12)
        ver_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        old_chip = self._version_chip(f"v{APP_VERSION}", Tokens.TEXT_SECONDARY, ghost=True)
        arrow = QLabel("→")
        arrow.setFont(Tokens.font(16, QFont.Weight.Bold))
        arrow.setStyleSheet(
            f"color: {Tokens.TEXT_TERTIARY}; background: transparent;"
        )
        new_chip = self._version_chip(f"v{self.manifest.version}", Tokens.CYAN, ghost=False)

        ver_layout.addWidget(old_chip)
        ver_layout.addWidget(arrow)
        ver_layout.addWidget(new_chip)

        self._content.addWidget(ver_card)
        self._content.addSpacing(18)

        # ── Release Notes Card ────────────────────────────────────────────
        if self.manifest.release_notes:
            notes_header = QLabel("WHAT'S NEW")
            notes_header.setFont(Tokens.font(10, QFont.Weight.DemiBold))
            notes_header.setStyleSheet(
                f"color: {Tokens.TEXT_TERTIARY}; background: transparent; "
                f"letter-spacing: 1.2px;"
            )
            self._content.addWidget(notes_header)
            self._content.addSpacing(8)

            notes_card = QFrame()
            notes_card.setObjectName("NotesCard")
            notes_card.setStyleSheet(f"""
                QFrame#NotesCard {{
                    background: {Tokens.SURFACE_1};
                    border: 1px solid {Tokens.BORDER};
                    border-radius: {Tokens.R_MD}px;
                }}
            """)
            notes_layout = QVBoxLayout(notes_card)
            notes_layout.setContentsMargins(14, 10, 14, 10)
            notes_layout.setSpacing(0)

            notes = QTextEdit()
            notes.setPlainText(self.manifest.release_notes[:1500])
            notes.setReadOnly(True)
            notes.setFixedHeight(110)
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
                QScrollBar:vertical {{
                    background: {Tokens.SURFACE_2};
                    width: 8px;
                    border-radius: 4px;
                }}
                QScrollBar::handle:vertical {{
                    background: {Tokens.SURFACE_3};
                    border-radius: 4px;
                    min-height: 24px;
                }}
            """)
            notes_layout.addWidget(notes)
            self._content.addWidget(notes_card)
            self._content.addSpacing(18)

        # Spacer
        self._content.addStretch(1)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        update_btn = AppleButton(
            "Install Now" if self.manifest.mandatory else "Download & Install",
            style="primary",
        )
        update_btn.setFixedHeight(40)
        update_btn.clicked.connect(self._on_update)
        btn_layout.addWidget(update_btn, 2)

        if not self.manifest.mandatory:
            later_btn = AppleButton("Later", style="secondary")
            later_btn.setFixedHeight(40)
            later_btn.clicked.connect(self._on_later)
            btn_layout.addWidget(later_btn, 1)

        self._content.addLayout(btn_layout)

        # ── Release Page Link ─────────────────────────────────────────────
        if self.manifest.release_page_url:
            self._content.addSpacing(10)
            link = QLabel(
                f'<a href="{self.manifest.release_page_url}" '
                f'style="color: {Tokens.TEXT_TERTIARY}; '
                f'text-decoration: none; font-size: 11px;">'
                f'View release page →</a>'
            )
            link.setOpenExternalLinks(True)
            link.setAlignment(Qt.AlignmentFlag.AlignCenter)
            link.setStyleSheet(
                f"color: {Tokens.TEXT_TERTIARY}; background: transparent; border: none;"
            )
            self._content.addWidget(link)

    def _version_chip(self, text: str, color: str, ghost: bool) -> QLabel:
        from apple_design import Tokens
        chip = QLabel(text)
        chip.setFont(Tokens.font(13, QFont.Weight.DemiBold))
        if ghost:
            chip.setStyleSheet(
                f"color: {Tokens.TEXT_SECONDARY}; background: {Tokens.SURFACE_2}; "
                f"border: 1px solid {Tokens.BORDER}; border-radius: {Tokens.R_SM}px; "
                f"padding: 6px 14px;"
            )
        else:
            chip.setStyleSheet(
                f"color: {color}; background: {color}1a; "
                f"border: 1px solid {color}55; border-radius: {Tokens.R_SM}px; "
                f"padding: 6px 14px;"
            )
        return chip

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

class DownloadProgressDialog(_BaseDialog):
    """Shows download progress, verification, and install button."""

    def __init__(self, manifest: "UpdateManifest", parent: QWidget = None):
        super().__init__(parent, title="Updating SONIC", subtitle="")
        self.manifest = manifest
        self.worker = None
        self._install_path: str | None = None
        self.setWindowTitle("SONIC Apex — Updating")
        self.setFixedSize(480, 300)
        self._build_content()

    def _build_content(self):
        from apple_design import Tokens, AppleButton, AppleProgressBar

        # ── Status ────────────────────────────────────────────────────────
        self.status_label = QLabel(f"Downloading v{self.manifest.version}…")
        self.status_label.setFont(Tokens.font(16, QFont.Weight.DemiBold))
        self.status_label.setStyleSheet(
            f"color: {Tokens.TEXT_PRIMARY}; background: transparent;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content.addWidget(self.status_label)

        self._content.addSpacing(14)

        # ── Progress Bar ──────────────────────────────────────────────────
        self.progress_bar = AppleProgressBar()
        self.progress_bar.setValue(0)
        self._content.addWidget(self.progress_bar)

        self._content.addSpacing(10)

        # ── Detail Label ──────────────────────────────────────────────────
        self.detail_label = QLabel("Preparing…")
        self.detail_label.setFont(Tokens.font(12))
        self.detail_label.setStyleSheet(
            f"color: {Tokens.TEXT_SECONDARY}; background: transparent;"
        )
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._content.addWidget(self.detail_label)

        self._content.addStretch(1)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.cancel_btn = AppleButton("Cancel", style="secondary")
        self.cancel_btn.setFixedHeight(38)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        self.retry_btn = AppleButton("Retry", style="ghost")
        self.retry_btn.setFixedHeight(38)
        self.retry_btn.clicked.connect(self._on_retry)
        self.retry_btn.setVisible(False)
        btn_layout.addWidget(self.retry_btn)

        self.install_btn = AppleButton("Install Now", style="primary")
        self.install_btn.setFixedHeight(38)
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

        self._content.addLayout(btn_layout)

    def showEvent(self, event):
        super().showEvent(event)
        self._start_download()

    def _start_download(self):
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Downloading v{self.manifest.version}…")
        self.detail_label.setText("Starting download…")
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
        self.status_label.setText("Verifying download…")
        self.detail_label.setText("SHA-256 check…")
        self.progress_bar.setValue(100)

        from updater import get_update_manager
        manager = get_update_manager()

        if manager.verify_artifact(Path(path), self.manifest.sha256):
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
        self.status_label.setText("Installing…")
        self.detail_label.setText("Launching updater — SONIC will restart")
        self.install_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)

        # Install in background thread so UI doesn't freeze
        def _do_install():
            manager.install_update(Path(self._install_path), self.manifest)

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
