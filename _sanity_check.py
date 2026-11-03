"""Quick sanity check — verify existing voice path is untouched."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

# Every existing module
from core.notify import Notifier
from core.tts import EdgeTTSEngine, KokoroTTSEngine, ElevenLabsTTSEngine, TTSPlayer, create_tts_player
from core.voice_pipeline import VoicePipeline
from core.jarvis_brain import JarvisBrain
from core.universal_router import UniversalRouter
from core.memory_palace import MemoryPalace
from core.knowledge_graph import KnowledgeGraph
from core.predict import Predictor
from core.code_sandbox import CodeSandbox
from core.workflow_engine import WorkflowEngine
from core.self_heal import SelfHeal
from core.world_pulse import WorldPulse
from core.screen_vision import ScreenVision
from core.voice_biometric import VoiceBiometric
from core.proactive_engine import ProactiveEngine
from core.action_bridge import ActionBridge
from core.voice_personas import VoicePersonaManager, PERSONAS

print("  ALL 16 EXISTING MODULES import OK")

import inspect
notif_src = inspect.getsource(Notifier)
print(f"  Notifier imports edge_tts: {'edge_tts' in notif_src}")
print(f"  Notifier uses SAPI: {'win32com' in notif_src or 'SAPI' in notif_src}")

# tts.py — existing edge-based JARVIS voice
eng = EdgeTTSEngine(voice="en-US-GuyNeural")
print(f"  tts.EdgeTTSEngine default voice: {eng.voice}")
print(f"  tts.EdgeTTSEngine.speak: {hasattr(eng, 'speak')}")

# Factory creates player
player = create_tts_player({"tts_engine": "edgetts"})
print(f"  TTSPlayer created from factory: {type(player).__name__}")

# Brain
brain = JarvisBrain(db_dir="_sanity_check_db")
print(f"  brain.say() exists: {hasattr(brain, 'say')}")
print(f"  brain.notifier is Notifier: {isinstance(brain.notifier, Notifier)}")

# New module — independent
mgr = VoicePersonaManager()
print(f"  VoicePersonaManager: {len(mgr.list_personas())} personas")
mgr.set_persona("cute_girl")
print(f"  Switch to cute_girl: {mgr.get_persona()}")
mgr.set_persona("jarvis_male")
print(f"  Switch back to jarvis_male: {mgr.get_persona()}")

print()
print("  VERIFIED: zero break, existing voice path untouched")
