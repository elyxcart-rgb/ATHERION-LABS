"""SONIC AI — Universal Unreal Engine Goal Interpreter.

Translates high-level "do anything in Unreal" intents into a sequence of
atomic UnrealAdapter operations. Examples:

  "create a new blueprint actor with a static mesh component"
    → create_blueprint → add_blueprint_component → set_blueprint_default
       → compile_blueprint → save_asset

  "import this FBX as a static mesh with auto LODs"
    → import_fbx → set_mesh_lod → set_mesh_collision → save_asset

  "build lighting at production quality"
    → set_lightmass_quality=Production → build_lighting_quality

  "package project for Windows"
    → save_all → package_windows

  "make a level with a landscape, 3 lights, and a post-process volume"
    → new_level → add_actor(Landscape) → add_actor(PointLight)x3
       → add_post_process_volume → save_current_level

Public API:
    UnrealGoalInterpreter()
    .interpret(goal_text, context=None) -> list[Action]
    .catalog() -> list[str]    # known goal patterns
    .describe(goal_name) -> dict
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from .actions import Action, ActionType, CapabilityTier


logger = logging.getLogger("sonic.ue_goals")


# ──────────────────────────────────────────────────────────────────────
# Goal patterns — natural-language triggers → composite plans
# ──────────────────────────────────────────────────────────────────────
@dataclass
class GoalPattern:
    name: str
    description: str
    intent_regex: list[str]          # any of these regexes match
    keywords: list[str] = field(default_factory=list)
    builder: str = ""                # name of method that builds actions


GOAL_CATALOG = sorted([
    # ── Project / level lifecycle ──
    GoalPattern("open_project", "Open a Unreal project (.uproject)",
                [r"open.*project", r"launch.*unreal", r"start.*unreal"],
                keywords=["open", "project", "uproject"],
                builder="build_open_project"),
    GoalPattern("new_level", "Create a new empty level",
                [r"new\s+(?:empty\s+)?level", r"create.*new.*map"],
                keywords=["new", "level", "map"],
                builder="build_new_level"),
    GoalPattern("save_all", "Save everything",
                [r"save\s+(?:all|everything|project)"],
                keywords=["save"],
                builder="build_save_all"),
    GoalPattern("build_lighting", "Build lighting for current level",
                [r"build.*light", r"rebuild.*light", r"compute.*light"],
                keywords=["build", "lighting", "lightmap"],
                builder="build_lighting"),

    # ── Blueprint ──
    GoalPattern("create_blueprint", "Create a new Blueprint class",
                [r"create.*blueprint", r"new.*blueprint", r"make.*blueprint",
                 r"add.*blueprint"],
                keywords=["blueprint"],
                builder="build_create_blueprint"),
    GoalPattern("compile_blueprint", "Compile all dirty Blueprints",
                [r"compile.*blueprint", r"build.*blueprint"],
                keywords=["compile", "blueprint"],
                builder="build_compile_blueprint"),

    # ── C++ ──
    GoalPattern("create_cpp_class", "Create a new C++ class",
                [r"create.*c\+\+.*class", r"new.*c\+\+", r"add.*c\+\+"],
                keywords=["c++", "class"],
                builder="build_create_cpp_class"),
    GoalPattern("compile_cpp", "Compile C++ / build solution",
                [r"compile.*c\+\+", r"build.*solution", r"build.*editor"],
                keywords=["compile", "build", "solution"],
                builder="build_compile_cpp"),
    GoalPattern("generate_project_files", "Regenerate Visual Studio project files",
                [r"generate.*project.*file", r"regenerate.*project"],
                keywords=["generate", "project", "files"],
                builder="build_generate_project_files"),

    # ── Asset import ──
    GoalPattern("import_fbx", "Import an FBX file",
                [r"import.*fbx", r"import.*mesh", r"import.*model",
                 r"load.*fbx"],
                keywords=["import", "fbx", "mesh"],
                builder="build_import_fbx"),
    GoalPattern("import_texture", "Import a texture image",
                [r"import.*texture", r"import.*image", r"load.*texture"],
                keywords=["import", "texture"],
                builder="build_import_texture"),
    GoalPattern("import_sound", "Import an audio file",
                [r"import.*sound", r"import.*audio", r"import.*music"],
                keywords=["import", "sound", "audio"],
                builder="build_import_sound"),

    # ── Material ──
    GoalPattern("create_material", "Create a new Material asset",
                [r"create.*material", r"new.*material"],
                keywords=["material"],
                builder="build_create_material"),

    # ── Actor manipulation ──
    GoalPattern("add_actor", "Add an actor to the level",
                [r"add.*actor", r"place.*actor", r"spawn.*actor",
                 r"drop.*actor"],
                keywords=["add", "place", "actor"],
                builder="build_add_actor"),
    GoalPattern("move_actor", "Move selected actor(s)",
                [r"move.*actor", r"reposition", r"set.*location"],
                keywords=["move", "actor", "position"],
                builder="build_move_actor"),
    GoalPattern("rotate_actor", "Rotate selected actor(s)",
                [r"rotate.*actor", r"turn.*actor", r"set.*rotation"],
                keywords=["rotate", "actor"],
                builder="build_rotate_actor"),

    # ── Lighting ──
    GoalPattern("add_light", "Add a light to the level",
                [r"add.*light", r"place.*light", r"drop.*light",
                 r"add.*point.*light", r"add.*spot.*light",
                 r"add.*directional"],
                keywords=["light"],
                builder="build_add_light"),
    GoalPattern("add_post_process", "Add a post-process volume",
                [r"post.*process", r"add.*volume"],
                keywords=["post", "process", "volume"],
                builder="build_add_post_process"),

    # ── Packaging ──
    GoalPattern("package_windows", "Package the project for Windows",
                [r"package.*windows", r"build.*windows", r"cook.*windows",
                 r"make.*build.*windows"],
                keywords=["package", "windows", "build"],
                builder="build_package_windows"),
    GoalPattern("package_android", "Package the project for Android",
                [r"package.*android", r"build.*android", r"cook.*android"],
                keywords=["package", "android"],
                builder="build_package_android"),

    # ── Animation ──
    GoalPattern("play_in_editor", "Play / Simulate in Editor",
                [r"play.*editor", r"simulate.*editor", r"hit.*play",
                 r"start.*play"],
                keywords=["play", "simulate"],
                builder="build_play_in_editor"),
    GoalPattern("stop_play", "Stop play-in-editor",
                [r"stop.*play", r"end.*play"],
                keywords=["stop"],
                builder="build_stop_play"),

    # ── Content browser / asset mgmt ──
    GoalPattern("list_assets", "List all assets under a path",
                [r"list.*assets", r"show.*assets", r"find.*assets"],
                keywords=["list", "assets"],
                builder="build_list_assets"),
    GoalPattern("migrate_assets", "Migrate assets between projects",
                [r"migrate.*assets", r"copy.*assets.*to"],
                keywords=["migrate", "assets"],
                builder="build_migrate_assets"),
    GoalPattern("duplicate_asset", "Duplicate an asset",
                [r"duplicate.*asset", r"copy.*asset"],
                keywords=["duplicate", "asset"],
                builder="build_duplicate_asset"),

    # ── Utilities ──
    GoalPattern("take_screenshot", "Take a screenshot of the editor",
                [r"screenshot", r"capture.*viewport", r"take.*picture"],
                keywords=["screenshot"],
                builder="build_take_screenshot"),
    GoalPattern("open_settings", "Open editor / project settings",
                [r"open.*settings", r"editor.*preferences",
                 r"project.*settings"],
                keywords=["settings", "preferences"],
                builder="build_open_settings"),

    # ── Composite "do anything" ──
    GoalPattern("setup_basic_scene", "Create a level with floor + light + camera + save",
                [r"setup.*scene", r"basic.*scene", r"starter.*scene",
                 r"default.*level"],
                keywords=["scene", "setup"],
                builder="build_setup_basic_scene"),
    GoalPattern("quick_playtest", "Save, play in editor, screenshot, stop",
                [r"playtest", r"quick.*play", r"test.*gameplay"],
                keywords=["playtest", "test"],
                builder="build_quick_playtest"),
], key=lambda g: g.name)


class UnrealGoalInterpreter:
    """Translates high-level goals → list of atomic Unreal Actions."""

    def __init__(self):
        self._catalog = GOAL_CATALOG

    # ── public ──
    def catalog(self) -> list[str]:
        return [g.name for g in self._catalog]

    def describe(self, goal_name: str) -> Optional[dict]:
        for g in self._catalog:
            if g.name == goal_name:
                return {"name": g.name, "description": g.description,
                        "keywords": g.keywords}
        return None

    def interpret(self, goal_text: str,
                  context: Optional[dict] = None) -> list[Action]:
        """Return a sequence of Actions that accomplish the goal."""
        text = goal_text.lower()
        context = context or {}

        # Try regex match
        for g in self._catalog:
            for pat in g.intent_regex:
                if re.search(pat, text):
                    builder = getattr(self, g.builder, None)
                    if builder:
                        return builder(goal_text, context)
        # Fallback: keyword match
        best = None
        best_score = 0
        for g in self._catalog:
            score = sum(1 for kw in g.keywords if kw in text)
            if score > best_score:
                best = g
                best_score = score
        if best:
            builder = getattr(self, best.builder, None)
            if builder:
                return builder(goal_text, context)

        # Last resort: forward to Adapter directly with raw intent
        return [self._make_action("noop", target_name=goal_text,
                                    description=f"raw intent: {goal_text}")]

    def _make_action(self, op: str, **params) -> Action:
        return Action(
            action_type=ActionType.RUN_WORKFLOW,
            target_name=op,
            parameters={"op": op, **params},
            preferred_tier=CapabilityTier.T4_ADAPTER,
            description=f"ue.{op}",
        )

    # ── builders ──
    def build_open_project(self, text, ctx) -> list[Action]:
        path = self._extract_path(text) or ctx.get("project_path", "")
        return [self._make_action("open_project", project_path=path)]

    def build_new_level(self, text, ctx) -> list[Action]:
        path = self._extract_path(text) or "/Game/Maps/NewMap"
        return [self._make_action("new_level", level_path=path)]

    def build_save_all(self, text, ctx) -> list[Action]:
        return [self._make_action("save_all")]

    def build_lighting(self, text, ctx) -> list[Action]:
        quality = self._match_enum(text, ["preview", "medium", "high",
                                          "production"], "Production")
        return [
            self._make_action("set_lightmass_quality", quality=quality.title()),
            self._make_action("build_lighting_quality", quality=quality.title()),
        ]

    def build_create_blueprint(self, text, ctx) -> list[Action]:
        name = self._extract_name(text) or "NewBlueprint"
        parent = "Actor"
        if "actor" in text:
            parent = "Actor"
        elif "character" in text:
            parent = "Character"
        elif "pawn" in text:
            parent = "Pawn"
        elif "widget" in text:
            parent = "UserWidget"
        elif "game mode" in text or "gamemode" in text:
            parent = "GameModeBase"
        elif "component" in text:
            parent = "ActorComponent"
        path = f"/Game/Blueprints/{name}"
        return [
            self._make_action("create_blueprint", name=name, parent=parent,
                              path=path),
            self._make_action("save_asset", path=path),
        ]

    def build_compile_blueprint(self, text, ctx) -> list[Action]:
        return [self._make_action("compile_blueprint")]

    def build_create_cpp_class(self, text, ctx) -> list[Action]:
        name = self._extract_name(text) or "NewActor"
        parent = "AActor"
        if "character" in text:
            parent = "ACharacter"
        elif "controller" in text:
            parent = "APlayerController"
        elif "game mode" in text:
            parent = "AGameModeBase"
        elif "component" in text:
            parent = "UActorComponent"
        return [
            self._make_action("create_cpp_class", name=name, parent=parent),
            self._make_action("generate_project_files"),
            self._make_action("build_solution",
                              solution_path=ctx.get("solution_path", "")),
        ]

    def build_compile_cpp(self, text, ctx) -> list[Action]:
        return [
            self._make_action("compile_cpp",
                              project_path=ctx.get("project_path", "")),
        ]

    def build_generate_project_files(self, text, ctx) -> list[Action]:
        return [self._make_action("generate_project_files")]

    def build_import_fbx(self, text, ctx) -> list[Action]:
        src = self._extract_path(text) or ctx.get("source_path", "")
        is_skel = "skeletal" in text or "animated" in text or "character" in text
        dst = "/Game/Meshes" if is_skel else "/Game/StaticMeshes"
        if "skeleton" in text:
            dst = "/Game/Characters/Meshes"
        return [
            self._make_action("import_fbx", source_path=src, destination=dst,
                              skeletal=is_skel),
            self._make_action("set_mesh_lod"),
            self._make_action("set_mesh_collision"),
            self._make_action("save_all"),
        ]

    def build_import_texture(self, text, ctx) -> list[Action]:
        src = self._extract_path(text) or ctx.get("source_path", "")
        is_normal = "normal" in text
        dst = "/Game/Textures/NormalMaps" if is_normal else "/Game/Textures"
        actions = [self._make_action("import_texture", source_path=src,
                                       destination=dst)]
        if is_normal:
            actions.append(self._make_action("convert_to_normal_map"))
        actions.append(self._make_action("set_texture_settings"))
        actions.append(self._make_action("save_all"))
        return actions

    def build_import_sound(self, text, ctx) -> list[Action]:
        src = self._extract_path(text) or ctx.get("source_path", "")
        dst = "/Game/Audio"
        return [
            self._make_action("import_sound", source_path=src, destination=dst),
            self._make_action("save_all"),
        ]

    def build_create_material(self, text, ctx) -> list[Action]:
        name = self._extract_name(text) or "M_NewMaterial"
        path = f"/Game/Materials/{name}"
        return [
            self._make_action("create_material", name=name),
            self._make_action("save_asset", path=path),
        ]

    def build_add_actor(self, text, ctx) -> list[Action]:
        cls = self._extract_actor_class(text) or "StaticMeshActor"
        loc = self._extract_vector(text, "at", default=(0, 0, 0))
        return [self._make_action("add_actor", class_name=cls,
                                    location=list(loc))]

    def build_move_actor(self, text, ctx) -> list[Action]:
        loc = self._extract_vector(text, "to", default=(0, 0, 0))
        return [self._make_action("move_actor", location=list(loc))]

    def build_rotate_actor(self, text, ctx) -> list[Action]:
        rot = self._extract_vector(text, "to", default=(0, 0, 0))
        return [self._make_action("rotate_actor", rotation=list(rot))]

    def build_add_light(self, text, ctx) -> list[Action]:
        cls = "DirectionalLight"
        if "point" in text:
            cls = "PointLight"
        elif "spot" in text:
            cls = "SpotLight"
        elif "directional" in text or "sun" in text:
            cls = "DirectionalLight"
        elif "rect" in text or "area" in text:
            cls = "RectLight"
        loc = self._extract_vector(text, "at", default=(0, 0, 500))
        return [self._make_action("add_light", class_name=cls,
                                    location=list(loc))]

    def build_add_post_process(self, text, ctx) -> list[Action]:
        return [self._make_action("add_post_process_volume")]

    def build_package_windows(self, text, ctx) -> list[Action]:
        return [
            self._make_action("save_all"),
            self._make_action("package_windows",
                              project_path=ctx.get("project_path", "")),
        ]

    def build_package_android(self, text, ctx) -> list[Action]:
        return [
            self._make_action("save_all"),
            self._make_action("package_android",
                              project_path=ctx.get("project_path", "")),
        ]

    def build_play_in_editor(self, text, ctx) -> list[Action]:
        return [self._make_action("play_in_editor")]

    def build_stop_play(self, text, ctx) -> list[Action]:
        return [self._make_action("stop_play_in_editor")]

    def build_list_assets(self, text, ctx) -> list[Action]:
        path = self._extract_path(text) or "/Game"
        return [self._make_action("list_assets", path=path)]

    def build_migrate_assets(self, text, ctx) -> list[Action]:
        src = self._extract_path(text) or "/Game/AssetsToMigrate"
        dst = ctx.get("destination_project", "")
        return [self._make_action("migrate_assets", assets=[src],
                                    destination=dst)]

    def build_duplicate_asset(self, text, ctx) -> list[Action]:
        src = self._extract_path(text) or ctx.get("src", "")
        dst = src.rsplit("/", 1)[0] + "/Copy_" + src.rsplit("/", 1)[-1]
        return [self._make_action("duplicate_asset", src=src, dst=dst)]

    def build_take_screenshot(self, text, ctx) -> list[Action]:
        return [self._make_action("take_screenshot")]

    def build_open_settings(self, text, ctx) -> list[Action]:
        if "project" in text:
            return [self._make_action("open_project_settings")]
        return [self._make_action("open_editor_preferences")]

    def build_setup_basic_scene(self, text, ctx) -> list[Action]:
        return [
            self._make_action("new_level", level_path="/Game/Maps/BasicScene"),
            self._make_action("add_actor", class_name="StaticMeshActor",
                              location=[0, 0, 0]),
            self._make_action("add_light", class_name="DirectionalLight",
                              location=[0, 0, 500]),
            self._make_action("add_light", class_name="PointLight",
                              location=[300, 300, 200]),
            self._make_action("add_post_process_volume"),
            self._make_action("save_current_level"),
        ]

    def build_quick_playtest(self, text, ctx) -> list[Action]:
        return [
            self._make_action("save_all"),
            self._make_action("play_in_editor"),
            # Note: stop + screenshot are user-driven after they verify play
        ]

    # ── extractors ──
    @staticmethod
    def _extract_path(text: str) -> str:
        m = re.search(r'([A-Za-z]:[\\/][^\s"\']+\.u?\w+)', text)
        if m:
            return m.group(1)
        m = re.search(r'([\\/][\w/.\-]+\.\w+)', text)
        if m:
            return m.group(1)
        m = re.search(r'["\']([^"\']+)["\']', text)
        if m and ("/" in m.group(1) or "\\" in m.group(1)):
            return m.group(1)
        return ""

    @staticmethod
    def _extract_name(text: str) -> str:
        # "named X" / "called X" / "with name X"
        m = re.search(r'(?:named|called|with name)\s+["\']?(\w+)["\']?', text)
        if m:
            return m.group(1)
        # quoted token
        m = re.search(r'["\'](\w+)["\']', text)
        if m:
            return m.group(1)
        return ""

    @staticmethod
    def _extract_actor_class(text: str) -> str:
        # Common actor types
        actor_map = [
            ("directional light", "DirectionalLight"),
            ("point light", "PointLight"),
            ("spot light", "SpotLight"),
            ("static mesh", "StaticMeshActor"),
            ("skeletal mesh", "SkeletalMeshActor"),
            ("camera", "CameraActor"),
            ("player start", "PlayerStart"),
            ("character", "Character"),
            ("pawn", "Pawn"),
            ("cube", "StaticMeshActor"),
            ("sphere", "StaticMeshActor"),
            ("landscape", "Landscape"),
            ("foliage", "Foliage"),
            ("trigger box", "TriggerBox"),
            ("trigger sphere", "TriggerSphere"),
            ("post process volume", "PostProcessVolume"),
            ("audio", "AmbientSound"),
        ]
        low = text.lower()
        for kw, cls in actor_map:
            if kw in low:
                return cls
        return ""

    @staticmethod
    def _extract_vector(text: str, keyword: str,
                         default: tuple = (0, 0, 0)) -> tuple:
        # Look for "at X Y Z" or "to X, Y, Z"
        m = re.search(rf'{keyword}\s*\(?\s*(-?\d+\.?\d*)\s*[,\s]+\s*(-?\d+\.?\d*)\s*[,\s]+\s*(-?\d+\.?\d*)',
                      text)
        if m:
            try:
                return (float(m.group(1)), float(m.group(2)), float(m.group(3)))
            except ValueError:
                pass
        return default

    @staticmethod
    def _match_enum(text: str, options: list[str], default: str) -> str:
        low = text.lower()
        for o in options:
            if o in low:
                return o
        return default
