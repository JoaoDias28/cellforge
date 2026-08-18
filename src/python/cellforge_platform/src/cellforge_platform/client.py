"""Typed Python client for the CellForge platform service."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI

from cellforge_platform.models import (
    BundleRecord,
    ComponentDetail,
    ComponentSummary,
    EvidenceRecord,
    EvidenceRecordCreate,
    EvidenceSnapshot,
    HealthResponse,
    ProductionAttachmentRecord,
    ProductionJobRecord,
    ProductionResultRecord,
    ProductionTraceRecord,
    ProjectRecord,
    RecipeApprovalSummary,
    RecipeRecord,
    ResolutionResponse,
    SyncBatchResponse,
)


class PlatformClientError(Exception):
    """Exception raised when platform API returns an error response."""

    def __init__(
        self, status_code: int, code: str, message: str, payload: dict[str, Any] | None = None
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.payload = payload or {}
        super().__init__(f"[{status_code}] {code}: {message}")


class PlatformClient:
    """HTTP client communicating with the CellForge platform registry service."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        auth_token: str | None = None,
        dev_user: str | None = None,
        dev_role: str | None = None,
        app: FastAPI | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_prefix = "/api/v1"
        self._auth_token = auth_token
        self._dev_user = dev_user
        self._dev_role = dev_role
        self.app = app

        headers: dict[str, str] = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        if dev_user:
            headers["X-CellForge-Dev-User"] = dev_user
        if dev_role:
            headers["X-CellForge-Dev-Role"] = dev_role

        self._client: Any
        if app is not None:
            from starlette.testclient import TestClient

            self._client = TestClient(app=app, base_url=self.base_url, headers=headers)
        else:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=timeout,
            )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PlatformClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _handle_response(self, response: httpx.Response) -> Any:
        if response.is_error:
            try:
                data = response.json()
                detail = data.get("detail", {})
                if isinstance(detail, dict):
                    code = detail.get("code", "error")
                    msg = detail.get("message", str(detail))
                else:
                    code = "error"
                    msg = str(detail)
            except Exception:
                code = "http_error"
                msg = response.text or f"HTTP {response.status_code}"
            raise PlatformClientError(response.status_code, code, msg)

        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # -------------------------------------------------------------------------
    # Health
    # -------------------------------------------------------------------------

    def health(self) -> HealthResponse:
        resp = self._client.get("/health")
        data = self._handle_response(resp)
        return HealthResponse.model_validate(data)

    # -------------------------------------------------------------------------
    # Artifacts
    # -------------------------------------------------------------------------

    def upload_artifact(self, data: bytes, media_type: str = "application/octet-stream") -> str:
        headers = {"content-type": media_type}
        resp = self._client.post(
            f"{self.api_prefix}/artifacts/upload", content=data, headers=headers
        )
        result = self._handle_response(resp)
        return str(result["digest"])

    def download_artifact(self, digest: str) -> bytes:
        resp = self._client.get(f"{self.api_prefix}/artifacts/{digest}")
        if resp.is_error:
            self._handle_response(resp)
        return bytes(resp.content)

    # -------------------------------------------------------------------------
    # Components
    # -------------------------------------------------------------------------

    def publish_component(
        self,
        manifest: dict[str, Any],
        *,
        package_bytes: bytes | None = None,
        git_repo: str | None = None,
        git_commit: str | None = None,
    ) -> ComponentDetail:
        blob_digest: str | None = None
        if package_bytes is not None:
            blob_digest = self.upload_artifact(package_bytes, media_type="application/octet-stream")

        payload = {
            "manifest": manifest,
            "package_artifact_digest": blob_digest,
            "git_repo": git_repo,
            "git_commit": git_commit,
        }
        resp = self._client.post(f"{self.api_prefix}/components/publish", json=payload)
        data = self._handle_response(resp)
        return ComponentDetail.model_validate(data)

    def list_components(
        self,
        *,
        kind: str | None = None,
        support_level: str | None = None,
        query: str | None = None,
        include_deprecated: bool = True,
    ) -> list[ComponentSummary]:
        params: dict[str, Any] = {"include_deprecated": include_deprecated}
        if kind is not None:
            params["kind"] = kind
        if support_level is not None:
            params["support_level"] = support_level
        if query is not None:
            params["query"] = query

        resp = self._client.get(f"{self.api_prefix}/components", params=params)
        data = self._handle_response(resp)
        return [ComponentSummary.model_validate(c) for c in data]

    def get_component(self, component_type: str, version: str) -> ComponentDetail:
        resp = self._client.get(f"{self.api_prefix}/components/{component_type}/{version}")
        data = self._handle_response(resp)
        return ComponentDetail.model_validate(data)

    def deprecate_component(
        self, component_type: str, version: str, reason: str
    ) -> ComponentSummary:
        payload = {"reason": reason}
        resp = self._client.post(
            f"{self.api_prefix}/components/{component_type}/{version}/deprecate", json=payload
        )
        data = self._handle_response(resp)
        return ComponentSummary.model_validate(data)

    def download_component(self, component_type: str, version: str) -> bytes:
        resp = self._client.get(f"{self.api_prefix}/components/{component_type}/{version}/download")
        if resp.is_error:
            self._handle_response(resp)
        return bytes(resp.content)

    # -------------------------------------------------------------------------
    # Projects
    # -------------------------------------------------------------------------

    def register_project(
        self,
        *,
        cell_id: str,
        name: str,
        cell_yaml_sha256: str,
        scene_sha256: str,
        description: str | None = None,
        git_repo: str | None = None,
        git_revision: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ProjectRecord:
        payload = {
            "cell_id": cell_id,
            "name": name,
            "cell_yaml_sha256": cell_yaml_sha256,
            "scene_sha256": scene_sha256,
            "description": description,
            "git_repo": git_repo,
            "git_revision": git_revision,
            "metadata": metadata or {},
        }
        resp = self._client.post(f"{self.api_prefix}/projects", json=payload)
        data = self._handle_response(resp)
        return ProjectRecord.model_validate(data)

    def list_projects(self) -> list[ProjectRecord]:
        resp = self._client.get(f"{self.api_prefix}/projects")
        data = self._handle_response(resp)
        return [ProjectRecord.model_validate(p) for p in data]

    def get_project(self, cell_id: str) -> ProjectRecord:
        resp = self._client.get(f"{self.api_prefix}/projects/{cell_id}")
        data = self._handle_response(resp)
        return ProjectRecord.model_validate(data)

    # -------------------------------------------------------------------------
    # Recipes
    # -------------------------------------------------------------------------

    def publish_recipe(
        self,
        *,
        cell_id: str,
        recipe_id: str,
        version: int,
        name: str,
        schema_sha256: str,
        recipe_data: dict[str, Any],
        status: str = "draft",
    ) -> RecipeRecord:
        payload = {
            "project_id": cell_id,
            "recipe_id": recipe_id,
            "version": version,
            "name": name,
            "status": status,
            "schema_sha256": schema_sha256,
            "recipe_data": recipe_data,
        }
        resp = self._client.post(f"{self.api_prefix}/projects/{cell_id}/recipes", json=payload)
        data = self._handle_response(resp)
        return RecipeRecord.model_validate(data)

    def list_recipes(self, cell_id: str, recipe_id: str | None = None) -> list[RecipeRecord]:
        params = {"recipe_id": recipe_id} if recipe_id else {}
        resp = self._client.get(f"{self.api_prefix}/projects/{cell_id}/recipes", params=params)
        data = self._handle_response(resp)
        return [RecipeRecord.model_validate(r) for r in data]

    def get_recipe(self, cell_id: str, recipe_id: str, version: int) -> RecipeRecord:
        resp = self._client.get(
            f"{self.api_prefix}/projects/{cell_id}/recipes/{recipe_id}/{version}"
        )
        data = self._handle_response(resp)
        return RecipeRecord.model_validate(data)

    # -------------------------------------------------------------------------
    # Bundles
    # -------------------------------------------------------------------------

    def publish_bundle(
        self,
        *,
        bundle_id: str,
        target_profile: str,
        execution_mode: str,
        source_revision: str,
        manifest: dict[str, Any],
        signature: dict[str, Any],
        checksums_txt: str,
        bundle_bytes: bytes | None = None,
        project_id: str | None = None,
    ) -> BundleRecord:
        blob_digest: str | None = None
        if bundle_bytes is not None:
            blob_digest = self.upload_artifact(bundle_bytes, media_type="application/octet-stream")

        payload = {
            "bundle_id": bundle_id,
            "project_id": project_id,
            "target_profile": target_profile,
            "execution_mode": execution_mode,
            "source_revision": source_revision,
            "manifest": manifest,
            "signature": signature,
            "checksums_txt": checksums_txt,
            "bundle_artifact_digest": blob_digest,
        }
        resp = self._client.post(f"{self.api_prefix}/bundles/publish", json=payload)
        data = self._handle_response(resp)
        return BundleRecord.model_validate(data)

    def list_bundles(
        self,
        *,
        target_profile: str | None = None,
        execution_mode: str | None = None,
    ) -> list[BundleRecord]:
        params: dict[str, Any] = {}
        if target_profile:
            params["target_profile"] = target_profile
        if execution_mode:
            params["execution_mode"] = execution_mode
        resp = self._client.get(f"{self.api_prefix}/bundles", params=params)
        data = self._handle_response(resp)
        return [BundleRecord.model_validate(b) for b in data]

    def get_bundle(self, bundle_id: str) -> BundleRecord:
        resp = self._client.get(f"{self.api_prefix}/bundles/{bundle_id}")
        data = self._handle_response(resp)
        return BundleRecord.model_validate(data)

    def download_bundle(self, bundle_id: str) -> bytes:
        resp = self._client.get(f"{self.api_prefix}/bundles/{bundle_id}/download")
        if resp.is_error:
            self._handle_response(resp)
        return bytes(resp.content)

    # -------------------------------------------------------------------------
    # Resolution
    # -------------------------------------------------------------------------

    def resolve_cell(
        self,
        cell_yaml: str,
        mode: str = "simulation",
        allow_deprecated: bool = False,
    ) -> ResolutionResponse:
        payload = {
            "cell_yaml": cell_yaml,
            "mode": mode,
            "allow_deprecated": allow_deprecated,
        }
        resp = self._client.post(f"{self.api_prefix}/resolve", json=payload)
        data = self._handle_response(resp)
        return ResolutionResponse.model_validate(data)

    # -------------------------------------------------------------------------
    # Recipe Approvals
    # -------------------------------------------------------------------------

    def approve_recipe(
        self,
        cell_id: str,
        recipe_id: str,
        version: int,
        role: str,
        decision: str = "approved",
        comments: str | None = None,
        signature: str | None = None,
    ) -> RecipeApprovalSummary:
        payload = {
            "role": role,
            "decision": decision,
            "comments": comments,
            "signature": signature,
        }
        resp = self._client.post(
            f"{self.api_prefix}/projects/{cell_id}/recipes/{recipe_id}/{version}/approve",
            json=payload,
        )
        data = self._handle_response(resp)
        return RecipeApprovalSummary.model_validate(data)

    def get_recipe_approvals(
        self,
        cell_id: str,
        recipe_id: str,
        version: int,
    ) -> RecipeApprovalSummary:
        resp = self._client.get(
            f"{self.api_prefix}/projects/{cell_id}/recipes/{recipe_id}/{version}/approvals"
        )
        data = self._handle_response(resp)
        return RecipeApprovalSummary.model_validate(data)

    # -------------------------------------------------------------------------
    # Evidence & Signed Snapshots
    # -------------------------------------------------------------------------

    def create_evidence(self, record: EvidenceRecordCreate) -> EvidenceRecord:
        resp = self._client.post(
            f"{self.api_prefix}/evidence",
            json=record.model_dump(mode="json"),
        )
        data = self._handle_response(resp)
        return EvidenceRecord.model_validate(data)

    def get_evidence(self, evidence_id: str) -> EvidenceRecord:
        resp = self._client.get(f"{self.api_prefix}/evidence/{evidence_id}")
        data = self._handle_response(resp)
        return EvidenceRecord.model_validate(data)

    def list_evidence(
        self,
        *,
        cell_id: str | None = None,
        kind: str | None = None,
        artifact_sha256: str | None = None,
    ) -> list[EvidenceRecord]:
        params: dict[str, Any] = {}
        if cell_id is not None:
            params["cell_id"] = cell_id
        if kind is not None:
            params["kind"] = kind
        if artifact_sha256 is not None:
            params["artifact_sha256"] = artifact_sha256
        resp = self._client.get(f"{self.api_prefix}/evidence", params=params)
        data = self._handle_response(resp)
        return [EvidenceRecord.model_validate(item) for item in data]

    def generate_evidence_snapshot(
        self,
        cell_id: str,
        *,
        valid_until: str | None = None,
        key_id: str | None = None,
    ) -> EvidenceSnapshot:
        payload = {
            "cell_id": cell_id,
            "valid_until": valid_until,
            "key_id": key_id,
        }
        resp = self._client.post(f"{self.api_prefix}/evidence/snapshots", json=payload)
        data = self._handle_response(resp)
        return EvidenceSnapshot.model_validate(data)

    # -------------------------------------------------------------------------
    # Production Synchronization
    # -------------------------------------------------------------------------

    def sync_batch(
        self,
        cell_id: str,
        *,
        jobs: list[ProductionJobRecord] | None = None,
        traces: list[ProductionTraceRecord] | None = None,
        results: list[ProductionResultRecord] | None = None,
        attachments: list[ProductionAttachmentRecord] | None = None,
    ) -> SyncBatchResponse:
        payload = {
            "cell_id": cell_id,
            "jobs": [j.model_dump(mode="json") for j in (jobs or [])],
            "traces": [t.model_dump(mode="json") for t in (traces or [])],
            "results": [r.model_dump(mode="json") for r in (results or [])],
            "attachments": [a.model_dump(mode="json") for a in (attachments or [])],
        }
        resp = self._client.post(f"{self.api_prefix}/sync/batch", json=payload)
        data = self._handle_response(resp)
        return SyncBatchResponse.model_validate(data)

    def list_production_jobs(
        self,
        *,
        cell_id: str | None = None,
        job_id: str | None = None,
    ) -> list[ProductionJobRecord]:
        params: dict[str, Any] = {}
        if cell_id is not None:
            params["cell_id"] = cell_id
        if job_id is not None:
            params["job_id"] = job_id
        resp = self._client.get(f"{self.api_prefix}/production/jobs", params=params)
        data = self._handle_response(resp)
        return [ProductionJobRecord.model_validate(item) for item in data]

    def list_production_traces(
        self,
        *,
        trace_id: str | None = None,
        cell_id: str | None = None,
    ) -> list[ProductionTraceRecord]:
        params: dict[str, Any] = {}
        if trace_id is not None:
            params["trace_id"] = trace_id
        if cell_id is not None:
            params["cell_id"] = cell_id
        resp = self._client.get(f"{self.api_prefix}/production/traces", params=params)
        data = self._handle_response(resp)
        return [ProductionTraceRecord.model_validate(item) for item in data]

    def list_production_results(
        self,
        *,
        cell_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[ProductionResultRecord]:
        params: dict[str, Any] = {}
        if cell_id is not None:
            params["cell_id"] = cell_id
        if trace_id is not None:
            params["trace_id"] = trace_id
        resp = self._client.get(f"{self.api_prefix}/production/results", params=params)
        data = self._handle_response(resp)
        return [ProductionResultRecord.model_validate(item) for item in data]

    def list_production_attachments(
        self,
        *,
        cell_id: str | None = None,
        trace_id: str | None = None,
    ) -> list[ProductionAttachmentRecord]:
        params: dict[str, Any] = {}
        if cell_id is not None:
            params["cell_id"] = cell_id
        if trace_id is not None:
            params["trace_id"] = trace_id
        resp = self._client.get(f"{self.api_prefix}/production/attachments", params=params)
        data = self._handle_response(resp)
        return [ProductionAttachmentRecord.model_validate(item) for item in data]
