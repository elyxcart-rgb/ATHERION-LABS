"""Multiple customizable car models for the racing game.

Each car is defined as a ``CarSpec`` dataclass containing its physics
parameters, visual colours, and a short description.  Procedural mesh
generators create the 3D model at runtime (no external assets required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from panda3d.core import NodePath, GeomNode, Geom, GeomVertexData, GeomVertexFormat, GeomVertexWriter, GeomTriangles, Vec4

from .physics import (
    CarPhysicsParams, EngineProfile, GearboxProfile,
    TireProfile, AeroProfile, SuspensionProfile,
)


# ---------------------------------------------------------------------------
# Car specification
# ---------------------------------------------------------------------------

@dataclass
class CarSpec:
    """Full specification of a car model (physics + visual metadata)."""
    id: str
    name: str
    description: str
    params: CarPhysicsParams
    primary_color: tuple[int, int, int] = (200, 30, 30)
    accent_color: tuple[int, int, int] = (40, 40, 40)
    # Customisation sliders (0-1) set by the player
    colour_index: int = 0
    upgrade_engine: int = 0   # 0 = stock, 1 = stage-1, 2 = stage-2
    upgrade_tires: int = 0
    upgrade_aero: int = 0

    # Colour palette
    COLOURS: list[tuple[int, int, int]] = field(default_factory=lambda: [
        (200, 30, 30),    # Red
        (30, 30, 200),    # Blue
        (30, 180, 30),    # Green
        (255, 200, 0),    # Yellow
        (255, 140, 0),    # Orange
        (180, 30, 180),   # Purple
        (255, 255, 255),  # White
        (30, 30, 30),     # Black
        (0, 200, 200),    # Cyan
        (255, 100, 100),  # Pink
    ])

    def apply_colour(self, index: int) -> None:
        self.colour_index = index % len(self.COLOURS)
        self.primary_color = self.COLOURS[self.colour_index]

    def get_effective_params(self) -> CarPhysicsParams:
        """Return params with upgrades applied."""
        p = self.params
        # Engine upgrade: +5% torque per stage
        stage_mult = 1.0 + self.upgrade_engine * 0.05
        new_curve = [(r, t * stage_mult) for r, t in p.engine.torque_curve]
        p.engine = EngineProfile(
            max_rpm=p.engine.max_rpm,
            idle_rpm=p.engine.idle_rpm,
            redline_rpm=p.engine.redline_rpm,
            torque_curve=new_curve,
        )
        # Tire upgrade: +8% grip per stage
        p.tires = TireProfile(
            grip_coefficient=p.tires.grip_coefficient * (1.0 + self.upgrade_tires * 0.08),
            rolling_resistance=p.tires.rolling_resistance * (1.0 - self.upgrade_tires * 0.03),
            radius=p.tires.radius,
            width=p.tires.width,
        )
        # Aero upgrade: +10% downforce per stage
        p.aero = AeroProfile(
            drag_coefficient=p.aero.drag_coefficient * (1.0 + self.upgrade_aero * 0.02),
            frontal_area=p.aero.frontal_area,
            downforce_coefficient=p.aero.downforce_coefficient * (1.0 + self.upgrade_aero * 0.10),
        )
        return p


# ---------------------------------------------------------------------------
# Procedural mesh builder
# ---------------------------------------------------------------------------

def build_car_mesh(spec: CarSpec) -> NodePath:
    """Create a simple boxy car model procedurally (no external assets).

    Returns a ``NodePath`` parented to nothing that can be reparented to
    the scene graph.
    """
    r, g, b = spec.primary_color
    ar, ag, ab = spec.accent_color

    root = NodePath(spec.id)

    # -- Body -----------------------------------------------------------
    body = _make_box(2.0, 0.6, 4.2, r / 255.0, g / 255.0, b / 255.0)
    body.reparentTo(root)
    body.setPos(0, 0.45, 0)

    # -- Cabin (windshield area) ----------------------------------------
    cabin = _make_box(1.7, 0.5, 2.0, ar / 255.0, ag / 255.0, ab / 255.0)
    cabin.reparentTo(root)
    cabin.setPos(0, 0.85, -0.3)

    # -- Hood bulge -----------------------------------------------------
    hood = _make_box(1.6, 0.15, 1.2, min(r + 20, 255) / 255.0, min(g + 20, 255) / 255.0, min(b + 20, 255) / 255.0)
    hood.reparentTo(root)
    hood.setPos(0, 0.73, 1.1)

    # -- Spoiler --------------------------------------------------------
    spoiler = _make_box(1.8, 0.08, 0.35, ar / 255.0, ag / 255.0, ab / 255.0)
    spoiler.reparentTo(root)
    spoiler.setPos(0, 0.95, -1.9)

    # Spoiler uprights
    for x_off in (-0.6, 0.6):
        upright = _make_box(0.08, 0.3, 0.08, ar / 255.0, ag / 255.0, ab / 255.0)
        upright.reparentTo(root)
        upright.setPos(x_off, 0.80, -1.9)

    # -- Wheels ---------------------------------------------------------
    wheel_positions = [
        (-0.85, 0.25, 1.3),
        (0.85, 0.25, 1.3),
        (-0.85, 0.25, -1.2),
        (0.85, 0.25, -1.2),
    ]
    for wx, wy, wz in wheel_positions:
        wheel = _make_cylinder(0.15, 0.25, 20, 0.1, 0.1, 0.1)
        wheel.reparentTo(root)
        wheel.setPos(wx, wy, wz)
        wheel.setHpr(0, 0, 90)

    # -- Headlights -----------------------------------------------------
    for x_off in (-0.7, 0.7):
        light = _make_box(0.2, 0.12, 0.08, 1.0, 1.0, 0.8)
        light.reparentTo(root)
        light.setPos(x_off, 0.48, 2.1)

    # -- Tail lights ----------------------------------------------------
    for x_off in (-0.7, 0.7):
        tl = _make_box(0.2, 0.12, 0.08, 0.8, 0.05, 0.05)
        tl.reparentTo(root)
        tl.setPos(x_off, 0.48, -2.1)

    return root


def _make_box(w: float, h: float, d: float, r: float, g: float, b: float) -> NodePath:
    """Create a coloured box mesh."""
    fmt = GeomVertexFormat.getV3n3cpt1()
    vdata = GeomVertexData("box", fmt, Geom.UHStatic)

    hw, hh, hd = w / 2, h / 2, d / 2

    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")
    texcoord = GeomVertexWriter(vdata, "texcoord")

    # 8 vertices of the box
    verts = [
        (-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd),
        (-hw, -hh, hd),  (hw, -hh, hd),  (hw, hh, hd),  (-hw, hh, hd),
    ]
    normals = [
        (0, 0, -1), (0, 0, -1), (0, 0, -1), (0, 0, -1),
        (0, 0, 1),  (0, 0, 1),  (0, 0, 1),  (0, 0, 1),
    ]
    uvs = [
        (0, 0), (1, 0), (1, 1), (0, 1),
        (0, 0), (1, 0), (1, 1), (0, 1),
    ]

    for v, n, uv in zip(verts, normals, uvs):
        vertex.addData3(*v)
        normal.addData3(*n)
        color.addData4(r, g, b, 1.0)
        texcoord.addData2(*uv)

    # 6 faces × 2 triangles
    faces = [
        (0, 1, 2, 3),  # front
        (5, 4, 7, 6),  # back
        (4, 0, 3, 7),  # left
        (1, 5, 6, 2),  # right
        (3, 2, 6, 7),  # top
        (4, 5, 1, 0),  # bottom
    ]

    tris = GeomTriangles(Geom.UHStatic)
    for a, b2, c, d2 in faces:
        tris.addVertices(a, b2, c)
        tris.addVertices(a, c, d2)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("box")
    node.addGeom(geom)
    return NodePath(node)


def _make_cylinder(radius: float, height: float, segments: int,
                   r: float, g: float, b: float) -> NodePath:
    """Create a simple coloured cylinder."""
    fmt = GeomVertexFormat.getV3n3cpt1()
    vdata = GeomVertexData("cyl", fmt, Geom.UHStatic)

    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")
    texcoord = GeomVertexWriter(vdata, "texcoord")

    import math
    hh = height / 2
    for i in range(segments + 1):
        angle = 2 * math.pi * i / segments
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        # Bottom vertex
        vertex.addData3(x, y, -hh)
        normal.addData3(math.cos(angle), math.sin(angle), 0)
        color.addData4(r, g, b, 1.0)
        texcoord.addData2(i / segments, 0)
        # Top vertex
        vertex.addData3(x, y, hh)
        normal.addData3(math.cos(angle), math.sin(angle), 0)
        color.addData4(r, g, b, 1.0)
        texcoord.addData2(i / segments, 1)

    tris = GeomTriangles(Geom.UHStatic)
    for i in range(segments):
        b0 = i * 2
        t0 = i * 2 + 1
        b1 = (i + 1) * 2
        t1 = (i + 1) * 2 + 1
        tris.addVertices(b0, b1, t1)
        tris.addVertices(b0, t1, t0)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("cyl")
    node.addGeom(geom)
    return NodePath(node)


# ---------------------------------------------------------------------------
# Car catalogue
# ---------------------------------------------------------------------------

def get_car_catalogue() -> list[CarSpec]:
    """Return the list of all available car models."""
    return [
        CarSpec(
            id="street_gt",
            name="Street GT",
            description="Balanced sports car — great for beginners.",
            params=CarPhysicsParams(
                name="Street GT",
                mass=1350,
                wheelbase=2.50,
                track_width=1.52,
                cg_height=0.44,
                weight_distribution=0.54,
                engine=EngineProfile(max_rpm=7200, idle_rpm=900, redline_rpm=7500,
                                     torque_curve=[(900, 130), (2200, 210), (3800, 270), (5200, 250), (6200, 210), (7200, 170)]),
                gearbox=GearboxProfile(gear_ratios=[3.50, 2.35, 1.72, 1.28, 0.98, 0.78], final_drive=3.40),
                tires=TireProfile(grip_coefficient=1.02),
                aero=AeroProfile(drag_coefficient=0.34, frontal_area=2.15, downforce_coefficient=0.10),
                max_steer_angle=30.0,
            ),
            primary_color=(200, 30, 30),
        ),
        CarSpec(
            id="turbo_s",
            name="Turbo S",
            description="High-torque turbocharged coupe — powerful and agile.",
            params=CarPhysicsParams(
                name="Turbo S",
                mass=1420,
                wheelbase=2.58,
                track_width=1.58,
                cg_height=0.42,
                weight_distribution=0.56,
                engine=EngineProfile(max_rpm=7000, idle_rpm=850, redline_rpm=7200,
                                     torque_curve=[(850, 150), (2000, 260), (3500, 320), (5000, 300), (6000, 250), (7000, 200)]),
                gearbox=GearboxProfile(gear_ratios=[3.60, 2.40, 1.75, 1.30, 1.00, 0.80], final_drive=3.50),
                tires=TireProfile(grip_coefficient=1.08),
                aero=AeroProfile(drag_coefficient=0.36, frontal_area=2.20, downforce_coefficient=0.13),
                max_steer_angle=32.0,
            ),
            primary_color=(30, 30, 200),
        ),
        CarSpec(
            id="rally_x",
            name="Rally X",
            description="All-wheel-drive rally machine — excels on loose surfaces.",
            params=CarPhysicsParams(
                name="Rally X",
                mass=1380,
                wheelbase=2.52,
                track_width=1.55,
                cg_height=0.48,
                weight_distribution=0.52,
                engine=EngineProfile(max_rpm=7500, idle_rpm=950, redline_rpm=7800,
                                     torque_curve=[(950, 140), (2500, 230), (4000, 290), (5500, 270), (6500, 230), (7500, 190)]),
                gearbox=GearboxProfile(gear_ratios=[3.70, 2.50, 1.80, 1.35, 1.05, 0.85], final_drive=3.60),
                tires=TireProfile(grip_coefficient=0.95),
                aero=AeroProfile(drag_coefficient=0.38, frontal_area=2.25, downforce_coefficient=0.08),
                max_steer_angle=35.0,
            ),
            primary_color=(30, 180, 30),
        ),
        CarSpec(
            id="super_v",
            name="Super V12",
            description="V12 supercar — top speed monster with premium handling.",
            params=CarPhysicsParams(
                name="Super V12",
                mass=1500,
                wheelbase=2.62,
                track_width=1.60,
                cg_height=0.40,
                weight_distribution=0.57,
                engine=EngineProfile(max_rpm=8000, idle_rpm=1000, redline_rpm=8500,
                                     torque_curve=[(1000, 160), (2500, 280), (4000, 350), (5500, 330), (6500, 280), (8000, 220)]),
                gearbox=GearboxProfile(gear_ratios=[3.80, 2.60, 1.90, 1.40, 1.08, 0.82], final_drive=3.35),
                tires=TireProfile(grip_coefficient=1.12),
                aero=AeroProfile(drag_coefficient=0.32, frontal_area=2.10, downforce_coefficient=0.16),
                max_steer_angle=28.0,
            ),
            primary_color=(255, 200, 0),
        ),
        CarSpec(
            id="drift_king",
            name="Drift King",
            description="Rear-wheel-drive drift specialist — sideways is the only way.",
            params=CarPhysicsParams(
                name="Drift King",
                mass=1300,
                wheelbase=2.48,
                track_width=1.50,
                cg_height=0.43,
                weight_distribution=0.53,
                engine=EngineProfile(max_rpm=7800, idle_rpm=900, redline_rpm=8000,
                                     torque_curve=[(900, 135), (2200, 220), (3800, 285), (5200, 265), (6200, 225), (7800, 175)]),
                gearbox=GearboxProfile(gear_ratios=[3.55, 2.38, 1.74, 1.30, 1.00, 0.78], final_drive=3.45),
                tires=TireProfile(grip_coefficient=0.88),  # lower grip for easier drifting
                aero=AeroProfile(drag_coefficient=0.35, frontal_area=2.18, downforce_coefficient=0.09),
                max_steer_angle=38.0,
            ),
            primary_color=(180, 30, 180),
        ),
    ]
