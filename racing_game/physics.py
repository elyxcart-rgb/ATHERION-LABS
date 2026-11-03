"""Realistic car physics engine for the racing game.

Implements a simplified but convincing vehicle dynamics model including:
- Tire friction circle with lateral and longitudinal grip
- Weight transfer during braking/acceleration and cornering
- Aerodynamic drag and downforce
- Engine torque curve with RPM simulation
- Gearbox with automatic and manual modes
- Suspension spring-damper model
- Collision response with track boundaries
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAVITY = 9.81          # m/s^2
AIR_DENSITY = 1.225     # kg/m^3
DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EngineProfile:
    """Engine torque curve defined by (RPM, torque_Nm) control points."""
    max_rpm: float = 7000.0
    idle_rpm: float = 800.0
    redline_rpm: float = 7500.0
    # (rpm, torque) pairs — torque at intermediate RPMs is linearly interpolated
    torque_curve: list[tuple[float, float]] = field(default_factory=lambda: [
        (800, 120.0),
        (2000, 200.0),
        (3500, 280.0),
        (5000, 260.0),
        (6000, 220.0),
        (7000, 180.0),
    ])

    def torque_at(self, rpm: float) -> float:
        """Return engine torque (Nm) at the given RPM via piecewise linear interp."""
        rpm = max(self.idle_rpm, min(rpm, self.max_rpm))
        curve = self.torque_curve
        if rpm <= curve[0][0]:
            return curve[0][1]
        if rpm >= curve[-1][0]:
            return curve[-1][1]
        for i in range(len(curve) - 1):
            r0, t0 = curve[i]
            r1, t1 = curve[i + 1]
            if r0 <= rpm <= r1:
                t = (rpm - r0) / (r1 - r0)
                return t0 + t * (t1 - t0)
        return curve[-1][1]


@dataclass
class GearboxProfile:
    """Gearbox with fixed ratios and an optional final drive ratio."""
    # Gear ratios: index 0 = 1st gear, …  N = top gear
    gear_ratios: list[float] = field(default_factory=lambda: [
        3.60,  # 1st
        2.40,  # 2nd
        1.75,  # 3rd
        1.30,  # 4th
        1.00,  # 5th
        0.80,  # 6th
    ])
    final_drive: float = 3.42
    reverse_ratio: float = 3.20
    shift_time: float = 0.15  # seconds to complete a shift

    @property
    def num_gears(self) -> int:
        return len(self.gear_ratios)


@dataclass
class TireProfile:
    """Tire parameters that define the friction circle."""
    grip_coefficient: float = 1.05       # lateral grip multiplier
    rolling_resistance: float = 0.015
    radius: float = 0.33                 # metres (≈ 13 inch rim + tyre)
    width: float = 0.225                 # metres


@dataclass
class AeroProfile:
    """Aerodynamic coefficients."""
    drag_coefficient: float = 0.35
    frontal_area: float = 2.2            # m^2
    downforce_coefficient: float = 0.12  # total (front + rear)


@dataclass
class SuspensionProfile:
    """Simple spring-damper suspension model."""
    spring_rate: float = 35000.0   # N/m
    damping_ratio: float = 0.7
    travel: float = 0.12           # metres
    ride_height: float = 0.15      # metres


@dataclass
class CarPhysicsParams:
    """Complete set of physical parameters for one car model."""
    name: str = "Default Car"
    mass: float = 1400.0           # kg (curb weight)
    wheelbase: float = 2.55        # m
    track_width: float = 1.55      # m
    cg_height: float = 0.45        # m – centre of gravity height
    weight_distribution: float = 0.55  # fraction of weight on front axle
    engine: EngineProfile = field(default_factory=EngineProfile)
    gearbox: GearboxProfile = field(default_factory=GearboxProfile)
    tires: TireProfile = field(default_factory=TireProfile)
    aero: AeroProfile = field(default_factory=AeroProfile)
    suspension: SuspensionProfile = field(default_factory=SuspensionProfile)
    max_steer_angle: float = 32.0  # degrees at wheels


# ---------------------------------------------------------------------------
# CarPhysics — runtime state + integration
# ---------------------------------------------------------------------------

class CarPhysics:
    """Simulates the physics of a single car each frame.

    Public attributes (read by the rendering layer):
        x, y, z         – world position (Panda3D Y-up: x=lateral, y=up, z=forward)
        heading          – radians, 0 = +Z
        speed            – scalar m/s along the car's forward axis
        rpm              – current engine RPM
        gear             – current gear (0-based; -1 = reverse)
        steer_angle      – current steering angle in radians
        throttle         – 0.0 – 1.0
        brake            – 0.0 – 1.0
        handbrake        – 0.0 – 1.0
        lateral_g        – lateral acceleration in G
        longitudinal_g   – longitudinal acceleration in G
    """

    def __init__(self, params: CarPhysicsParams | None = None):
        self.params = params or CarPhysicsParams()
        # Position / orientation
        self.x: float = 0.0
        self.y: float = 0.0
        self.z: float = 0.0
        self.heading: float = 0.0  # radians
        # Velocity components in car-local frame
        self._vx: float = 0.0     # lateral (right is +)
        self._vz: float = 0.0     # forward is +
        self._vz_global: float = 0.0
        # Engine / drivetrain
        self.rpm: float = self.params.engine.idle_rpm
        self.gear: int = 0
        self._shift_timer: float = 0.0
        self._clutch: float = 1.0
        # Inputs (set each frame)
        self.throttle: float = 0.0
        self.brake: float = 0.0
        self.handbrake: float = 0.0
        self.steer_input: float = 0.0  # -1 … +1
        # Derived
        self.speed: float = 0.0
        self.steer_angle: float = 0.0
        self.lateral_g: float = 0.0
        self.longitudinal_g: float = 0.0
        self._prev_vz: float = 0.0
        self._prev_vx: float = 0.0
        # Wheel spin for visual FX
        self.wheel_spin: float = 0.0

    # -- helpers -----------------------------------------------------------

    @property
    def speed_kmh(self) -> float:
        return self.speed * 3.6

    @property
    def is_reversing(self) -> bool:
        return self.gear < 0

    # -- reset -------------------------------------------------------------

    def reset(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, heading: float = 0.0) -> None:
        self.x, self.y, self.z = x, y, z
        self.heading = heading
        self._vx = self._vz = self._vz_global = 0.0
        self.rpm = self.params.engine.idle_rpm
        self.gear = 0
        self.throttle = self.brake = self.handbrake = 0.0
        self.steer_input = 0.0
        self.speed = 0.0
        self.steer_angle = 0.0
        self.wheel_spin = 0.0

    # -- main update -------------------------------------------------------

    def update(self, dt: float) -> None:
        """Advance the physics simulation by *dt* seconds."""
        p = self.params
        p_gear = p.gearbox
        p_tire = p.tires
        p_aero = p.aero
        p_engine = p.engine

        # --- Steering ---------------------------------------------------
        target_steer = self.steer_input * p.max_steer_angle * DEG_TO_RAD
        # Speed-sensitive steering: reduce at high speed
        speed_factor = max(0.3, 1.0 - self.speed / 60.0)
        target_steer *= speed_factor
        # Smooth steering
        steer_rate = 4.0
        self.steer_angle += (target_steer - self.steer_angle) * min(1.0, steer_rate * dt)

        # --- Drivetrain -------------------------------------------------
        self._shift_timer = max(0.0, self._shift_timer - dt)

        if self._shift_timer > 0.0:
            self._clutch = 0.0
        else:
            self._clutch = min(1.0, self._clutch + dt / 0.05)

        # Auto gear selection
        if self._shift_timer <= 0.0:
            self._auto_shift()

        # Engine torque
        engine_torque = p_engine.torque_at(self.rpm) * self.throttle
        # Transmission torque to wheels
        if self.gear >= 0:
            ratio = p_gear.gear_ratios[self.gear] * p_gear.final_drive
        else:
            ratio = p_gear.reverse_ratio * p_gear.final_drive
        wheel_torque = engine_torque * ratio * self._clutch

        # --- Forces (car-local frame) ------------------------------------
        # Drag
        v_total = math.hypot(self._vx, self._vz)
        drag_force = 0.5 * AIR_DENSITY * p_aero.drag_coefficient * p_aero.frontal_area * v_total * v_total
        drag_lateral = -drag_force * (self._vx / max(v_total, 0.01))
        drag_forward = -drag_force * (self._vz / max(v_total, 0.01))

        # Downforce
        downforce = 0.5 * AIR_DENSITY * p_aero.downforce_coefficient * p_aero.frontal_area * self._vz * self._vz
        effective_weight = (p.mass * GRAVITY + downforce)

        # Rolling resistance
        rolling = -p_tire.rolling_resistance * effective_weight * (1.0 if self._vz >= 0 else -1.0)

        # Traction (longitudinal)
        traction = wheel_torque / p_tire.radius if self._vz >= 0 or self.gear < 0 else 0.0
        if self.gear < 0 and self._vz < 0:
            traction = -abs(wheel_torque / p_tire.radius)

        # Brake force
        brake_force = 0.0
        total_brake = max(self.brake, self.handbrake * 0.9)
        if total_brake > 0.0:
            max_brake = effective_weight * 1.2  # up to 1.2 G deceleration
            brake_force = -total_brake * max_brake * (1.0 if self._vz > 0 else -1.0)

        # Net forward force
        net_forward = traction + drag_forward + rolling + brake_force

        # Lateral friction (tire grip limit)
        grip_limit = p_tire.grip_coefficient * effective_weight
        # Centripetal accel from steering
        if abs(self.steer_angle) > 0.001 and abs(self._vz) > 0.5:
            turn_radius = p.wheelbase / math.tan(abs(self.steer_angle))
            centripetal = p.mass * self._vz * self._vz / max(turn_radius, 1.0)
        else:
            centripetal = 0.0

        # Lateral grip force opposes sliding
        if abs(self._vx) > 0.01:
            lateral_friction = -math.copysign(min(abs(self._vx) * p.mass * 8.0, grip_limit), self._vx)
        else:
            lateral_friction = 0.0

        # Handbrake: lock rear wheels → reduce lateral grip dramatically
        if self.handbrake > 0.5:
            lateral_friction *= 0.3
            grip_limit *= 0.3

        net_lateral = lateral_friction + drag_lateral

        # --- Integrate velocities (car-local) ----------------------------
        self._vz += (net_forward / p.mass) * dt
        self._vx += (net_lateral / p.mass) * dt

        # Clamp lateral speed so it can't exceed grip
        max_lateral = grip_limit / p.mass * dt * 10.0
        self._vx = max(-max_lateral, min(max_lateral, self._vx))

        # --- Update global position --------------------------------------
        cos_h = math.cos(self.heading)
        sin_h = math.sin(self.heading)
        # Car local Z is forward, local X is right
        global_vz = self._vz * cos_h - self._vx * sin_h
        global_vx = self._vz * sin_h + self._vx * cos_h

        self.x += global_vx * dt
        self.z += global_vz * dt

        # --- Heading change from steering --------------------------------
        if abs(self._vz) > 0.1:
            angular_vel = self._vz * math.tan(self.steer_angle) / p.wheelbase
            self.heading += angular_vel * dt

        # Normalize heading to [0, 2π)
        self.heading %= (2 * math.pi)

        # --- Speed & accelerations ---------------------------------------
        self.speed = math.hypot(self._vx, self._vz)
        self._vz_global = global_vz

        # Accelerations for HUD
        self.longitudinal_g = (self._vz - self._prev_vz) / max(dt, 0.001) / GRAVITY
        self.lateral_g = (self._vx - self._prev_vx) / max(dt, 0.001) / GRAVITY
        self._prev_vz = self._vz
        self._prev_vx = self._vx

        # --- Wheel spin visual -------------------------------------------
        if self._vz > 0.5:
            wheel_rps = self._vz / (2 * math.pi * p_tire.radius)
            self.wheel_spin += wheel_rps * dt * 2 * math.pi
        else:
            self.wheel_spin *= 0.9  # slow down when stopped

    # -- automatic shifting ------------------------------------------------

    def _auto_shift(self) -> None:
        p = self.params
        p_gear = p.gearbox
        if self.gear < 0:
            return

        # Up-shift near redline
        if self.rpm >= p_gear.redline_rpm * 0.95 and self.gear < p_gear.num_gears - 1:
            self.gear += 1
            self._shift_timer = p_gear.shift_time
            return

        # Down-shift if RPM drops too low
        if self.gear > 0 and self.rpm < p_gear.idle_rpm * 1.5:
            self.gear -= 1
            self._shift_timer = p_gear.shift_time
            return

    # -- manual shift helpers ----------------------------------------------

    def shift_up(self) -> None:
        if self._shift_timer > 0.0:
            return
        if self.gear < self.params.gearbox.num_gears - 1:
            self.gear += 1
            self._shift_timer = self.params.gearbox.shift_time

    def shift_down(self) -> None:
        if self._shift_timer > 0.0:
            return
        if self.gear > 0:
            self.gear -= 1
            self._shift_timer = self.params.gearbox.shift_time

    # -- collision with walls ---------------------------------------------

    def apply_collision_response(self, normal_x: float, normal_z: float, penetration: float) -> None:
        """Push the car out of a wall and reflect velocity along the wall normal."""
        # Separate
        self.x += normal_x * penetration
        self.z += normal_z * penetration
        # Reflect velocity
        dot = self._vx * normal_x + self._vz * normal_z
        if dot < 0:
            restitution = 0.4
            self._vx -= (1 + restitution) * dot * normal_x
            self._vz -= (1 + restitution) * dot * normal_z
            self.speed = math.hypot(self._vx, self._vz)
