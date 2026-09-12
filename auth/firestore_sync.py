"""Firestore user data isolation for SONIC AI — cloud sync layer."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try to import Firebase Admin SDK (server-side)
try:
    import firebase_admin
    from firebase_admin import firestore, credentials
    HAS_FIREBASE_ADMIN = True
except ImportError:
    HAS_FIREBASE_ADMIN = False
    firestore = None  # type: ignore


class FirestoreIsolation:
    """Manages per-user Firestore data with strict UID scoping.

    All reads/writes are scoped to users/{uid}/...
    No cross-user access is possible.
    """

    def __init__(self):
        self._db = None
        self._initialized = False

    def initialize(self, credential_path: str = "") -> bool:
        """Initialize Firebase Admin SDK with service account credentials."""
        if not HAS_FIREBASE_ADMIN:
            logger.warning("[Firestore] firebase_admin SDK not installed")
            return False

        if self._initialized:
            return True

        try:
            if credential_path and Path(credential_path).exists():
                cred = credentials.Certificate(credential_path)
                firebase_admin.initialize_app(cred)
            elif not firebase_admin._apps:
                # Try default credentials
                firebase_admin.initialize_app()

            self._db = firestore.client()
            self._initialized = True
            logger.info("[Firestore] Initialized successfully")
            return True
        except Exception as e:
            logger.warning("[Firestore] Init failed: %s", e)
            return False

    @property
    def is_available(self) -> bool:
        return self._initialized and self._db is not None

    # ── Profile ────────────────────────────────────────────────────────

    def save_profile(self, uid: str, profile: dict) -> bool:
        """Save user profile to Firestore under users/{uid}/profile/main."""
        if not self.is_available:
            return False
        try:
            doc_ref = self._db.collection("users").document(uid).collection("profile").document("main")
            doc_ref.set(profile, merge=True)
            return True
        except Exception as e:
            logger.error("[Firestore] Save profile failed: %s", e)
            return False

    def load_profile(self, uid: str) -> dict:
        """Load user profile from Firestore."""
        if not self.is_available:
            return {}
        try:
            doc_ref = self._db.collection("users").document(uid).collection("profile").document("main")
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else {}
        except Exception as e:
            logger.error("[Firestore] Load profile failed: %s", e)
            return {}

    # ── Preferences ────────────────────────────────────────────────────

    def save_preferences(self, uid: str, preferences: dict) -> bool:
        """Save user preferences to Firestore."""
        if not self.is_available:
            return False
        try:
            doc_ref = self._db.collection("users").document(uid).collection("preferences").document("main")
            doc_ref.set(preferences, merge=True)
            return True
        except Exception as e:
            logger.error("[Firestore] Save preferences failed: %s", e)
            return False

    def load_preferences(self, uid: str) -> dict:
        """Load user preferences from Firestore."""
        if not self.is_available:
            return {}
        try:
            doc_ref = self._db.collection("users").document(uid).collection("preferences").document("main")
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else {}
        except Exception as e:
            logger.error("[Firestore] Load preferences failed: %s", e)
            return {}

    # ── Settings ───────────────────────────────────────────────────────

    def save_settings(self, uid: str, settings: dict) -> bool:
        """Save user settings (API keys, voice, etc.) to Firestore."""
        if not self.is_available:
            return False
        try:
            doc_ref = self._db.collection("users").document(uid).collection("settings").document("main")
            doc_ref.set(settings, merge=True)
            return True
        except Exception as e:
            logger.error("[Firestore] Save settings failed: %s", e)
            return False

    def load_settings(self, uid: str) -> dict:
        """Load user settings from Firestore."""
        if not self.is_available:
            return {}
        try:
            doc_ref = self._db.collection("users").document(uid).collection("settings").document("main")
            doc = doc_ref.get()
            return doc.to_dict() if doc.exists else {}
        except Exception as e:
            logger.error("[Firestore] Load settings failed: %s", e)
            return {}

    # ── Memories (batch) ───────────────────────────────────────────────

    def save_memories(self, uid: str, memories: list[dict]) -> bool:
        """Save user memories to Firestore in batch."""
        if not self.is_available:
            return False
        try:
            batch = self._db.batch()
            col = self._db.collection("users").document(uid).collection("memories")
            for mem in memories:
                doc_id = mem.get("memory_id", "")
                if doc_id:
                    batch.set(col.document(doc_id), mem, merge=True)
            batch.commit()
            return True
        except Exception as e:
            logger.error("[Firestore] Save memories failed: %s", e)
            return False

    def load_memories(self, uid: str, limit: int = 100) -> list[dict]:
        """Load user memories from Firestore."""
        if not self.is_available:
            return []
        try:
            col = self._db.collection("users").document(uid).collection("memories")
            docs = col.limit(limit).stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error("[Firestore] Load memories failed: %s", e)
            return []

    # ── Projects ───────────────────────────────────────────────────────

    def save_project(self, uid: str, project: dict) -> bool:
        """Save a project to Firestore."""
        if not self.is_available:
            return False
        try:
            proj_id = project.get("project_id", "")
            if not proj_id:
                return False
            doc_ref = self._db.collection("users").document(uid).collection("projects").document(proj_id)
            doc_ref.set(project, merge=True)
            return True
        except Exception as e:
            logger.error("[Firestore] Save project failed: %s", e)
            return False

    def load_projects(self, uid: str) -> list[dict]:
        """Load all user projects from Firestore."""
        if not self.is_available:
            return []
        try:
            col = self._db.collection("users").document(uid).collection("projects")
            docs = col.stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error("[Firestore] Load projects failed: %s", e)
            return []

    # ── Tasks ──────────────────────────────────────────────────────────

    def save_task(self, uid: str, task: dict) -> bool:
        """Save a task to Firestore."""
        if not self.is_available:
            return False
        try:
            task_id = task.get("task_id", "")
            if not task_id:
                return False
            doc_ref = self._db.collection("users").document(uid).collection("tasks").document(task_id)
            doc_ref.set(task, merge=True)
            return True
        except Exception as e:
            logger.error("[Firestore] Save task failed: %s", e)
            return False

    def load_tasks(self, uid: str, status: str = "") -> list[dict]:
        """Load user tasks from Firestore."""
        if not self.is_available:
            return []
        try:
            col = self._db.collection("users").document(uid).collection("tasks")
            if status:
                col = col.where("status", "==", status)
            docs = col.stream()
            return [doc.to_dict() for doc in docs]
        except Exception as e:
            logger.error("[Firestore] Load tasks failed: %s", e)
            return []

    # ── Utility ────────────────────────────────────────────────────────

    def delete_all_user_data(self, uid: str) -> bool:
        """Delete ALL data for a user. Used for account deletion."""
        if not self.is_available:
            return False
        try:
            user_ref = self._db.collection("users").document(uid)
            # Delete all subcollections
            for subcol_name in ["profile", "preferences", "memories", "projects",
                                "tasks", "sessions", "settings", "experiences", "lessons"]:
                docs = user_ref.collection(subcol_name).stream()
                for doc in docs:
                    doc.reference.delete()
            # Delete the user document itself
            user_ref.delete()
            return True
        except Exception as e:
            logger.error("[Firestore] Delete user data failed: %s", e)
            return False


# Singleton
_firestore = None

def get_firestore() -> FirestoreIsolation:
    global _firestore
    if _firestore is None:
        _firestore = FirestoreIsolation()
    return _firestore
