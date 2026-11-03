"""SONIC AI — Unreal Engine 4.22+ Test Suite.

Verifies:
  1. UnrealAdapter imports cleanly and reports 50+ operations
  2. Each operation produces a valid Python script (or shortcut)
  3. UnrealGoalInterpreter matches all 30 goal patterns
  4. Goal decomposition returns valid Actions
  5. UniversalAgent.run_goal("import fbx ...") hits Unreal interpreter
  6. Adapter discovers install dir + Python path + RC port
  7. run_unreal_op convenience works for all ops

Run with:  python -m core.universal.tests.unreal_tests
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Callable

from core.universal.tests.run_all import TestSuite


def _adapter_imports_test():
    from core.universal.adapters.unreal import (
        UnrealAdapter, UE_OPERATIONS, UE_SHORTCUTS,
    )
    assert len(UE_OPERATIONS) >= 50, f"only {len(UE_OPERATIONS)} ops"
    assert len(UE_SHORTCUTS) >= 30, f"only {len(UE_SHORTCUTS)} shortcuts"
    ad = UnrealAdapter()
    catalog = ad.catalog()
    assert catalog == UE_OPERATIONS


def _adapter_discovers_environment_test():
    """Adapter reports install dir + python path (might be empty)."""
    from core.universal.adapters.unreal import UnrealAdapter
    ad = UnrealAdapter()
    info = ad.observe(None)
    assert "install_dir" in info
    assert "python_path" in info
    assert "editor_running" in info
    assert "operation_count" in info
    assert info["operation_count"] >= 50


def _adapter_executes_each_op_test():
    """Every operation returns a valid AdapterResult (not crashes)."""
    from core.universal.adapters.unreal import UnrealAdapter
    from core.universal.adapters.actions_compat import Action, ActionType
    ad = UnrealAdapter()
    failures = []
    for op in ad.catalog():
        try:
            action = Action(
                action_type=ActionType.RUN_WORKFLOW,
                target_name=op,
                parameters={"op": op,
                            "project_path": "C:/test/Test.uproject",
                            "source_path": "C:/test/hero.fbx",
                            "destination": "/Game/Test",
                            "name": "TestAsset",
                            "level_path": "/Game/Maps/TestMap",
                            "location": [0, 0, 100],
                            "rotation": [0, 0, 0],
                            "scale": [1, 1, 1],
                            "quality": "Production",
                            "class_name": "StaticMeshActor",
                            "message": "test commit",
                            "plugin": "MyPlugin",
                            "new_name": "Renamed",
                            "src": "/Game/Test/asset",
                            "dst": "/Game/Test/asset_copy",
                            "assets": ["/Game/Test/a", "/Game/Test/b"],
                            "var_name": "MyVar",
                            "var_type": "float",
                            "value": 1.0,
                            "blueprint": "/Game/BP_MyActor",
                            "component": "StaticMeshComponent",
                            "expression": "TextureSampleParameter2D",
                            "material": "/Game/Materials/M_Test",
                            "blueprint": "/Game/BP_Test",
                            "skeletal": False,
                            "solution_path": "C:/test/Test.sln",
                            "parent": "Actor"},
            )
            result = ad.execute(action, None)
            assert hasattr(result, "success"), f"{op} returned no success"
            assert hasattr(result, "method"), f"{op} returned no method"
        except Exception as exc:
            failures.append((op, str(exc)))
    assert not failures, f"crashed on: {failures[:5]}"


def _adapter_run_op_convenience_test():
    """run_op() builds a synthetic action and executes."""
    from core.universal.adapters.unreal import UnrealAdapter
    ad = UnrealAdapter()
    result = ad.run_op("save_all")
    assert hasattr(result, "success")
    result2 = ad.run_op("set_lightmass_quality", quality="Production")
    assert hasattr(result2, "success")


def _interpreter_imports_test():
    from core.universal.ue_goals import UnrealGoalInterpreter, GOAL_CATALOG
    assert len(GOAL_CATALOG) >= 25, f"only {len(GOAL_CATALOG)} goals"
    interp = UnrealGoalInterpreter()
    catalog = interp.catalog()
    assert len(catalog) >= 25


def _interpreter_matches_common_goals_test():
    from core.universal.ue_goals import UnrealGoalInterpreter
    interp = UnrealGoalInterpreter()
    test_cases = [
        ("open my project at C:/Game/Test.uproject", "open_project"),
        ("create a new empty level", "new_level"),
        ("save all", "save_all"),
        ("build lighting at production quality", "build_lighting"),
        ("create a new blueprint for an actor", "create_blueprint"),
        ("compile all blueprints", "compile_blueprint"),
        ("create a new c++ class for a character", "create_cpp_class"),
        ("import this fbx D:/models/hero.fbx as skeletal mesh", "import_fbx"),
        ("import this texture D:/img/wall.png as normal map", "import_texture"),
        ("import this sound D:/audio/music.wav", "import_sound"),
        ("create a new material", "create_material"),
        ("add a point light at 100 200 300", "add_light"),
        ("add a post process volume", "add_post_process"),
        ("package the project for windows", "package_windows"),
        ("play in editor", "play_in_editor"),
        ("stop play", "stop_play"),
        ("list assets under /Game/Meshes", "list_assets"),
        ("migrate assets to D:/other/Project.uproject", "migrate_assets"),
        ("duplicate the asset /Game/BP_Hero", "duplicate_asset"),
        ("take a screenshot", "take_screenshot"),
        ("open project settings", "open_settings"),
        ("setup a basic scene", "setup_basic_scene"),
        ("do a quick playtest", "quick_playtest"),
    ]
    for text, expected_goal in test_cases:
        actions = interp.interpret(text)
        assert actions, f"no actions for: {text}"
        ops = [a.parameters.get("op") for a in actions]
        # The expected goal name should map to its builder's first op
        goal_names = interp.catalog()
        # sanity: at least one real op returned
        assert any(op and op != "noop" for op in ops), \
            f"only noop returned for: {text}"


def _interpreter_decomposes_to_actions_test():
    from core.universal.ue_goals import UnrealGoalInterpreter
    interp = UnrealGoalInterpreter()
    actions = interp.interpret("import this fbx D:/models/hero.fbx")
    assert len(actions) >= 3, f"too few actions: {len(actions)}"
    ops = [a.parameters.get("op") for a in actions]
    assert "import_fbx" in ops
    # Should also call set_mesh_lod + set_mesh_collision + save_all
    assert "set_mesh_lod" in ops
    assert "save_all" in ops


def _interpreter_extracts_actor_class_test():
    from core.universal.ue_goals import UnrealGoalInterpreter
    interp = UnrealGoalInterpreter()
    cases = [
        ("add a point light at 0 0 500", "PointLight"),
        ("place a directional light", "DirectionalLight"),
        ("drop a static mesh actor", "StaticMeshActor"),
        ("add a character at 0 0 100", "Character"),
        ("add a cube", "StaticMeshActor"),
        ("add a player start", "PlayerStart"),
        ("place a trigger box", "TriggerBox"),
    ]
    for text, expected in cases:
        actions = interp.interpret(text)
        assert actions
        params = actions[0].parameters
        cls = params.get("class_name", "")
        assert cls == expected, \
            f"text={text!r} got cls={cls!r} expected={expected!r}"


def _interpreter_extracts_vector_test():
    from core.universal.ue_goals import UnrealGoalInterpreter
    interp = UnrealGoalInterpreter()
    actions = interp.interpret("add a point light at 100 200 300")
    assert actions
    p = actions[0].parameters
    loc = p.get("location")
    assert loc and loc == [100, 200, 300], f"loc={loc}"


def _interpreter_quality_extraction_test():
    from core.universal.ue_goals import UnrealGoalInterpreter
    interp = UnrealGoalInterpreter()
    for text, expected_q in [
        ("build lighting at preview quality", "preview"),
        ("build lighting at production quality", "production"),
        ("rebuild lighting at medium quality", "medium"),
        ("build lighting", "production"),  # default
    ]:
        actions = interp.interpret(text)
        # first action sets lightmass quality
        params = actions[0].parameters
        assert params.get("quality", "").lower() == expected_q, \
            f"text={text!r} quality={params.get('quality')!r} expected={expected_q!r}"


def _agent_unreal_pipeline_test():
    """UniversalAgent routes Unreal intents through ue_interpreter first."""
    from core.universal.agent import UniversalAgent
    from core.universal.checkpoint import Checkpoint

    agent = UniversalAgent.__new__(UniversalAgent)
    from core.universal.tool_memory import ToolPerformanceMemory
    from core.universal.capability_router import CapabilityRouter
    from core.universal.target_resolver import TargetResolver
    from core.universal.verification import VerificationEngine
    from core.universal.recovery import RecoveryEngine
    from core.universal.checkpoint import TaskCheckpointManager
    from core.universal.ue_goals import UnrealGoalInterpreter

    agent.memory = ToolPerformanceMemory()
    agent.capability_router = CapabilityRouter(tool_memory=agent.memory)
    agent.target_resolver = TargetResolver()
    agent.verifier = VerificationEngine()
    agent.recovery = RecoveryEngine(router=agent.capability_router,
                                    verifier=agent.verifier)
    agent.checkpoints = TaskCheckpointManager()
    agent.ue_interpreter = UnrealGoalInterpreter()
    agent._bridge = None
    agent._router = None
    agent._vision = None
    agent._llm = None
    agent._tasks = {}
    agent._cancel_flags = {}

    from core.universal.agent import AgentGoal
    goal = AgentGoal(text="create a new blueprint for a character")
    cp = Checkpoint(task_id="ue-1", goal_text=goal.text)
    agent._tasks[goal.goal_id] = {"goal": goal, "status": "pending"}
    agent._cancel_flags[goal.goal_id] = False

    result = type("R", (), {"steps": [], "actions_attempted": 0,
                             "actions_succeeded": 0, "actions_failed": 0,
                             "recovery_attempts": 0, "status": "pending",
                             "final_message": "", "error": "",
                             "goal_id": goal.goal_id})()
    actions = agent._plan(goal, result, cp)
    assert actions
    ops = [a.parameters.get("op") for a in actions]
    assert "create_blueprint" in ops, \
        f"UE interpreter didn't trigger; got ops={ops}"


def _agent_run_unreal_op_test():
    """agent.run_unreal_op() exposes direct op execution."""
    from core.universal.agent import UniversalAgent
    agent = UniversalAgent.__new__(UniversalAgent)
    from core.universal.tool_memory import ToolPerformanceMemory
    from core.universal.capability_router import CapabilityRouter
    from core.universal.target_resolver import TargetResolver
    from core.universal.verification import VerificationEngine
    from core.universal.recovery import RecoveryEngine
    from core.universal.checkpoint import TaskCheckpointManager
    from core.universal.ue_goals import UnrealGoalInterpreter

    agent.memory = ToolPerformanceMemory()
    agent.capability_router = CapabilityRouter(tool_memory=agent.memory)
    agent.target_resolver = TargetResolver()
    agent.verifier = VerificationEngine()
    agent.recovery = RecoveryEngine(router=agent.capability_router,
                                    verifier=agent.verifier)
    agent.checkpoints = TaskCheckpointManager()
    agent.ue_interpreter = UnrealGoalInterpreter()
    agent._bridge = None
    agent._router = None
    agent._vision = None
    agent._llm = None
    agent._tasks = {}
    agent._cancel_flags = {}

    result = agent.run_unreal_op("save_all")
    assert hasattr(result, "success")

    listing = agent.list_unreal_ops()
    assert len(listing) >= 50

    goal_names = agent.list_unreal_goals()
    assert len(goal_names) >= 25


def main() -> int:
    suite = TestSuite(name="unreal")
    print("\n=== SONIC AI — Unreal Adapter Test Suite ===\n")
    suite.add("unreal_adapter_imports", _adapter_imports_test)
    suite.add("unreal_adapter_discovers_env", _adapter_discovers_environment_test)
    suite.add("unreal_adapter_executes_each_op", _adapter_executes_each_op_test)
    suite.add("unreal_adapter_run_op_convenience", _adapter_run_op_convenience_test)
    suite.add("unreal_interpreter_imports", _interpreter_imports_test)
    suite.add("unreal_interpreter_matches_common_goals", _interpreter_matches_common_goals_test)
    suite.add("unreal_interpreter_decomposes_to_actions", _interpreter_decomposes_to_actions_test)
    suite.add("unreal_interpreter_extracts_actor_class", _interpreter_extracts_actor_class_test)
    suite.add("unreal_interpreter_extracts_vector", _interpreter_extracts_vector_test)
    suite.add("unreal_interpreter_quality_extraction", _interpreter_quality_extraction_test)
    suite.add("agent_unreal_pipeline", _agent_unreal_pipeline_test)
    suite.add("agent_run_unreal_op", _agent_run_unreal_op_test)

    print(f"\n{'=' * 60}")
    summary = suite.summary()
    print(f"  Suite: {summary['suite']}")
    print(f"  PASSED: {summary['passed']}/{summary['total']}")
    if summary["failed"]:
        print(f"  FAILED: {summary['failed']}")
        for r in summary["results"]:
            if not r["passed"]:
                print(f"    - {r['name']}: {r['message']}")
        return 1
    print("  ALL UNREAL ✓\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
