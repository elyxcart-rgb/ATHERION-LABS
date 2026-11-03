"""Diverse racing tracks for the racing game.

Tracks are defined as sequences of control points that form a closed loop.
The track builder creates the road surface, barriers, and scenery procedurally.
Each track has a name, difficulty, length, and recommended car class.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from panda3d.core import (
    NodePath, GeomNode, Geom, GeomVertexData, GeomVertexFormat,
    GeomVertexWriter, GeomTriangles, Vec4, Vec3,
    CardMaker, TextureStage, TextNode,
)

from .physics import CarPhysics


# ---------------------------------------------------------------------------
# Track definition
# ---------------------------------------------------------------------------

@dataclass
class TrackPoint:
    """A point on the track centre-line."""
    x: float
    z: float
    width: float = 12.0  # road width at this point
    banking: float = 0.0  # degrees of bank


@dataclass
class TrackSpec:
    """Complete specification for a racing track."""
    id: str
    name: str
    description: str
    difficulty: str  # "Easy", "Medium", "Hard", "Expert"
    laps: int = 3
    points: list[TrackPoint] = field(default_factory=list)

    # Scenery colours
    ground_color: tuple[float, float, float] = (0.15, 0.35, 0.12)
    road_color: tuple[float, float, float] = (0.25, 0.25, 0.28)
    barrier_color: tuple[float, float, float] = (0.7, 0.7, 0.7)
    sky_color: tuple[float, float, float] = (0.45, 0.65, 0.95)


# ---------------------------------------------------------------------------
# Track catalogue
# ---------------------------------------------------------------------------

def _circle_points(cx: float, cz: float, radius: float, n: int, width: float = 12.0) -> list[TrackPoint]:
    pts = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        pts.append(TrackPoint(cx + radius * math.cos(angle), cz + radius * math.sin(angle), width))
    return pts


def _figure_eight_points(cx: float, cz: float, radius: float, n: int, width: float = 11.0) -> list[TrackPoint]:
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = cx + radius * math.sin(t)
        z = cz + radius * math.sin(t) * math.cos(t)
        pts.append(TrackPoint(x, z, width))
    return pts


def _oval_points(cx: float, cz: float, rx: float, rz: float, n: int, width: float = 13.0) -> list[TrackPoint]:
    pts = []
    for i in range(n):
        angle = 2 * math.pi * i / n
        pts.append(TrackPoint(cx + rx * math.cos(angle), cz + rz * math.sin(angle), width))
    return pts


def _serpentine_points(start_x: float, start_z: float, n: int, width: float = 10.0) -> list[TrackPoint]:
    pts = []
    x, z = start_x, start_z
    for i in range(n):
        direction = 1 if (i // 4) % 2 == 0 else -1
        pts.append(TrackPoint(x, z, width))
        if i % 4 == 0:
            x += 40 * direction
        elif i % 4 == 1:
            z += 30
        elif i % 4 == 2:
            x -= 40 * direction
        else:
            z += 30
    return pts


def _monaco_points() -> list[TrackPoint]:
    """Tight street-circuit inspired by Monaco."""
    return [
        TrackPoint(0, 0, 8), TrackPoint(30, 0, 8), TrackPoint(40, 15, 8),
        TrackPoint(35, 35, 8), TrackPoint(15, 45, 8), TrackPoint(-10, 40, 8),
        TrackPoint(-25, 25, 8), TrackPoint(-30, 5, 8), TrackPoint(-15, -10, 8),
        TrackPoint(10, -15, 8), TrackPoint(25, -5, 8),
    ]


def _nurburgring_points() -> list[TrackPoint]:
    """Long, flowing GP-style circuit."""
    base = _circle_points(0, 0, 120, 32, 14)
    for i, pt in enumerate(base):
        offset = 20 * math.sin(i * 0.5) + 10 * math.cos(i * 0.3)
        pt.x += offset
        pt.z += 15 * math.cos(i * 0.4)
        pt.width = 12 + 4 * math.sin(i * 0.2)
    return base


def _desert_sprint_points() -> list[TrackPoint]:
    """Fast desert circuit with long straights and sweeping curves."""
    pts = [
        TrackPoint(0, 0, 16), TrackPoint(80, 0, 16), TrackPoint(120, 30, 14),
        TrackPoint(100, 70, 12), TrackPoint(50, 90, 12), TrackPoint(-10, 80, 14),
        TrackPoint(-40, 50, 12), TrackPoint(-60, 20, 14), TrackPoint(-30, -10, 14),
    ]
    return pts


def _mountain_pass_points() -> list[TrackPoint]:
    """Winding mountain road with elevation changes."""
    pts = []
    for i in range(40):
        t = 2 * math.pi * i / 40
        x = 100 * math.cos(t) + 30 * math.sin(3 * t)
        z = 80 * math.sin(t) + 25 * math.cos(2 * t)
        w = 10 + 3 * math.sin(t * 2)
        pts.append(TrackPoint(x, z, w))
    return pts


def get_track_catalogue() -> list[TrackSpec]:
    """Return the list of all available tracks."""
    return [
        TrackSpec(
            id="sunrise_circuit",
            name="Sunrise Circuit",
            description="A gentle oval circuit perfect for learning the ropes.",
            difficulty="Easy",
            laps=3,
            points=_oval_points(0, 0, 100, 60, 24),
            ground_color=(0.18, 0.40, 0.14),
            sky_color=(0.50, 0.70, 0.95),
        ),
        TrackSpec(
            id="city_rush",
            name="City Rush",
            description="Tight urban circuit with narrow streets and sharp turns.",
            difficulty="Medium",
            laps=4,
            points=_monaco_points(),
            ground_color=(0.20, 0.20, 0.22),
            sky_color=(0.40, 0.55, 0.80),
        ),
        TrackSpec(
            id="desert_sprint",
            name="Desert Sprint",
            description="High-speed desert track with wide straights and sweeping curves.",
            difficulty="Medium",
            laps=3,
            points=_desert_sprint_points(),
            ground_color=(0.55, 0.45, 0.25),
            sky_color=(0.70, 0.80, 0.95),
        ),
        TrackSpec(
            id="mountain_pass",
            name="Mountain Pass",
            description="Winding alpine road with hairpin turns and elevation changes.",
            difficulty="Hard",
            laps=3,
            points=_mountain_pass_points(),
            ground_color=(0.25, 0.38, 0.18),
            sky_color=(0.55, 0.68, 0.90),
        ),
        TrackSpec(
            id="green_oval",
            name="Green Oval",
            description="Classic superspeedway oval — pure speed and drafting.",
            difficulty="Easy",
            laps=5,
            points=_oval_points(0, 0, 140, 80, 30, 18),
            ground_color=(0.15, 0.35, 0.12),
            sky_color=(0.45, 0.65, 0.95),
        ),
        TrackSpec(
            id="ring_master",
            name="Ring Master",
            description="Long, flowing GP circuit inspired by the Nürburgring.",
            difficulty="Hard",
            laps=3,
            points=_nurburgring_points(),
            ground_color=(0.20, 0.32, 0.15),
            sky_color=(0.50, 0.62, 0.88),
        ),
        TrackSpec(
            id="figure_eight",
            name="Figure Eight",
            description="Crossing track — watch out for the intersection!",
            difficulty="Expert",
            laps=3,
            points=_figure_eight_points(0, 0, 80, 28, 11),
            ground_color=(0.18, 0.30, 0.14),
            sky_color=(0.48, 0.60, 0.85),
        ),
        TrackSpec(
            id="serpentine",
            name="Serpentine",
            description="Zigzag challenge — only the best steering can win here.",
            difficulty="Expert",
            laps=2,
            points=_serpentine_points(-60, -60, 32, 10),
            ground_color=(0.22, 0.36, 0.16),
            sky_color=(0.52, 0.66, 0.92),
        ),
    ]


# ---------------------------------------------------------------------------
# Track builder — procedural mesh
# ---------------------------------------------------------------------------

class TrackBuilder:
    """Builds the 3D track geometry from a TrackSpec."""

    def __init__(self, spec: TrackSpec):
        self.spec = spec
        self.node: NodePath | None = None
        self.barrier_node: NodePath | None = None
        self.ground_node: NodePath | None = None
        self.checkpoint_positions: list[tuple[float, float, float]] = []
        self._build()

    def _build(self) -> None:
        pts = self.spec.points
        if len(pts) < 3:
            return

        # Compute tangents and normals for each point
        n = len(pts)
        self._tangents: list[tuple[float, float]] = []
        self._normals: list[tuple[float, float]] = []

        for i in range(n):
            prev = pts[(i - 1) % n]
            nxt = pts[(i + 1) % n]
            dx = nxt.x - prev.x
            dz = nxt.z - prev.z
            length = math.hypot(dx, dz) or 1.0
            self._tangents.append((dx / length, dz / length))
            # Normal = perpendicular to tangent (pointing left)
            self._normals.append((-dz / length, dx / length))

        self._build_road()
        self._build_barriers()
        self._build_ground()
        self._set_checkpoints()

    # -- road surface -----------------------------------------------------

    def _build_road(self) -> None:
        pts = self.spec.points
        n = len(pts)
        fmt = GeomVertexFormat.getV3n3cpt1()
        vdata = GeomVertexData("road", fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")
        texcoord = GeomVertexWriter(vdata, "texcoord")

        r, g, b = self.spec.road_color

        # Centre-line checkpoints
        self._road_centres: list[tuple[float, float]] = []

        for i in range(n):
            pt = pts[i]
            nx, nz = self._normals[i]
            hw = pt.width / 2
            # Left edge
            vertex.addData3(pt.x - nx * hw, 0.05, pt.z - nz * hw)
            normal.addData3(0, 1, 0)
            color.addData4(r, g, b, 1.0)
            texcoord.addData2(0, i / n)
            # Right edge
            vertex.addData3(pt.x + nx * hw, 0.05, pt.z + nz * hw)
            normal.addData3(0, 1, 0)
            color.addData4(r, g, b, 1.0)
            texcoord.addData2(1, i / n)

            self._road_centres.append((pt.x, pt.z))

        tris = GeomTriangles(Geom.UHStatic)
        for i in range(n):
            left = i * 2
            right = i * 2 + 1
            next_left = ((i + 1) % n) * 2
            next_right = ((i + 1) % n) * 2 + 1
            tris.addVertices(left, right, next_right)
            tris.addVertices(left, next_right, next_left)

        # Road markings (centre line)
        fmt2 = GeomVertexFormat.getV3n3cpt1()
        vdata2 = GeomVertexData("markings", fmt2, Geom.UHStatic)
        v2 = GeomVertexWriter(vdata2, "vertex")
        n2 = GeomVertexWriter(vdata2, "normal")
        c2 = GeomVertexWriter(vdata2, "color")
        t2 = GeomVertexWriter(vdata2, "texcoord")

        for i in range(n):
            pt = pts[i]
            # Dashed centre line
            if i % 4 < 2:
                v2.addData3(pt.x, 0.06, pt.z)
                n2.addData3(0, 1, 0)
                c2.addData4(1.0, 1.0, 1.0, 0.8)
                t2.addData2(0.5, 0)

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("road")
        node.addGeom(geom)
        self.node = NodePath(node)

        # Markings node
        mark_tris = GeomTriangles(Geom.UHStatic)
        for i in range(0, len(pts) - 1, 2):
            mark_tris.addVertices(i, i + 1, i + 1)
        geom2 = Geom(vdata2)
        geom2.addPrimitive(mark_tris)
        node2 = GeomNode("markings")
        node2.addGeom(geom2)
        markings = NodePath(node2)
        markings.reparentTo(self.node)

        # Start/finish line
        self._add_start_line()

    def _add_start_line(self) -> None:
        if not self.spec.points or not self.node:
            return
        pt = self.spec.points[0]
        nx, nz = self._normals[0]
        hw = pt.width / 2
        fmt = GeomVertexFormat.getV3n3cpt1()
        vdata = GeomVertexData("start", fmt, Geom.UHStatic)
        v = GeomVertexWriter(vdata, "vertex")
        n = GeomVertexWriter(vdata, "normal")
        c = GeomVertexWriter(vdata, "color")
        t = GeomVertexWriter(vdata, "texcoord")

        w = 1.0
        v.addData3(pt.x - nx * hw, 0.07, pt.z - nz * hw)
        v.addData3(pt.x + nx * hw, 0.07, pt.z + nz * hw)
        v.addData3(pt.x + nx * hw - w * self._tangents[0][0], 0.07, pt.z + nz * hw - w * self._tangents[0][1])
        v.addData3(pt.x - nx * hw - w * self._tangents[0][0], 0.07, pt.z - nz * hw - w * self._tangents[0][1])
        for _ in range(4):
            n.addData3(0, 1, 0)
        for _ in range(2):
            c.addData4(1.0, 1.0, 1.0, 1.0)
        for _ in range(2):
            c.addData4(0.1, 0.1, 0.1, 1.0)
        t.addData2(0, 0); t.addData2(1, 0); t.addData2(1, 1); t.addData2(0, 1)

        tris = GeomTriangles(Geom.UHStatic)
        tris.addVertices(0, 1, 2)
        tris.addVertices(0, 2, 3)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("start")
        node.addGeom(geom)
        start_line = NodePath(node)
        start_line.reparentTo(self.node)

    # -- barriers ---------------------------------------------------------

    def _build_barriers(self) -> None:
        pts = self.spec.points
        n = len(pts)
        fmt = GeomVertexFormat.getV3n3cpt1()
        vdata = GeomVertexData("barrier", fmt, Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        normal = GeomVertexWriter(vdata, "normal")
        color = GeomVertexWriter(vdata, "color")
        texcoord = GeomVertexWriter(vdata, "texcoord")

        r, g, b = self.spec.barrier_color
        barrier_h = 0.8

        for i in range(n):
            pt = pts[i]
            nx, nz = self._normals[i]
            hw = pt.width / 2 + 0.5  # offset from road edge

            # Left barrier
            lx = pt.x - nx * hw
            lz = pt.z - nz * hw
            vertex.addData3(lx, 0, lz)
            vertex.addData3(lx, barrier_h, lz)
            normal.addData3(-nx, 0, -nz)
            normal.addData3(-nx, 0, -nz)
            color.addData4(r, g, b, 1.0)
            color.addData4(r, g, b, 1.0)
            texcoord.addData2(0, 0)
            texcoord.addData2(0, 1)

            # Right barrier
            rx = pt.x + nx * hw
            rz = pt.z + nz * hw
            vertex.addData3(rx, 0, rz)
            vertex.addData3(rx, barrier_h, rz)
            normal.addData3(nx, 0, nz)
            normal.addData3(nx, 0, nz)
            color.addData4(r, g, b, 1.0)
            color.addData4(r, g, b, 1.0)
            texcoord.addData2(1, 0)
            texcoord.addData2(1, 1)

        tris = GeomTriangles(Geom.UHStatic)
        for i in range(n):
            base = i * 4
            next_base = ((i + 1) % n) * 4
            # Left wall
            tris.addVertices(base, base + 1, next_base + 1)
            tris.addVertices(base, next_base + 1, next_base)
            # Right wall
            tris.addVertices(base + 2, base + 3, next_base + 3)
            tris.addVertices(base + 2, next_base + 3, next_base + 2)

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("barrier")
        node.addGeom(geom)
        self.barrier_node = NodePath(node)

    # -- ground plane -----------------------------------------------------

    def _build_ground(self) -> None:
        cm = CardMaker("ground")
        cm.setFrame(-500, 500, -500, 500)
        self.ground_node = NodePath(cm.generate())
        self.ground_node.setP(-90)
        self.ground_node.setY(-0.05)
        r, g, b = self.spec.ground_color
        from panda3d.core import ColorAttrib
        self.ground_node.setColor(r, g, b, 1.0)

    # -- checkpoint positions for lap detection ---------------------------

    def _set_checkpoints(self) -> None:
        pts = self.spec.points
        n = len(pts)
        step = max(1, n // 10)
        for i in range(0, n, step):
            pt = pts[i]
            t = self._tangents[i]
            self.checkpoint_positions.append((pt.x, 0.0, pt.z))

    # -- collision helpers ------------------------------------------------

    def check_wall_collision(self, car_x: float, car_z: float, car_radius: float = 1.2) -> tuple[bool, float, float, float]:
        """Check if the car hits a barrier.

        Returns (hit, normal_x, normal_z, penetration_depth).
        """
        pts = self.spec.points
        n = len(pts)
        for i in range(n):
            pt = pts[i]
            nx, nz = self._normals[i]
            hw = pt.width / 2 + 0.5
            # Distance from car to centre-line
            dx = car_x - pt.x
            dz = car_z - pt.z
            dist_along_normal = dx * nx + dz * nz
            dist_along_tangent = dx * self._tangents[i][0] + dz * self._tangents[i][1]
            # Check if within the segment length
            next_pt = pts[(i + 1) % n]
            seg_len = math.hypot(next_pt.x - pt.x, next_pt.z - pt.z)
            if -car_radius < dist_along_tangent < seg_len + car_radius:
                if abs(dist_along_normal) > hw - car_radius:
                    # Collision!
                    penetration = abs(dist_along_normal) - (hw - car_radius)
                    sign = 1 if dist_along_normal > 0 else -1
                    return True, nx * sign, nz * sign, penetration
        return False, 0, 0, 0

    def is_on_track(self, x: float, z: float) -> bool:
        """Rough check if a point is on or near the road."""
        pts = self.spec.points
        n = len(pts)
        for i in range(n):
            pt = pts[i]
            nx, nz = self._normals[i]
            hw = pt.width / 2 + 1.0
            dx = x - pt.x
            dz = z - pt.z
            dist = abs(dx * nx + dz * nz)
            if dist < hw:
                return True
        return False

    def get_start_position(self) -> tuple[float, float, float]:
        """Return (x, y, z, heading) for the car at the start line."""
        if not self.spec.points:
            return (0, 0, 0, 0)
        pt = self.spec.points[0]
        t = self._tangents[0] if self._tangents else (1, 0)
        heading = math.atan2(t[0], t[1])
        return (pt.x, 0.0, pt.z, heading)

    def get_lap_progress(self, x: float, z: float) -> float:
        """Return 0.0–1.0 progress through the current lap."""
        pts = self.spec.points
        n = len(pts)
        if n < 2:
            return 0.0
        # Find closest segment
        best_dist = float("inf")
        best_idx = 0
        for i in range(n):
            pt = pts[i]
            d = math.hypot(x - pt.x, z - pt.z)
            if d < best_dist:
                best_dist = d
                best_idx = i
        return best_idx / n
