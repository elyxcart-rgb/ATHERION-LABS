"""SONIC AI — Voice Biometric.

JARVIS-style speaker identification and emotion detection from voice features.

Public API:
    VoiceBiometric()
    .enroll(name, audio_features)         # teach SONIC who's who
    .identify(audio_features)             # who's speaking? -> name or "unknown"
    .detect_emotion(audio_features)       # neutral|happy|sad|angry|calm
    .list_users() -> list[str]
    .get_stats() -> dict

Uses lightweight acoustic features (pitch + energy + spectral centroid) so
it works offline without heavy ML models. The trade-off is accuracy — but
for a personal desktop assistant this is plenty.

Voice "fingerprint" features (12 numbers):
    mean pitch, std pitch, pitch range
    mean energy, std energy
    mean spectral centroid, std centroid
    zero-crossing rate mean
    speaking rate proxy (sample variation)
    +4 derived features
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional


def _safe_list(xs):
    return [float(x) for x in xs] if xs else []


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs):
    if not xs:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _voice_features(audio: list[float] | list[int] | bytes) -> list[float]:
    """Extract a 12-dim voice fingerprint from raw audio samples.

    Accepts list of floats (-1..1), list of ints (PCM16), or raw bytes.
    Gracefully returns zero vector on errors.
    """
    try:
        if isinstance(audio, bytes):
            # Decode PCM16
            import array
            audio = array.array('h', audio)
        audio = [float(x) for x in audio]
    except Exception:
        return [0.0] * 12

    if len(audio) < 800:
        return [0.0] * 12

    # Pitch estimation via autocorrelation (very rough)
    def _autocorr_pitch(buf, sample_rate=16000, fmin=80, fmax=400):
        max_lag = sample_rate // fmin
        min_lag = sample_rate // fmax
        best_lag = 0
        best_val = 0.0
        # Normalize
        n = len(buf)
        for lag in range(min_lag, min(max_lag, n // 2)):
            val = 0.0
            for i in range(n - lag):
                val += buf[i] * buf[i + lag]
            if val > best_val:
                best_val = val
                best_lag = lag
        if best_lag == 0:
            return 0.0
        return sample_rate / best_lag

    # Process in 30ms frames (480 samples @ 16kHz)
    frame_size = 480
    hop = 240
    pitches = []
    energies = []
    zcrs = []
    centroids = []

    try:
        import numpy as np  # type: ignore
        arr = np.array(audio, dtype=np.float32)
        # Normalize
        max_val = float(np.max(np.abs(arr)) or 1.0)
        arr = arr / max_val
        for start in range(0, len(arr) - frame_size, hop):
            frame = arr[start:start + frame_size]
            energy = float(np.mean(frame ** 2))
            energies.append(energy)
            # Zero-crossing rate
            zcr = float(np.mean(np.abs(np.diff(np.sign(frame))) > 0))
            zcrs.append(zcr)
            # Simple centroid estimate (energy distribution)
            fft_mag = np.abs(np.fft.rfft(frame))
            freqs = np.fft.rfftfreq(len(frame), d=1.0 / 16000)
            if fft_mag.sum() > 0:
                centroid = float(np.sum(freqs * fft_mag) / np.sum(fft_mag))
                centroids.append(centroid)
            # Pitch (autocorr)
            pitch = _autocorr_pitch(frame)
            if 60 < pitch < 500:
                pitches.append(pitch)
    except ImportError:
        # No numpy — fall back to pure-python (slower but works)
        for start in range(0, len(audio) - frame_size, hop):
            frame = audio[start:start + frame_size]
            energy = _mean([x * x for x in frame])
            energies.append(energy)
            zc = 0
            for i in range(1, len(frame)):
                if (frame[i] >= 0) != (frame[i - 1] >= 0):
                    zc += 1
            zcrs.append(zc / len(frame))
            pitch = _autocorr_pitch(frame)
            if 60 < pitch < 500:
                pitches.append(pitch)
            # Crude centroid
            n = len(frame)
            if n > 1:
                c = sum(i * abs(frame[i]) for i in range(n)) / sum(abs(x) for x in frame)
                centroids.append(c * 100)  # scale to Hz-ish

    return [
        _mean(pitches),       # 0 mean pitch
        _std(pitches),        # 1 pitch variation
        max(pitches) - min(pitches) if pitches else 0.0,  # 2 pitch range
        _mean(energies),      # 3 energy
        _std(energies),       # 4 energy variation
        _mean(centroids),     # 5 spectral centroid
        _std(centroids),      # 6 centroid variation
        _mean(zcrs),          # 7 ZCR
        _std(zcrs),           # 8 ZCR variation
        len(pitches) / max(1, len(energies)),  # 9 voiced fraction
        max(energies) if energies else 0.0,   # 10 peak energy
        _std([abs(x) for x in audio[:8000]]) if audio else 0.0,  # 11 loudness variation
    ]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    """Returns distance in [0, 2]. Lower = more similar."""
    if not a or not b or len(a) != len(b):
        return 2.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1e-9
    nb = math.sqrt(sum(y * y for y in b)) or 1e-9
    sim = dot / (na * nb)
    return max(0.0, 1.0 - sim)


# ── Emotion heuristic ──────────────────────────────────────────────────────
_EMOTION_KEYS = ["calm", "neutral", "happy", "angry", "sad"]


def _detect_emotion(features: list[float]) -> tuple[str, float]:
    """Map voice features to an emotion label + confidence."""
    pitch_mean = features[0]
    pitch_var = features[1]
    energy = features[3]
    energy_var = features[4]
    centroid = features[5]
    zcr = features[7]

    # Heuristics
    if energy > 0.05 and pitch_var > 30:
        return "angry", 0.65
    if energy > 0.04 and centroid > 1000:
        return "happy", 0.6
    if energy < 0.005 and pitch_var < 20:
        return "sad", 0.55
    if energy_var > 0.02 and zcr > 0.05:
        return "neutral", 0.5
    return "calm", 0.5


# ═════════════════════════════════════════════════════════════════════════════
# VoiceBiometric
# ═════════════════════════════════════════════════════════════════════════════

class VoiceBiometric:
    """Speaker identification + emotion from voice features."""

    def __init__(self, db_path: str | Path = "~/.sonic_brain/voiceprints.db"):
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    # ── Public ───────────────────────────────────────────────────────────────

    def enroll(self, name: str, audio, samples_needed: int = 3) -> dict:
        """Enroll a user. Each call adds one voice-print sample."""
        features = _voice_features(audio)
        with self._lock:
            cur = self._conn().execute(
                "INSERT INTO voiceprints (name, features_json, ts) VALUES (?, ?, ?)",
                (name, json.dumps(features), time.time()),
            )
            self._conn().commit()
            count = self._count_for(name)
            return {
                "ok": True,
                "user": name,
                "sample_id": cur.lastrowid,
                "samples_for_user": count,
                "enough_samples": count >= samples_needed,
            }

    def identify(self, audio, threshold: float = 0.4) -> dict:
        """Identify the speaker from a voice sample.

        Returns {"user": "alice"|"unknown", "confidence": 0..1, "scores": {...}}.
        """
        target = _voice_features(audio)
        if all(v == 0 for v in target):
            return {"user": "unknown", "confidence": 0.0, "scores": {}, "reason": "no audio"}

        with self._lock:
            rows = self._conn().execute(
                "SELECT name, features_json FROM voiceprints"
            ).fetchall()
            if not rows:
                return {"user": "unknown", "confidence": 0.0, "scores": {},
                        "reason": "no enrolled users"}

            # Average features per user
            user_features: dict[str, list[list[float]]] = {}
            for name, feat_json in rows:
                feats = json.loads(feat_json)
                user_features.setdefault(name, []).append(feats)

            scores: dict[str, float] = {}
            for name, feat_list in user_features.items():
                # Mean features across samples
                mean_features = [_mean(col) for col in zip(*feat_list)]
                dist = _cosine_distance(target, mean_features)
                scores[name] = max(0.0, 1.0 - dist)

            best_user = max(scores, key=scores.get)
            best_score = scores[best_user]
            if best_score < threshold:
                return {"user": "unknown", "confidence": best_score, "scores": scores,
                        "reason": f"below threshold {threshold}"}
            return {"user": best_user, "confidence": best_score, "scores": scores}

    def detect_emotion(self, audio) -> dict:
        features = _voice_features(audio)
        label, conf = _detect_emotion(features)
        return {"emotion": label, "confidence": conf, "features": features}

    def list_users(self) -> list[str]:
        with self._lock:
            rows = self._conn().execute(
                "SELECT DISTINCT name FROM voiceprints ORDER BY name"
            ).fetchall()
            return [r[0] for r in rows]

    def remove_user(self, name: str) -> int:
        with self._lock:
            cur = self._conn().execute(
                "DELETE FROM voiceprints WHERE name=?", (name,)
            )
            self._conn().commit()
            return cur.rowcount

    def get_stats(self) -> dict:
        with self._lock:
            total = self._conn().execute(
                "SELECT COUNT(*) FROM voiceprints"
            ).fetchone()[0]
            users = self.list_users()
            db_size = self._db_path.stat().st_size if self._db_path.exists() else 0
            return {
                "samples": total,
                "users": users,
                "user_count": len(users),
                "db_size_bytes": db_size,
            }

    # ── Internals ────────────────────────────────────────────────────────────

    def _count_for(self, name: str) -> int:
        return self._conn().execute(
            "SELECT COUNT(*) FROM voiceprints WHERE name=?", (name,)
        ).fetchone()[0]

    def _init_db(self):
        with self._lock:
            self._conn().execute("""
                CREATE TABLE IF NOT EXISTS voiceprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    features_json TEXT NOT NULL,
                    ts REAL NOT NULL
                )
            """)
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_vp_name ON voiceprints(name)"
            )
            self._conn().commit()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self, "_db") or self._db is None:
            self._db = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._db.row_factory = sqlite3.Row
        return self._db
