"""Isaac Sim 6/OpenUSD edge for physical pen spawning, attachment, and seating signals."""

from __future__ import annotations

from typing import Any

from cellforge_simulation.physical import PenPose, PhysicalSimulationError


class IsaacPenPhysicsBackend:
    """Thin adapter over OpenUSD/PhysX APIs supplied by a supported Isaac Sim 6 runtime."""

    fidelity = "L2"

    def __init__(self, stage: Any, world: Any | None = None) -> None:
        if stage is None:
            raise PhysicalSimulationError(
                "physical.isaac.stage_missing: an OpenUSD stage is required"
            )
        try:
            from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics
        except ImportError as error:  # pragma: no cover - exercised only in Isaac Sim
            raise RuntimeError(
                "physical.isaac.unavailable: Isaac Sim 6 OpenUSD/PhysX modules are required"
            ) from error
        self._Gf = Gf
        self._Sdf = Sdf
        self._Usd = Usd
        self._UsdGeom = UsdGeom
        self._UsdPhysics = UsdPhysics
        self._stage = stage
        self._world = world
        self._attached: dict[str, str] = {}

    def spawn_pen(self, object_id: str, pose: PenPose) -> str:
        if not object_id or "/" in object_id:
            raise PhysicalSimulationError("physical.object_id.invalid: expected one prim-safe ID")
        path = f"/World/SpawnedProducts/{object_id}"
        if self._stage.GetPrimAtPath(path).IsValid():
            self._stage.RemovePrim(path)
        capsule = self._UsdGeom.Capsule.Define(self._stage, path)
        capsule.CreateAxisAttr("X")
        capsule.CreateRadiusAttr(0.006)
        capsule.CreateHeightAttr(0.128)
        xform = self._UsdGeom.Xformable(capsule.GetPrim())
        xform.AddTranslateOp().Set(
            self._Gf.Vec3d(pose.x_mm / 1000.0, pose.y_mm / 1000.0, pose.z_mm / 1000.0)
        )
        xform.AddRotateZOp().Set(pose.yaw_deg)
        self._UsdPhysics.CollisionAPI.Apply(capsule.GetPrim())
        self._UsdPhysics.RigidBodyAPI.Apply(capsule.GetPrim())
        mass = self._UsdPhysics.MassAPI.Apply(capsule.GetPrim())
        mass.CreateMassAttr(0.018)
        capsule.GetPrim().CreateAttribute(
            "cellforge:runtimeProductId", self._Sdf.ValueTypeNames.String, custom=True
        ).Set(object_id)
        return path

    def set_pen_pose(self, pen_path: str, pose: PenPose) -> None:
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid():
            raise PhysicalSimulationError(f"physical.pen.missing: '{pen_path}' does not exist")
        xform = self._UsdGeom.Xformable(prim)
        xform.ClearXformOpOrder()
        xform.AddTranslateOp().Set(
            self._Gf.Vec3d(pose.x_mm / 1000.0, pose.y_mm / 1000.0, pose.z_mm / 1000.0)
        )
        xform.AddRotateZOp().Set(pose.yaw_deg)

    def attach(self, pen_path: str, tool_path: str = "/World/Robot/GripperTcp") -> str:
        pen = self._stage.GetPrimAtPath(pen_path)
        tool = self._stage.GetPrimAtPath(tool_path)
        if not pen.IsValid() or not tool.IsValid():
            raise PhysicalSimulationError(
                "physical.attach.missing_prim: pen or tool prim is missing"
            )
        joint_path = f"/World/PhysicsJoints/{pen.GetName()}_grasp"
        joint = self._UsdPhysics.FixedJoint.Define(self._stage, joint_path)
        joint.CreateBody0Rel().SetTargets([self._Sdf.Path(tool_path)])
        joint.CreateBody1Rel().SetTargets([self._Sdf.Path(pen_path)])
        self._attached[pen_path] = joint_path
        return joint_path

    def detach(self, pen_path: str) -> None:
        joint_path = self._attached.pop(pen_path, "")
        if joint_path:
            self._stage.RemovePrim(joint_path)

    def is_attached(self, pen_path: str) -> bool:
        joint_path = self._attached.get(pen_path)
        return bool(joint_path and self._stage.GetPrimAtPath(joint_path).IsValid())

    def is_seated(
        self,
        pen_path: str,
        *,
        fixture_center_m: tuple[float, float, float] = (0.55, 0.0, 0.84),
        translation_tolerance_m: float = 0.0005,
    ) -> bool:
        if translation_tolerance_m <= 0:
            raise PhysicalSimulationError("physical.seating.invalid_tolerance: must be positive")
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid() or self.is_attached(pen_path):
            return False
        transform = self._UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(
            self._Usd.TimeCode.Default()
        )
        translation = transform.ExtractTranslation()
        return all(
            abs(float(translation[index]) - fixture_center_m[index]) <= translation_tolerance_m
            for index in range(3)
        )

    def is_dropped(self, pen_path: str, *, minimum_z_m: float = 0.75) -> bool:
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid() or self.is_attached(pen_path):
            return False
        translation = (
            self._UsdGeom.Xformable(prim)
            .ComputeLocalToWorldTransform(self._Usd.TimeCode.Default())
            .ExtractTranslation()
        )
        return float(translation[2]) < minimum_z_m

    def step(self, count: int = 1) -> None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 10000:
            raise PhysicalSimulationError("physical.step.invalid: count must be in [1, 10000]")
        if self._world is None:
            raise PhysicalSimulationError("physical.step.world_missing: Isaac World is required")
        for _ in range(count):
            self._world.step(render=False)
