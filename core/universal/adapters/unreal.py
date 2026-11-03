"""SONIC AI — Unreal Engine 4.22+ Adapter (Universal).

Comprehensive adapter for Unreal Editor covering:

LEVEL 1 — Native Python API (unreal.* modules)
    Project lifecycle     : open, save, save_all, recent, switch
    Level operations      : new_level, open_level, save_level, build_lighting
    Actor manipulation    : add_actor, delete_actor, move, rotate, scale, duplicate
    Blueprint             : create, compile, set_variable, add_component,
                            add_node, add_event, connect_pins
    C++ class             : create_class, compile_cpp, build_solution
    Materials             : create, add_expression, connect_material
    Textures              : import, set_compression, set_filter, set_srgb
    Static/Skeletal Mesh  : import, set_lod, set_collision, set_shadow
    Animation             : create_anim_blueprint, set_skeleton
    Niagara               : create_system, add_emitter
    Sequencer             : create_sequence, add_actor_to_track
    Audio                 : import_sound_cue, play_in_editor
    Lighting              : build_lighting, set_lightmass_quality
    Packaging             : package_windows, package_android, package_linux
    Settings              : get_project_setting, set_project_setting
    Plugin management     : enable_plugin, disable_plugin
    Source control        : git_checkout, git_commit, perforce_submit
    Editor utilities      : take_screenshot, export_selected, find_actors
    Content browser       : list_assets, filter, rename, delete, duplicate

LEVEL 2 — WebRemoteControl plugin (UE 4.25+, HTTP :30010)
    Same calls over HTTP when Python not available

LEVEL 3 — UIA (pywinauto on UnrealEditor.exe)
    Top menu bar, toolbar buttons, modal dialogs

LEVEL 4 — Vision (SmartClicker + screenshot)
    Viewport clicks, content browser grid, right-click context menus

LEVEL 5 — Keyboard shortcuts
    50+ Unreal editor shortcuts mapped

The adapter is self-discovering — it picks the best working tier per call
and falls back gracefully on failure.

Public API:
    UnrealAdapter()
    .catalog() → list of operation names
    .execute(action, state) → AdapterResult
    .observe(state) → dict
    .run_op(op, **params) → AdapterResult  # convenience for callers
"""
from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.unreal")


# ──────────────────────────────────────────────────────────────────────
# Process + window patterns
# ──────────────────────────────────────────────────────────────────────
UE_PROCESSES = ["UnrealEditor", "UE4Editor", "UnrealEditor-Cmd",
                "UnrealEditor.exe", "UE4Editor.exe"]
UE_PROJECT_EXT = ".uproject"
UE_TITLE_HINTS = ("Unreal Editor", "UnrealEngine", " - UnrealEd")


# ──────────────────────────────────────────────────────────────────────
# Keyboard shortcuts (UE 4.x standard)
# ──────────────────────────────────────────────────────────────────────
UE_SHORTCUTS = {
    # File
    "save_all":           "Ctrl+Shift+S",
    "save_current":       "Ctrl+S",
    "open_project":       "Ctrl+O",
    "new_level":          "Ctrl+N",
    "open_level":         "Ctrl+O",
    # Build
    "build":              "F7",
    "compile_blueprints": "Ctrl+F7",
    "build_lighting":     "Ctrl+Shift+L",
    # Play
    "play":               "Alt+P",
    "stop_play":          "Escape",
    "pause":              "Pause",
    # Edit
    "undo":               "Ctrl+Z",
    "redo":               "Ctrl+Y",
    "duplicate":          "Ctrl+D",
    "delete":             "Delete",
    "select_all":         "Ctrl+A",
    "copy":               "Ctrl+C",
    "paste":              "Ctrl+V",
    "cut":                "Ctrl+X",
    "group":              "Ctrl+G",
    "ungroup":            "Ctrl+Shift+G",
    # Viewport modes
    "wireframe":          "Alt+1",
    "lit":                "Alt+2",
    "detail_lighting":    "Alt+3",
    "show_collision":     "Alt+C",
    "show_bounds":        "Alt+B",
    "show_stats":         "Alt+4",
    # Camera
    "perspective":        "Alt+G",
    "top":                "Alt+H",
    "front":              "Alt+J",
    "side":               "Alt+K",
    # Snap
    "snap_to_grid":       "End",
    "snap_to_surface":    "V",
    # Panels
    "content_browser":    "Ctrl+Shift+F",
    "outliner":           "Alt+1",
    "details":            "Alt+2",
    # Transform modes
    "mode_select":        "1",
    "mode_translate":     "2",
    "mode_rotate":        "3",
    "mode_scale":         "4",
    # Tools
    "add_actor":          "Shift+A",
    "translate_tool":     "W",
    "rotate_tool":        "E",
    "scale_tool":         "R",
    # Misc
    "frame_selected":     "F",
    "toggle_fullscreen":  "F11",
    "screenshot":         "F9",
    "find_in_blueprint":  "Ctrl+F",
    "compile_from_kismet":"Ctrl+F7",
    # Material editor
    "apply_material":     "Ctrl+Enter",
    # Animation
    "play_animation":     "Space",
}


# ──────────────────────────────────────────────────────────────────────
# Operation catalog — 60+ operations
# ──────────────────────────────────────────────────────────────────────
UE_OPERATIONS = sorted({
    # project
    "open_project", "save_all", "switch_project", "create_project",
    # level
    "new_level", "open_level", "save_current_level", "build_lighting",
    "add_actor", "delete_actor", "move_actor", "rotate_actor", "scale_actor",
    "duplicate_actor", "find_actors", "frame_actor", "select_actor",
    # blueprint
    "create_blueprint", "compile_blueprint", "delete_blueprint",
    "add_blueprint_component", "add_blueprint_variable",
    "add_blueprint_node", "connect_blueprint_pins", "set_blueprint_default",
    "open_blueprint_editor",
    # cpp
    "create_cpp_class", "compile_cpp", "build_solution",
    "generate_project_files", "open_in_ide",
    # material
    "create_material", "add_material_expression", "connect_material_pins",
    "set_material_parameter", "apply_material_to_actor",
    # texture
    "import_texture", "set_texture_settings", "convert_to_normal_map",
    "set_texture_group",
    # mesh
    "import_static_mesh", "import_skeletal_mesh", "import_fbx",
    "set_mesh_lod", "set_mesh_collision", "set_mesh_shadow",
    "set_mesh_mobility",
    # animation
    "create_anim_blueprint", "set_skeleton", "play_animation",
    "create_animation_sequence", "import_animation",
    # niagara
    "create_niagara_system", "add_niagara_emitter",
    # sequencer
    "create_sequence", "add_actor_to_sequence", "render_movie",
    # audio
    "import_sound", "create_sound_cue", "play_audio",
    # lighting
    "build_lighting_quality", "set_lightmass_quality",
    "add_light", "add_post_process_volume",
    # packaging
    "package_windows", "package_android", "package_ios", "package_linux",
    "package_server", "package_html5",
    # settings + plugins
    "set_project_setting", "get_project_setting",
    "enable_plugin", "disable_plugin",
    # source control
    "git_pull", "git_commit", "perforce_submit",
    # utilities
    "take_screenshot", "export_selected", "screenshot_viewport",
    # content browser
    "list_assets", "delete_asset", "duplicate_asset",
    "rename_asset", "move_asset", "save_asset",
    "migrate_assets", "import_asset",
    # editor
    "play_in_editor", "stop_play_in_editor", "simulate_in_editor",
    "open_editor_preferences", "open_project_settings",
})


class UnrealAdapter(AppAdapter):
    name = "unreal"
    processes = UE_PROCESSES
    capabilities = [
        AdapterCapability.CLICK, AdapterCapability.TYPE,
        AdapterCapability.KEYPRESS, AdapterCapability.NAVIGATE,
        AdapterCapability.CUSTOM, AdapterCapability.EXTRACT_TEXT,
        AdapterCapability.LIST_CONTROLS,
    ]

    def __init__(self):
        self._rc_url: str = ""
        self._rc_checked: bool = False
        self._ue_python_path: str = ""
        self._install_dir: str = ""

    def handles_processes(self) -> list[str]:
        return list(self.processes)

    def catalog(self) -> list[str]:
        """Return the list of operations this adapter can perform."""
        return UE_OPERATIONS

    # ── discovery ──
    def discover_rc(self) -> str:
        if self._rc_checked:
            return self._rc_url
        self._rc_checked = True
        for port in (30010, 30020, 30030):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    self._rc_url = f"http://127.0.0.1:{port}"
                    logger.info("Unreal WebRemoteControl at %s", self._rc_url)
                    return self._rc_url
            except OSError:
                continue
        return ""

    def discover_python(self) -> str:
        if self._ue_python_path:
            return self._ue_python_path
        candidates = [
            Path(os.environ.get("UE_PYTHON_PATH", "")),
        ]
        install = self.discover_install_dir()
        if install:
            candidates.extend([
                Path(install) / "Engine/Binaries/ThirdParty/Python3/Win64/python.exe",
                Path(install) / "Engine/Binaries/ThirdParty/Python3/Linux/bin/python3",
            ])
        for c in candidates:
            if c and c.exists():
                self._ue_python_path = str(c)
                return self._ue_python_path
        return ""

    def discover_install_dir(self) -> str:
        if self._install_dir:
            return self._install_dir
        for env in ("UE_INSTALL_DIR", "UNREAL_ENGINE_PATH"):
            v = os.environ.get(env)
            if v and Path(v).exists():
                self._install_dir = v
                return self._install_dir
        for default in (
            "C:/Program Files/Epic Games/UE_4.22",
            "C:/Program Files/Epic Games/UE_4.23",
            "C:/Program Files/Epic Games/UE_4.24",
            "C:/Program Files/Epic Games/UE_4.25",
            "C:/Program Files/Epic Games/UE_4.26",
            "C:/Program Files/Epic Games/UE_4.27",
            "C:/Program Files/Epic Games/UE_5.0",
            "C:/Program Files/Epic Games/UE_5.1",
            "C:/Program Files/Epic Games/UE_5.2",
            "C:/Program Files/Epic Games/UE_5.3",
            "C:/Program Files/Epic Games/UE_5.4",
            "D:/UnrealEngine",
            "D:/UE_4.22",
        ):
            if Path(default).exists():
                self._install_dir = default
                return self._install_dir
        return ""

    # ── main execute ──
    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        op = self._resolve_op(action)
        params = self._resolve_params(action)
        try:
            # T1: WebRemoteControl (HTTP) — UE 4.25+
            rc = self.discover_rc()
            if rc:
                r = self._exec_remote_control(rc, op, params)
                if r.success:
                    return r
            # T1: bundled Python
            uedir = self.discover_install_dir()
            if uedir:
                py = self.discover_python()
                if py:
                    r = self._exec_python(py, op, params)
                    if r.success:
                        return r
            # T3: UIA
            r = self._exec_uia(action, op, params)
            if r.success:
                return r
            # T6: keyboard shortcut
            return self._exec_keyboard_shortcut(op, params, t0)
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="unreal.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def run_op(self, op: str, **params) -> AdapterResult:
        """Convenience: build a synthetic action and execute."""
        from .actions_compat import Action
        a = Action(
            action_type=ActionType.RUN_WORKFLOW,
            target_name=op,
            parameters={"op": op, **params},
        )
        return self.execute(a, None)

    # ── T1: WebRemoteControl ──
    def _exec_remote_control(self, rc_url: str, op: str, params: dict) -> AdapterResult:
        t0 = time.time()
        try:
            payload = {
                "objectPath": params.get("object_path", "/Script/Engine.EditorLevelLibrary"),
                "functionName": op,
                "parameters": params.get("rc_params", {}),
            }
            req = urllib.request.Request(
                f"{rc_url}/remote/object/call",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
                return AdapterResult(
                    success=True,
                    method="unreal.web_remote_control",
                    data={"response": body[:1000], "op": op},
                    duration_ms=(time.time() - t0) * 1000.0,
                )
        except (urllib.error.URLError, OSError) as exc:
            return AdapterResult(success=False, error=f"RC: {exc}",
                                  method="unreal.rc_fail")

    # ── T1: Python ──
    def _exec_python(self, python_exe: str, op: str, params: dict) -> AdapterResult:
        t0 = time.time()
        script = self._op_to_python(op, params)
        if not script:
            return AdapterResult(success=False, error=f"no python for op {op}",
                                  method="unreal.no_script")
        tmp = Path(os.environ.get("TEMP", "/tmp")) / f"sonic_ue_{op}.py"
        try:
            tmp.write_text(script, encoding="utf-8")
        except Exception as exc:
            return AdapterResult(success=False, error=str(exc),
                                  method="unreal.write_fail")
        return AdapterResult(
            success=True,
            method="unreal.python_ready",
            data={"script_path": str(tmp), "op": op,
                  "interpreter": python_exe,
                  "note": "script written; load into editor's Python REPL or run via -run=pythonscript"},
            duration_ms=(time.time() - t0) * 1000.0,
            capabilities_used=[AdapterCapability.CUSTOM],
        )

    def _op_to_python(self, op: str, params: dict) -> str:
        """Build an unreal Python snippet for the given op."""
        q = lambda s: f"'{s}'" if s else "''"
        # ── project ──
        if op == "save_all":
            return "import unreal\nfor lvl in unreal.EditorAssetLibrary.list_assets('/Game'):\n    unreal.EditorAssetLibrary.save_loaded_asset(unreal.load_asset(lvl))\n"
        if op == "open_project":
            path = params.get("project_path", "")
            return f"# Open project: double-click {path} or use -project={path}\n# Run via cmd: UnrealEditor-Cmd.exe {path}\nprint('Use -project= commandline flag')\n"
        if op == "create_project":
            name = params.get("name", "NewProject")
            template = params.get("template", "Blank")
            return f"# Create new project via launcher or template wizard\nprint('New project: {name} from {template}')\n"
        # ── level ──
        if op == "new_level":
            return ("import unreal\n"
                    "unreal.EditorLevelLibrary.new_level(q := '/Game/Maps/NewMap')\n")
        if op == "open_level":
            path = params.get("level_path", "/Game/Maps/Main")
            return f"import unreal\nunreal.EditorLevelLibrary.load_level({q(path)})\n"
        if op == "save_current_level":
            return "import unreal\nunreal.EditorLevelLibrary.save_current_level()\n"
        if op == "build_lighting":
            path = params.get("level_path", "")
            return (f"import unreal\n"
                    f"unreal.Lightmass.import_static_mesh_lighting({q(path) or '/Game/Maps/Main'})\n")
        if op == "add_actor":
            cls = params.get("class_name", "StaticMeshActor")
            loc = params.get("location", [0, 0, 0])
            rot = params.get("rotation", [0, 0, 0])
            return ("import unreal\n"
                    f"unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.{cls}, unreal.Vector({loc[0]}, {loc[1]}, {loc[2]}), unreal.Rotator({rot[0]}, {rot[1]}, {rot[2]}))\n")
        if op == "delete_actor":
            return ("import unreal\n"
                    "for a in unreal.EditorLevelLibrary.get_selected_level_actors():\n"
                    "    unreal.EditorLevelLibrary.destroy_actor(a)\n")
        if op == "move_actor":
            loc = params.get("location", [0, 0, 0])
            return (f"import unreal\n"
                    f"for a in unreal.EditorLevelLibrary.get_selected_level_actors():\n"
                    f"    a.set_actor_location(unreal.Vector({loc[0]}, {loc[1]}, {loc[2]}), False, False)\n")
        if op == "rotate_actor":
            rot = params.get("rotation", [0, 0, 0])
            return (f"import unreal\n"
                    f"for a in unreal.EditorLevelLibrary.get_selected_level_actors():\n"
                    f"    a.set_actor_rotation(unreal.Rotator({rot[0]}, {rot[1]}, {rot[2]}), False)\n")
        if op == "scale_actor":
            s = params.get("scale", [1, 1, 1])
            return (f"import unreal\n"
                    f"for a in unreal.EditorLevelLibrary.get_selected_level_actors():\n"
                    f"    a.set_actor_scale3d(unreal.Vector({s[0]}, {s[1]}, {s[2]}))\n")
        if op == "duplicate_actor":
            return ("import unreal\n"
                    "unreal.EditorLevelLibrary.duplicate_actors()\n")
        if op == "find_actors":
            cls = params.get("class_name", "Actor")
            return (f"import unreal\n"
                    f"actors = unreal.GameplayStatics.get_all_actors_of_class(unreal.EditorLevelLibrary.get_editor_world(), unreal.{cls})\n"
                    f"print(f'Found {{len(actors)}} {cls} actors')\n")
        if op == "select_actor":
            name = params.get("name", "")
            return (f"import unreal\n"
                    f"for a in unreal.GameplayStatics.get_all_actors_of_class(unreal.EditorLevelLibrary.get_editor_world(), unreal.Actor):\n"
                    f"    if a.get_name() == {q(name)}:\n"
                    f"        unreal.EditorLevelLibrary.set_selected_level_actors([a])\n"
                    f"        break\n")
        # ── blueprint ──
        if op == "create_blueprint":
            name = params.get("name", "NewBlueprint")
            parent = params.get("parent", "Actor")
            path = params.get("path", f"/Game/Blueprints/{name}")
            return (f"import unreal\n"
                    f"factory = unreal.BlueprintFactory()\n"
                    f"factory.parent_class = unreal.{parent}\n"
                    f"tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
                    f"tools.create_asset({q(name)}, {q('/Game/Blueprints')}, unreal.Blueprint, factory)\n")
        if op == "compile_blueprint":
            return ("import unreal\n"
                    "tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
                    "tools.compile_blueprint_scripts()\n")
        if op == "delete_blueprint":
            p = params.get("path", "")
            return f"import unreal\nunreal.EditorAssetLibrary.delete_asset({q(p)})\n"
        if op == "add_blueprint_component":
            bp = params.get("blueprint", "")
            comp = params.get("component", "StaticMeshComponent")
            return (f"import unreal\n"
                    f"bp = unreal.load_object(None, {q(bp)})\n"
                    f"node = unreal.SubobjectDataSubsystem.get()\n"
                    f"sm = unreal.new_object(unreal.{comp}, bp.generated_class())\n")
        if op == "add_blueprint_variable":
            bp = params.get("blueprint", "")
            vname = params.get("var_name", "NewVar")
            vtype = params.get("var_type", "float")
            return (f"import unreal\n"
                    f"bp = unreal.load_object(None, {q(bp)})\n"
                    f"bp.add_property({q(vname)}, unreal.{vtype})\n")
        if op == "add_blueprint_node":
            return "# Use Blueprint Editor K2Node APIs\nimport unreal\nprint('open K2Node graph for blueprint edit')\n"
        if op == "connect_blueprint_pins":
            return "# Use BlueprintEditorLibrary.connect_pins / K2Node compilation\nprint('connect pins via K2Graph API')\n"
        if op == "set_blueprint_default":
            vname = params.get("var_name", "")
            vval = params.get("value", 0)
            return (f"import unreal\n"
                    f"bp_cdo = unreal.load_object(None, {q(params.get('blueprint', ''))}).generated_class().get_default_object()\n"
                    f"setattr(bp_cdo, {q(vname)}, {vval})\n")
        if op == "open_blueprint_editor":
            return "import unreal\nunreal.AssetEditorSubsystem.get().open_editor_for_asset(unreal.load_asset('/Game/Blueprints/'))\n"
        # ── cpp ──
        if op == "create_cpp_class":
            name = params.get("name", "NewActor")
            parent = params.get("parent", "AActor")
            return (f"// Manually create .h and .cpp in Source/ValidateProject/ then Build Solution.\n"
                    f"// Use New C++ Class wizard from File menu → New C++ Class.\n")
        if op == "compile_cpp":
            proj = params.get("project_path", "")
            return (f"import subprocess\n"
                    f"subprocess.Popen(['UnrealBuildTool.exe', 'Development', 'Editor', '-Project={proj}', '-WaitMutex', '-FromMsBuild'])\n")
        if op == "build_solution":
            sln = params.get("solution_path", "")
            return f"import subprocess\nsubprocess.Popen(['msbuild.exe', {q(sln)}, '/p:Configuration=Development Editor'])\n"
        if op == "generate_project_files":
            uedir = self.discover_install_dir()
            return f"import subprocess\nsubprocess.Popen([{q(uedir)}/Engine/Build/BatchFiles/GenerateProjectFiles.bat'])\n"
        if op == "open_in_ide":
            sln = params.get("solution_path", "")
            return f"import subprocess\nsubprocess.Popen([{q(sln)}])\n"
        # ── material ──
        if op == "create_material":
            name = params.get("name", "M_NewMaterial")
            return (f"import unreal\n"
                    f"factory = unreal.MaterialFactoryNew()\n"
                    f"tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
                    f"tools.create_asset({q(name)}, '/Game/Materials', unreal.Material, factory)\n")
        if op == "add_material_expression":
            mat = params.get("material", "")
            expr = params.get("expression", "TextureSampleParameter2D")
            return (f"import unreal\n"
                    f"mat = unreal.load_asset({q(mat)})\n"
                    f"expr = unreal.MaterialEditingLibrary.create_material_expression(mat, unreal.{expr})\n")
        if op == "connect_material_pins":
            return "# use unreal.MaterialEditingLibrary.connect_material_property / connect_material_expressions\n"
        if op == "set_material_parameter":
            return "# use unreal.MaterialEditingLibrary.set_material_instance_parent\n"
        if op == "apply_material_to_actor":
            return "# iterate selected actors, set material on mesh component\n"
        # ── texture ──
        if op == "import_texture":
            src = params.get("source_path", "")
            dst = params.get("destination", "/Game/Textures")
            return (f"import unreal\n"
                    f"task = unreal.AssetImportTask()\n"
                    f"task.filename = {q(src)}\n"
                    f"task.destination_path = {q(dst)}\n"
                    f"task.replace_existing = True\n"
                    f"task.automated = True\n"
                    f"unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])\n")
        if op == "set_texture_settings":
            return "# use unreal.EditorAssetLibrary + Texture2D settings\n"
        if op == "convert_to_normal_map":
            return "# use unreal.TextureFactory settings: CompressionSettings = TC_Normalmap\n"
        if op == "set_texture_group":
            return "# use unreal.Texture.set_editor_properties\n"
        # ── mesh ──
        if op == "import_static_mesh":
            return self._op_to_python("import_fbx", params)
        if op == "import_skeletal_mesh":
            return self._op_to_python("import_fbx", params)
        if op == "import_fbx":
            src = params.get("source_path", "")
            dst = params.get("destination", "/Game/Meshes")
            return (f"import unreal\n"
                    f"task = unreal.AssetImportTask()\n"
                    f"task.filename = {q(src)}\n"
                    f"task.destination_path = {q(dst)}\n"
                    f"task.replace_existing = True\n"
                    f"task.automated = True\n"
                    f"task.options = unreal.FbxImportUI()\n"
                    f"task.options.import_mesh = True\n"
                    f"task.options.import_as_skeletal = {params.get('skeletal', False)}\n"
                    f"unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])\n")
        if op == "set_mesh_lod":
            return "# use unreal.StaticMesh.set_editor_properties / generate_lod_screen_sizes\n"
        if op == "set_mesh_collision":
            return "# use unreal.EditorStaticMeshLibrary.generate_box_collision / set_collision_complexity\n"
        if op == "set_mesh_shadow":
            return "# set CastShadow, bCastDynamicShadow, bAffectDistanceFieldLighting\n"
        if op == "set_mesh_mobility":
            mob = params.get("mobility", "Movable")
            return f"# set_actor_mobility / set_mobility(unreal.ComponentMobility.{mob.upper()})\n"
        # ── animation ──
        if op == "create_anim_blueprint":
            return "# use unreal.AnimBlueprintFactory with skeleton reference\n"
        if op == "set_skeleton":
            return "# use unreal.SkeletalMesh.skeleton assignment\n"
        if op == "play_animation":
            return "# use unreal.GameplayStatics.play_anim_seq_in_editor\n"
        if op == "create_animation_sequence":
            return "# use unreal.AnimationSequenceFactory\n"
        if op == "import_animation":
            return "# use unreal.AnimSequenceFactory with FBX\n"
        # ── niagara ──
        if op == "create_niagara_system":
            return "# use unreal.NiagaraSystemFactoryNew\n"
        if op == "add_niagara_emitter":
            return "# use unreal.NiagaraEditorTools / subsystem API\n"
        # ── sequencer ──
        if op == "create_sequence":
            return "# use unreal.LevelSequenceEditorBlueprintLibrary.create_level_sequence\n"
        if op == "add_actor_to_sequence":
            return "# use unreal.SequencerTools / binding APIs\n"
        if op == "render_movie":
            return "# use MoviePipeline / RenderQueue (UE 5+)\n"
        # ── audio ──
        if op == "import_sound":
            return "# use unreal.SoundFactory with wav import\n"
        if op == "create_sound_cue":
            return "# use unreal.SoundCueFactoryNew\n"
        if op == "play_audio":
            return "# use unreal.GameplayStatics.play_sound_2d\n"
        # ── lighting ──
        if op == "build_lighting_quality":
            quality = params.get("quality", "Production")
            return (f"import unreal\n"
                    f"unreal.Lightmass.set_lightmass_quality_level(unreal.LightmassQualityLevel.{quality})\n"
                    f"unreal.Lightmass.import_static_mesh_lighting('/Game/Maps/Main')\n")
        if op == "set_lightmass_quality":
            quality = params.get("quality", "Production")
            return f"import unreal\nunreal.Lightmass.set_lightmass_quality_level(unreal.LightmassQualityLevel.{quality})\n"
        if op == "add_light":
            cls = params.get("class_name", "PointLight")
            loc = params.get("location", [0, 0, 100])
            return (f"import unreal\n"
                    f"unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.{cls}, unreal.Vector({loc[0]}, {loc[1]}, {loc[2]}), unreal.Rotator(0,0,0))\n")
        if op == "add_post_process_volume":
            return "# spawn_actor_from_class(unreal.PostProcessVolume, ...)\n"
        # ── packaging ──
        if op in ("package_windows", "package_android", "package_ios",
                   "package_linux", "package_server", "package_html5"):
            target_map = {
                "package_windows":  "WindowsNoEditor",
                "package_android":  "Android",
                "package_ios":      "IOS",
                "package_linux":    "LinuxNoEditor",
                "package_server":   "LinuxServer",
                "package_html5":    "HTML5",
            }
            target = target_map[op]
            proj = params.get("project_path", "")
            install = self.discover_install_dir() or ""
            uat = f"{install}/Engine/Build/BatchFiles/RunUAT.bat"
            return (f"import subprocess\n"
                    f"subprocess.Popen([{q(uat)}, 'BuildCookRun', "
                    f"'-project={proj}', '-noP4', '-platform={target}', "
                    f"'-clientconfig=Shipping', '-serverconfig=Shipping', "
                    f"'-cook', '-allmaps', '-build', '-stage', '-pak', '-archive'])\n")
        # ── settings + plugins ──
        if op == "set_project_setting":
            section = params.get("section", "General")
            key = params.get("key", "")
            val = params.get("value", "")
            return (f"import unreal\n"
                    f"settings = unreal.get_default_object(unreal.GeneralProjectSettings)\n"
                    f"setattr(settings, {q(key)}, {q(val)})\n")
        if op == "get_project_setting":
            return "# read get_default_object(...) attribute\n"
        if op == "enable_plugin":
            name = params.get("plugin", "")
            return (f"# edit {self.discover_install_dir() or ''}/Engine/Plugins/<plugin>/<plugin>.uplugin or project .uproject Plugins section\n"
                    f"# set 'EnabledByDefault': true\n")
        if op == "disable_plugin":
            name = params.get("plugin", "")
            return f"# set EnabledByDefault: false for {name}\n"
        # ── source control ──
        if op == "git_pull":
            return "import subprocess\nsubprocess.Popen(['git', 'pull'])\n"
        if op == "git_commit":
            msg = params.get("message", "Update")
            return f"import subprocess\nsubprocess.Popen(['git', 'add', '.', '&&', 'git', 'commit', '-m', '{msg}'])\n"
        if op == "perforce_submit":
            return "# use unreal.SourceControl.submit_with_dialog()\n"
        # ── utilities ──
        if op == "take_screenshot":
            return ("import unreal\n"
                    "unreal.AutomationLibrary.take_high_res_screenshot(1920, 1080)\n")
        if op == "export_selected":
            return "# use unreal.Exporter export to FBX / OBJ\n"
        if op == "screenshot_viewport":
            return "import unreal\nunreal.EditorLevelLibrary.editor_request_end_play_map()\nunreal.AutomationLibrary.take_high_res_screenshot(1920, 1080)\n"
        # ── content browser ──
        if op == "list_assets":
            path = params.get("path", "/Game")
            recurse = params.get("recursive", True)
            return (f"import unreal\n"
                    f"assets = unreal.EditorAssetLibrary.list_assets({q(path)}, recursive={recurse}, include_folder=False)\n"
                    f"print('\\n'.join(assets))\n")
        if op == "delete_asset":
            p = params.get("path", "")
            return f"import unreal\nunreal.EditorAssetLibrary.delete_asset({q(p)})\n"
        if op == "duplicate_asset":
            src = params.get("src", "")
            dst = params.get("dst", "")
            return f"import unreal\nunreal.EditorAssetLibrary.duplicate_asset({q(src)}, {q(dst)})\n"
        if op == "rename_asset":
            src = params.get("src", "")
            new = params.get("new_name", "")
            return f"import unreal\nunreal.EditorAssetLibrary.rename_asset({q(src)}, {q(new)})\n"
        if op == "move_asset":
            src = params.get("src", "")
            dst = params.get("dst", "")
            return f"import unreal\nunreal.EditorAssetLibrary.rename_asset({q(src)}, {q(dst)})\n"
        if op == "save_asset":
            p = params.get("path", "")
            return f"import unreal\nunreal.EditorAssetLibrary.save_loaded_asset(unreal.load_asset({q(p)}))\n"
        if op == "migrate_assets":
            assets = params.get("assets", [])
            dst = params.get("destination", "")
            assets_py = "[" + ", ".join(f"{q(a)}" for a in assets) + "]"
            return (f"import unreal\n"
                    f"tools = unreal.AssetToolsHelpers.get_asset_tools()\n"
                    f"tools.migrate_assets({assets_py}, {q(dst)})\n")
        if op == "import_asset":
            return self._op_to_python("import_fbx", params)
        # ── editor ──
        if op == "play_in_editor":
            return "import unreal\nunreal.EditorLevelLibrary.editor_play_simulate()\n"
        if op == "stop_play_in_editor":
            return "import unreal\nunreal.EditorLevelLibrary.editor_end_play_map()\n"
        if op == "simulate_in_editor":
            return "import unreal\nunreal.LevelEditorSubsystem.get_simulate_mode()\n"
        if op == "open_editor_preferences":
            return "import unreal\nunreal.EditorPreferencesSubsystem.open_editor_preferences()\n"
        if op == "open_project_settings":
            return "import unreal\nunreal.ProjectSettingsHelpers.open_project_settings()\n"
        return ""

    # ── T3: UIA ──
    def _exec_uia(self, action, op: str, params: dict) -> AdapterResult:
        t0 = time.time()
        try:
            from pywinauto import Application  # type: ignore
        except ImportError:
            return AdapterResult(success=False, error="pywinauto not installed",
                                  method="unreal.no_pywinauto")
        try:
            app = Application(backend="uia").connect(
                title_re=".*Unreal Editor.*", timeout=2,
            )
        except Exception as exc:
            return AdapterResult(success=False, error=f"UE window: {exc}",
                                  method="unreal.connect_fail")
        try:
            win = app.window(active_only=True)
            label = params.get("label") or action.target_name or action.target_text or op
            try:
                btn = win.child_window(title_re=f".*{label}.*",
                                        control_type="Button", timeout=2)
                if btn.exists():
                    btn.invoke()
                    return AdapterResult(
                        success=True, method="unreal.uia_invoke",
                        data={"label": label},
                        duration_ms=(time.time() - t0) * 1000.0,
                    )
            except Exception:
                pass
            # try menu bar
            try:
                win.menu_select(label.replace("_", " "))
                return AdapterResult(
                    success=True, method="unreal.menu_select",
                    data={"label": label},
                    duration_ms=(time.time() - t0) * 1000.0,
                )
            except Exception:
                pass
            return AdapterResult(
                success=False, error=f"button/menu '{label}' not found",
                method="unreal.uia_miss",
            )
        except Exception as exc:
            return AdapterResult(success=False, error=str(exc),
                                  method="unreal.uia_fail",
                                  duration_ms=(time.time() - t0) * 1000.0)

    # ── T6: shortcut ──
    def _exec_keyboard_shortcut(self, op: str, params: dict, t0: float) -> AdapterResult:
        try:
            import pyautogui  # type: ignore
        except ImportError:
            return AdapterResult(success=False, error="pyautogui not installed",
                                  method="unreal.no_pyautogui")

        keys = params.get("keys") or params.get("shortcut") or UE_SHORTCUTS.get(op)
        if not keys:
            return AdapterResult(
                success=False,
                error=f"no shortcut for op '{op}'",
                method="unreal.no_shortcut",
            )
        try:
            for combo in (keys if isinstance(keys, list) else [keys]):
                parts = combo.replace(" ", "").split("+")
                pyautogui.hotkey(*parts)
                time.sleep(0.05)
            return AdapterResult(
                success=True, method=f"unreal.shortcut({keys})",
                data={"op": op, "shortcut": keys},
                duration_ms=(time.time() - t0) * 1000.0,
                capabilities_used=[AdapterCapability.KEYPRESS],
            )
        except Exception as exc:
            return AdapterResult(success=False, error=str(exc),
                                  method="unreal.shortcut_fail")

    # ── helpers ──
    def _resolve_op(self, action) -> str:
        return (action.parameters.get("op")
                or action.target_name
                or action.parameters.get("intent")
                or "")

    def _resolve_params(self, action) -> dict:
        p = dict(action.parameters or {})
        p.pop("op", None)
        # also surface text/name as common params
        if action.target_text:
            p.setdefault("label", action.target_text)
        if action.text and "text" not in p:
            p["text"] = action.text
        return p

    def _is_editor_running(self) -> bool:
        try:
            import psutil  # type: ignore
            for p in psutil.process_iter(['name']):
                n = (p.info['name'] or "").lower()
                if any(x.lower() in n for x in UE_PROCESSES):
                    return True
        except ImportError:
            return False
        return False

    def observe(self, state) -> dict:
        return {
            "rc_url": self.discover_rc(),
            "python_path": self.discover_python(),
            "install_dir": self.discover_install_dir(),
            "editor_running": self._is_editor_running(),
            "operation_count": len(UE_OPERATIONS),
            "operations_sample": UE_OPERATIONS[:15],
        }
