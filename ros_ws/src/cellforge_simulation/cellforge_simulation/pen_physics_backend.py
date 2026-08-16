"""Isaac Sim 6/OpenUSD edge for physical pen spawning, attachment, and seating signals."""

from __future__ import annotations

import math
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
            from isaacsim.core.experimental.prims import RigidPrim
            from pxr import (
                Gf,
                PhysicsSchemaTools,
                PhysxSchema,
                Sdf,
                Tf,
                Usd,
                UsdGeom,
                UsdPhysics,
            )
        except ImportError as error:  # pragma: no cover - exercised only in Isaac Sim
            raise RuntimeError(
                "physical.isaac.unavailable: Isaac Sim 6 OpenUSD/PhysX modules are required"
            ) from error
        self._Gf = Gf
        self._RigidPrim = RigidPrim
        self._PhysxSchema = PhysxSchema
        self._PhysicsSchemaTools = PhysicsSchemaTools
        self._Sdf = Sdf
        self._Tf = Tf
        self._Usd = Usd
        self._UsdGeom = UsdGeom
        self._UsdPhysics = UsdPhysics
        self._stage = stage
        self._world = world
        self._attached: dict[str, str] = {}
        self._rigid_prims: dict[str, Any] = {}

    def spawn_pen(self, object_id: str, pose: PenPose) -> str:
        if not object_id or "/" in object_id:
            raise PhysicalSimulationError("physical.object_id.invalid: expected one prim-safe ID")
        prim_name = self._Tf.MakeValidIdentifier(object_id)
        if not prim_name:
            raise PhysicalSimulationError("physical.object_id.invalid: cannot form a USD prim name")
        path = f"/World/SpawnedProducts/{prim_name}"
        if self._stage.GetPrimAtPath(path).IsValid():
            if self._world is not None:
                self.set_pen_pose(path, pose)
            self._stage.GetPrimAtPath(path).GetAttribute("cellforge:runtimeProductId").Set(
                object_id
            )
            return path
        capsule = self._UsdGeom.Capsule.Define(self._stage, self._Sdf.Path(path))
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
        contact = self._PhysxSchema.PhysxContactReportAPI.Apply(capsule.GetPrim())
        contact.CreateThresholdAttr().Set(0.0)
        capsule.GetPrim().CreateAttribute(
            "cellforge:runtimeProductId", self._Sdf.ValueTypeNames.String, custom=True
        ).Set(object_id)
        return path

    def reset_runtime_products(self) -> None:
        """Remove prior scenario products before configuring the next isolated L2 run."""

        self._attached.clear()
        self._rigid_prims.clear()
        self._stage.RemovePrim(self._Sdf.Path("/World/SpawnedProducts"))
        if self._world is not None:
            self._world.reset()

    def set_pen_pose(self, pen_path: str, pose: PenPose) -> None:
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid():
            raise PhysicalSimulationError(f"physical.pen.missing: '{pen_path}' does not exist")
        half_yaw = math.radians(pose.yaw_deg) / 2.0
        # Update the live PhysX tensor entity. Authoring xform ops alone is overwritten by the
        # rigid-body state on the next simulation step, especially for a kinematic grasp.
        rigid_prim = self._rigid_prim(pen_path)
        rigid_prim.set_world_poses(
            positions=[[pose.x_mm / 1000.0, pose.y_mm / 1000.0, pose.z_mm / 1000.0]],
            orientations=[[math.cos(half_yaw), 0.0, 0.0, math.sin(half_yaw)]],
        )

    def attach(self, pen_path: str, tool_path: str = "/World/Robot/GripperBody") -> str:
        pen = self._stage.GetPrimAtPath(pen_path)
        tool = self._stage.GetPrimAtPath(tool_path)
        if not pen.IsValid() or not tool.IsValid():
            raise PhysicalSimulationError(
                "physical.attach.missing_prim: pen or tool prim is missing"
            )
        joint_path = f"/World/PhysicsJoints/{pen.GetName()}_grasp"
        tool_world = self._UsdGeom.Xformable(tool).ComputeLocalToWorldTransform(
            self._Usd.TimeCode.Default()
        )
        tool_position = tool_world.ExtractTranslation()
        self.set_pen_pose(
            pen_path,
            PenPose(
                float(tool_position[0]) * 1000.0,
                float(tool_position[1]) * 1000.0,
                float(tool_position[2]) * 1000.0,
                0.0,
            ),
        )
        self.step(1)
        self._UsdPhysics.RigidBodyAPI(pen).GetKinematicEnabledAttr().Set(True)
        marker = self._UsdGeom.Scope.Define(self._stage, self._Sdf.Path(joint_path)).GetPrim()
        marker.CreateRelationship("cellforge:tool").SetTargets([self._Sdf.Path(tool_path)])
        marker.CreateRelationship("cellforge:product").SetTargets([self._Sdf.Path(pen_path)])
        marker.CreateAttribute(
            "cellforge:constraintType", self._Sdf.ValueTypeNames.String, custom=True
        ).Set("physx_kinematic_grasp")
        self._attached[pen_path] = joint_path
        return joint_path

    def detach(self, pen_path: str) -> None:
        joint_path = self._attached.pop(pen_path, "")
        if joint_path:
            self._stage.RemovePrim(joint_path)

    def set_dynamic(self, pen_path: str) -> None:
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid():
            raise PhysicalSimulationError(f"physical.pen.missing: '{pen_path}' does not exist")
        self._UsdPhysics.RigidBodyAPI(prim).GetKinematicEnabledAttr().Set(False)

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
        translation = self.translation_m(pen_path)
        return all(
            abs(translation[index] - fixture_center_m[index]) <= translation_tolerance_m
            for index in range(3)
        )

    def is_dropped(self, pen_path: str, *, minimum_z_m: float = 0.75) -> bool:
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid() or self.is_attached(pen_path):
            return False
        return self.translation_m(pen_path)[2] < minimum_z_m

    def translation_m(self, pen_path: str) -> tuple[float, float, float]:
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid():
            raise PhysicalSimulationError(f"physical.pen.missing: '{pen_path}' does not exist")
        rigid_prim = self._rigid_prim(pen_path)
        positions, _ = rigid_prim.get_world_poses()
        position = positions.numpy()[0]
        return (float(position[0]), float(position[1]), float(position[2]))

    def _rigid_prim(self, pen_path: str) -> Any:
        rigid_prim = self._rigid_prims.get(pen_path)
        if rigid_prim is None:
            rigid_prim = self._RigidPrim(pen_path)
            self._rigid_prims[pen_path] = rigid_prim
        return rigid_prim

    def contacts_for(self, pen_path: str) -> tuple[str, ...]:
        """Return collider paths from the immediate PhysX contact report for one pen."""

        if not self._stage.GetPrimAtPath(pen_path).IsValid():
            return ()
        try:
            from omni.physx import get_physx_simulation_interface
        except ImportError as error:  # pragma: no cover - exercised only in Isaac Sim
            raise RuntimeError(
                "physical.isaac.physx_unavailable: contact API is required"
            ) from error
        headers, _ = get_physx_simulation_interface().get_contact_report()
        contacts: set[str] = set()
        for header in headers:
            paths = {
                str(self._PhysicsSchemaTools.intToSdfPath(header.actor0)),
                str(self._PhysicsSchemaTools.intToSdfPath(header.actor1)),
                str(self._PhysicsSchemaTools.intToSdfPath(header.collider0)),
                str(self._PhysicsSchemaTools.intToSdfPath(header.collider1)),
            }
            if pen_path in paths:
                contacts.update(path for path in paths if path and path != pen_path)
        return tuple(sorted(contacts))

    def set_runtime_attribute(self, pen_path: str, name: str, value: str | bool) -> None:
        if not name or not name.replace("_", "").isalnum():
            raise PhysicalSimulationError("physical.attribute.invalid: expected an identifier")
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid():
            raise PhysicalSimulationError(f"physical.pen.missing: '{pen_path}' does not exist")
        value_type = (
            self._Sdf.ValueTypeNames.Bool
            if isinstance(value, bool)
            else self._Sdf.ValueTypeNames.String
        )
        prim.CreateAttribute(f"cellforge:{name}", value_type, custom=True).Set(value)

    def runtime_attribute(self, pen_path: str, name: str) -> str | bool | None:
        prim = self._stage.GetPrimAtPath(pen_path)
        if not prim.IsValid():
            return None
        attribute = prim.GetAttribute(f"cellforge:{name}")
        return attribute.Get() if attribute.IsValid() else None

    def step(self, count: int = 1) -> None:
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 10000:
            raise PhysicalSimulationError("physical.step.invalid: count must be in [1, 10000]")
        if self._world is None:
            raise PhysicalSimulationError("physical.step.world_missing: Isaac World is required")
        for _ in range(count):
            self._world.step(render=False)
