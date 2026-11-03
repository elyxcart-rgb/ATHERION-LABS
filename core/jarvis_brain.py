"""SONIC AI — Jarvis Brain (the "J.A.R.V.I.S." itself).

A unified facade that ties together all of SONIC's intelligence modules:

    UniversalRouter    → routes user utterances to actions
    ActionBridge       → executes the routed action against real modules
    ScreenVision       → live screen awareness
    MemoryPalace       → persistent long-term memory
    KnowledgeGraph     → entities + relationships for contextual recall
    ProactiveEngine    → anticipatory suggestions
    NextActionPredictor → next-action prediction
    SelfHeal           → diagnostics + auto-repair
    WorldPulse         → real-time ambient awareness
    VoicePipeline      → full wake-word → speak loop
    CodeSandbox        → safe Python execution
    WorkflowEngine     → DAG-based multi-step automation
    Notifier           → Windows desktop notifications + TTS

Public API:
    brain = JarvisBrain()
    .think(user_input) → routes + executes + speaks + learns
    .ambient_check()   → full environmental snapshot
    .start_proactive_loop()
    .start_voice_loop()
    .run_workflow(steps)
    .say(text)
    .notify(title, message)
    .status()

Everything degrades gracefully — missing subsystems are reported in
status() but don't break the rest.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Callable, Any

from .universal_router import UniversalRouter, Route
from .memory_palace import MemoryPalace, Memory
from .proactive_engine import ProactiveEngine, Suggestion
from .self_heal import SelfHeal, HealthReport


@dataclass
class ThoughtResult:
    route: Route
    response: str
    context_memories: list[Memory] = field(default_factory=list)
    screen_context: dict = field(default_factory=dict)
    suggestions: list[Suggestion] = field(default_factory=list)
    knowledge: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0
    subsystem_status: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "route": self.route.to_dict(),
            "response": self.response,
            "context_memories": [m.to_dict() for m in self.context_memories],
            "screen_context": self.screen_context,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "knowledge": self.knowledge,
            "elapsed_ms": self.elapsed_ms,
            "subsystem_status": self.subsystem_status,
        }


@dataclass
class AmbientSnapshot:
    timestamp: float
    health: Optional[HealthReport] = None
    suggestions: list[Suggestion] = field(default_factory=list)
    screen_focus: str = ""
    screen_app: str = ""
    memory_count: int = 0
    pattern_events: int = 0
    subsystem_status: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "health": self.health.to_dict() if self.health else None,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "screen_focus": self.screen_focus,
            "screen_app": self.screen_app,
            "memory_count": self.memory_count,
            "pattern_events": self.pattern_events,
            "subsystem_status": self.subsystem_status,
        }


class JarvisBrain:
    """The unified J.A.R.V.I.S.-class intelligence core."""

    def __init__(self,
                 db_dir: str | Path = "~/.sonic_brain",
                 llm_client: Optional[Callable[[str], str]] = None,
                 tts_fn: Optional[Callable[[str], None]] = None,
                 action_executor: Optional[Callable[[str, dict], str]] = None,
                 project_root: Optional[Path] = None):
        self._db_dir = Path(db_dir).expanduser()
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._llm = llm_client
        self._tts = tts_fn
        self._executor = action_executor

        # Subsystems — core
        self.router = UniversalRouter(llm_client=llm_client)
        self.memory = MemoryPalace(db_path=self._db_dir / "memory.db")
        self.proactive = ProactiveEngine(db_path=self._db_dir / "patterns.db")
        self.healer = SelfHeal(log_fn=lambda m: None)

        # Subsystems — power
        self.pulse = None
        self.vision = None
        self.sandbox = None
        self.workflow = None
        self.notifier = None
        self.voice = None
        self.knowledge = None
        self.predict = None
        self.bridge = None
        self.universal = None   # UniversalAgent — additive layer (Phase 4)

        try:
            from .world_pulse import WorldPulse
            self.pulse = WorldPulse(cache_dir=self._db_dir)
        except Exception as e:
            self._pulse_err = str(e)

        try:
            from .screen_vision import ScreenVision
            self.vision = ScreenVision(llm_client=llm_client)
        except Exception as e:
            self._vision_err = str(e)

        try:
            from .code_sandbox import CodeSandbox
            self.sandbox = CodeSandbox()
        except Exception as e:
            self._sandbox_err = str(e)

        try:
            from .workflow_engine import WorkflowEngine
            self.workflow = WorkflowEngine()
        except Exception as e:
            self._workflow_err = str(e)

        try:
            from .notify import Notifier
            self.notifier = Notifier()
        except Exception as e:
            self._notify_err = str(e)

        try:
            from .voice_pipeline import VoicePipeline
            self.voice = VoicePipeline(self, tts_fn=self._tts)
        except Exception as e:
            self._voice_err = str(e)

        try:
            from .knowledge_graph import KnowledgeGraph
            self.knowledge = KnowledgeGraph(db_path=self._db_dir / "kg.db")
        except Exception as e:
            self._kg_err = str(e)

        try:
            from .predict import NextActionPredictor
            self.predict = NextActionPredictor(db_path=self._db_dir / "predict.db")
        except Exception as e:
            self._predict_err = str(e)

        # Action bridge (real execution against the 45+ existing actions)
        try:
            from .action_bridge import ActionBridge
            self.bridge = ActionBridge(
                project_root=project_root,
                sandbox=self.sandbox,
                llm_client=llm_client,
                proactive_engine=self.proactive,
            )
            # Default executor: real bridge
            if self._executor is None:
                self._executor = self.bridge.execute
        except Exception as e:
            self._bridge_err = str(e)

        # Universal Agent — additive computer-use orchestrator
        try:
            from .universal import UniversalAgent
            self.universal = UniversalAgent(
                data_dir=self._db_dir,
                bridge=self.bridge,
                router=self.router,
                screen_vision=self.vision,
            )
        except Exception as e:
            self._universal_err = str(e)

        self._pulse_thread: Optional[threading.Thread] = None
        self._pulse_stop = threading.Event()
        self._lock = threading.RLock()

    # ── Public ───────────────────────────────────────────────────────────────

    def think(self, user_input: str, with_screen: bool = False,
              with_memory_recall: bool = True,
              with_knowledge_query: bool = True,
              execute: bool = True) -> ThoughtResult:
        """Process one user input through the full pipeline."""
        t0 = time.time()
        route = self.router.route(user_input)

        # Recall memories
        context_memories: list[Memory] = []
        if with_memory_recall:
            context_memories = self.memory.recall(user_input, top_k=5)

        # Knowledge graph query
        knowledge: dict = {}
        if with_knowledge_query and self.knowledge is not None:
            try:
                qr = self.knowledge.query(user_input)
                knowledge = qr.to_dict()
            except Exception:
                knowledge = {}

        # Screen context (only on demand — expensive)
        screen_ctx: dict = {}
        if with_screen and self.vision is not None:
            try:
                ctx = self.vision.see(with_description=False)
                screen_ctx = {
                    "focused_window": ctx.focused_window,
                    "focused_app": ctx.focused_app,
                    "word_count": ctx.word_count,
                    "summary": ctx.summary(),
                }
            except Exception:
                screen_ctx = {}

        # Suggestions
        suggestions = self.proactive.suggest(
            context={"focused_app": screen_ctx.get("focused_app", "")},
            max_suggestions=3,
        )

        # Execute
        if execute and self._executor is not None:
            try:
                response_text = self._executor(route.action, route.args)
            except Exception as e:
                response_text = f"Execution error: {e}"
        else:
            response_text = self._craft_response(route, context_memories, screen_ctx)

        # Learn from exchange
        try:
            self.memory.add_conversation(user_input, response_text)
            self.proactive.record_event(route.action, context=screen_ctx)
            if self.predict is not None:
                # Encode this action sequence for next-action prediction
                self.predict.record([route.action])
            # Try to learn entities from the input
            if self.knowledge is not None:
                self.knowledge.learn_from_text(user_input)
        except Exception:
            pass

        return ThoughtResult(
            route=route,
            response=response_text,
            context_memories=context_memories,
            screen_context=screen_ctx,
            suggestions=suggestions,
            knowledge=knowledge,
            elapsed_ms=(time.time() - t0) * 1000,
            subsystem_status=self.status(),
        )

    def ambient_check(self) -> AmbientSnapshot:
        """Full environmental snapshot: health, suggestions, screen, memory."""
        with self._lock:
            health = self.healer.full_health_check(auto_repair=True)
            suggestions = self.proactive.suggest(max_suggestions=5)
            screen_focus, screen_app = "", ""
            if self.vision is not None:
                try:
                    ctx = self.vision.see(with_description=False)
                    screen_focus = ctx.focused_window
                    screen_app = ctx.focused_app
                except Exception:
                    pass
            return AmbientSnapshot(
                timestamp=time.time(),
                health=health,
                suggestions=suggestions,
                screen_focus=screen_focus,
                screen_app=screen_app,
                memory_count=self.memory.count(),
                pattern_events=self.proactive.count_events(),
                subsystem_status=self.status(),
            )

    def start_proactive_loop(self, interval_seconds: float = 60.0,
                             on_suggestion: Optional[Callable[[Suggestion], None]] = None):
        self.stop_proactive_loop()
        self._pulse_stop.clear()

        def _loop():
            while not self._pulse_stop.is_set():
                try:
                    ctx = {}
                    if self.vision is not None:
                        try:
                            s = self.vision.see(with_description=False)
                            ctx["focused_app"] = s.focused_app
                        except Exception:
                            pass
                    suggestions = self.proactive.suggest(context=ctx, max_suggestions=3)
                    for s in suggestions:
                        if s.confidence >= 0.5 and on_suggestion is not None:
                            try:
                                on_suggestion(s)
                            except Exception:
                                pass
                except Exception:
                    pass
                self._pulse_stop.wait(interval_seconds)

        self._pulse_thread = threading.Thread(
            target=_loop, name="jarvis-proactive-loop", daemon=True
        )
        self._pulse_thread.start()

    def stop_proactive_loop(self):
        self._pulse_stop.set()
        if self._pulse_thread is not None and self._pulse_thread.is_alive():
            self._pulse_thread.join(timeout=2.0)
        self._pulse_thread = None

    def start_voice_loop(self):
        """Start continuous voice conversation (wake-word → speak loop)."""
        if self.voice is not None:
            self.voice.start()

    def stop_voice_loop(self):
        if self.voice is not None:
            self.voice.stop()

    def run_workflow(self, name: str, steps: list[dict]) -> "WorkflowResult":
        """Run a multi-step automation workflow."""
        if self.workflow is None:
            raise RuntimeError("workflow engine not available")
        if self.bridge is None:
            raise RuntimeError("action bridge not available")
        return self.workflow.run_simple(name, steps, self.bridge.execute)

    def run_python(self, code: str) -> "SandboxResult":
        if self.sandbox is None:
            raise RuntimeError("sandbox not available")
        return self.sandbox.run(code)

    def complete(self, partial: str, n: int = 5) -> list:
        """Autocomplete partial input."""
        if self.predict is None or not hasattr(self.predict, "complete"):
            return []
        return self.predict.complete(partial, n)

    def notify(self, title: str, message: str, urgency: str = "normal") -> Any:
        if self.notifier is None:
            print(f"[NOTIFY] {title}: {message}")
            return None
        return self.notifier.toast(title, message, urgency=urgency)

    def say(self, text: str):
        """Speak via TTS / Notifier / stdout fallback."""
        if self._tts is not None:
            try:
                self._tts(text)
                return
            except Exception:
                pass
        if self.notifier is not None:
            try:
                self.notifier.speak(text)
                return
            except Exception:
                pass
        print(f"[JARVIS] {text}")

    # ── UniversalAgent passthrough ─────────────────────────────────────────
    def run_goal(self, goal_text: str, context: Optional[dict] = None):
        """Run a goal-driven computer-use task via UniversalAgent.

        Pure additive — uses the existing brain subsystems:
          - self.bridge  → real action execution
          - self.router  → natural-language intent parsing
          - self.vision  → screen awareness
          - self.universal.memory → persisted tool performance

        Returns AgentResult.to_dict()
        """
        if self.universal is None:
            return {
                "status": "failed",
                "error": "UniversalAgent unavailable",
                "reason": getattr(self, "_universal_err", "unknown"),
            }
        try:
            result = self.universal.run(goal_text, context=context)
            return result.to_dict()
        except Exception as exc:
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    def cancel_goal(self, goal_id: str) -> bool:
        if self.universal is None:
            return False
        return self.universal.cancel(goal_id)

    def resume_goal(self, goal_id: str):
        if self.universal is None:
            return {"status": "failed", "error": "UniversalAgent unavailable"}
        result = self.universal.resume(goal_id)
        return result.to_dict() if result else None

    def status(self) -> dict:
        with self._lock:
            return {
                "router":     {"available": True, "stats": self.router.get_stats()},
                "memory":     {"available": True, "stats": self.memory.get_stats()},
                "proactive":  {"available": True, "stats": self.proactive.get_stats()},
                "healer":     {"available": True},
                "vision":     {"available": self.vision is not None},
                "pulse":      {"available": self.pulse is not None},
                "sandbox":    {"available": self.sandbox is not None,
                               "stats": self.sandbox.get_stats() if self.sandbox else None},
                "workflow":   {"available": self.workflow is not None,
                               "stats": self.workflow.get_stats() if self.workflow else None},
                "notifier":   {"available": self.notifier is not None,
                               "stats": self.notifier.get_stats() if self.notifier else None},
                "voice":      {"available": self.voice is not None,
                               "stats": self.voice.get_stats() if self.voice else None},
                "knowledge":  {"available": self.knowledge is not None,
                               "stats": self.knowledge.get_stats() if self.knowledge else None},
                "predict":    {"available": self.predict is not None,
                               "stats": self.predict.get_stats() if self.predict else None},
                "bridge":     {"available": self.bridge is not None,
                               "stats": self.bridge.get_stats() if self.bridge else None,
                               "missing_actions": list(self.bridge.get_missing_actions().keys())
                                                    if self.bridge else []},
                "universal":  {"available": self.universal is not None,
                               "stats": self.universal.status() if self.universal else None},
                "llm":        {"available": self._llm is not None},
                "tts":        {"available": self._tts is not None},
                "executor":   {"available": self._executor is not None},
                "timestamp":  time.time(),
            }

    # ── Internals ────────────────────────────────────────────────────────────

    def _craft_response(self, route: Route, memories: list[Memory],
                        screen_ctx: dict) -> str:
        action = route.action
        if action == "ask_ai":
            if self._llm is not None:
                ctx_str = ""
                if memories:
                    ctx_str = "\n\nRelevant things I remember:\n" + "\n".join(
                        f"• {m.text}" for m in memories[:3]
                    )
                prompt = route.args.get("prompt", "")
                try:
                    return self._llm(prompt + ctx_str).strip()
                except Exception as e:
                    return f"AI temporarily unavailable ({e})"
            return "I would answer that, but no AI engine is wired in yet."
        prefix_map = {
            "open_app": "Opening", "close_app": "Closing",
            "switch_window": "Switching to", "web_search": "Searching for",
            "play_youtube": "Playing on YouTube", "set_volume": "Setting volume to",
            "screenshot": "Taking a screenshot", "set_reminder": "I'll remind you",
            "translate": "Translating", "send_email": "Drafting email",
            "send_message": "Sending message", "generate_code": "Generating code",
            "run_python": "Running Python", "research": "Researching",
            "weather": "Checking weather", "lock_computer": "Locking the workstation",
        }
        prefix = prefix_map.get(action, f"Executing {action}")
        if route.args:
            arg_str = ", ".join(f"{k}={v}" for k, v in route.args.items()
                                if k != "target")
            target = route.args.get("target", route.args.get("query", ""))
            return f"{prefix} {target} {arg_str}".strip()
        return prefix

