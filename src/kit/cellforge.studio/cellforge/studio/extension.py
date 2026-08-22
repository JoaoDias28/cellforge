"""Isaac Sim 6 / Omniverse Kit UI adapter for the Cell Studio shell."""

import json
from pathlib import Path

import omni.ext
import omni.ui as ui

from cellforge.studio.application import (
    BrowserComponent,
    ComponentFilters,
    SpatialComponent,
    StudioApplication,
)
from cellforge.studio.backend import create_default_application
from cellforge.studio.simulation_backend import create_simulation_application
from cellforge.studio.simulation_host import create_kit_simulation_host

PROJECT_WINDOW = "CellForge Project"
VALIDATION_WINDOW = "CellForge Validation"
LOG_WINDOW = "CellForge Log"
COMPONENT_WINDOW = "CellForge Components"
CONNECTION_WINDOW = "CellForge Connections"
SIMULATION_WINDOW = "CellForge Simulation"
TASK_WINDOW = "CellForge Tasks"
RECIPE_WINDOW = "CellForge Recipes"
DEPLOYMENT_WINDOW = "CellForge Deployment"
EVIDENCE_WINDOW = "CellForge Evidence"


class CellForgeStudioExtension(omni.ext.IExt):
    """Own the shell windows for the lifetime of the Kit extension."""

    def on_startup(self, ext_id: str) -> None:
        """Create a read-only empty shell; startup never opens a project."""

        self._ext_id = ext_id
        self._application: StudioApplication | None = create_default_application()
        self._simulation_host, simulation_host_error = create_kit_simulation_host()
        self._simulation_application = create_simulation_application(simulation_host_error)
        self._project_path_model = ui.SimpleStringModel("")
        self._guided_template_model = ui.SimpleStringModel("blank")
        self._guided_name_model = ui.SimpleStringModel("Guided Cell")
        self._guided_schema_model = ui.SimpleStringModel("0.1.0")
        self._guided_seed_model = ui.SimpleIntModel(3901)
        self._kind_filter_model = ui.SimpleStringModel("")
        self._capability_filter_model = ui.SimpleStringModel("")
        self._support_filter_model = ui.SimpleStringModel("")
        self._simulation_filter_model = ui.SimpleStringModel("")
        self._remove_instance_model = ui.SimpleStringModel("")
        self._spatial_instance_model = ui.SimpleStringModel("")
        self._transform_model = ui.SimpleStringModel(
            "[1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]"
        )
        self._configuration_model = ui.SimpleStringModel("{}")
        self._variants_model = ui.SimpleStringModel("{}")
        self._calibration_kind_model = ui.SimpleStringModel("camera.intrinsics")
        self._calibration_valid_until_model = ui.SimpleStringModel("2030-01-01T00:00:00Z")
        self._calibration_data_model = ui.SimpleStringModel("{}")
        self._calibration_record_model = ui.SimpleStringModel("{}")
        self._connection_id_model = ui.SimpleStringModel("")
        self._connection_kind_model = ui.SimpleStringModel("software")
        self._from_component_model = ui.SimpleStringModel("")
        self._from_port_model = ui.SimpleStringModel("")
        self._to_component_model = ui.SimpleStringModel("")
        self._to_port_model = ui.SimpleStringModel("")
        self._scenario_path_model = ui.SimpleStringModel("")
        self._simulation_project_path_model = ui.SimpleStringModel("")
        self._step_count_model = ui.SimpleIntModel(1)
        self._fault_at_model = ui.SimpleStringModel("now")
        self._fault_target_model = ui.SimpleStringModel("")
        self._fault_code_model = ui.SimpleStringModel("")
        self._fault_parameters_model = ui.SimpleStringModel("{}")
        self._final_status_model = ui.SimpleStringModel("SUCCESS")
        self._evidence_path_model = ui.SimpleStringModel("")
        self._task_id_model = ui.SimpleStringModel("pen_engraving")
        self._task_xml_model = ui.SimpleStringModel("")
        self._recipe_id_model = ui.SimpleStringModel("pen-aluminium-reference")
        self._recipe_version_model = ui.SimpleIntModel(1)
        self._recipe_data_model = ui.SimpleStringModel("{}")
        self._recipe_status_model = ui.SimpleStringModel("VALIDATED")
        self._recipe_evidence_model = ui.SimpleStringModel("scenario:nominal")
        self._recipe_diff_version_b_model = ui.SimpleIntModel(2)
        self._recipe_diff_output_model = ui.SimpleStringModel("")
        self._selected_scenario_model = ui.SimpleStringModel("nominal")
        self._scenario_seed_model = ui.SimpleIntModel(1001)
        self._scenario_fidelity_model = ui.SimpleStringModel("L0")
        self._selected_evidence_path_model = ui.SimpleStringModel("")
        self._deployment_profile_id_model = ui.SimpleStringModel("deployment-sim")
        self._deployment_target_profile_model = ui.SimpleStringModel("pen-cell-amd64")
        self._deployment_mode_model = ui.SimpleStringModel("simulation")
        self._deployment_revision_model = ui.SimpleStringModel("main")
        self._deployment_output_dir_model = ui.SimpleStringModel("dist/bundle")
        self._deployment_signing_key_model = ui.SimpleStringModel("keys/signing.pem")
        self._diff_base_bundle_model = ui.SimpleStringModel("")
        self._diff_candidate_bundle_model = ui.SimpleStringModel("")
        self._diff_output_model = ui.SimpleStringModel("")
        self._signature_bundle_path_model = ui.SimpleStringModel("")
        self._signature_trusted_keys_model = ui.SimpleStringModel("")
        self._compat_bundle_path_model = ui.SimpleStringModel("")
        self._compat_target_facts_model = ui.SimpleStringModel("/etc/cellforge/target.json")
        self._agent_install_root_model = ui.SimpleStringModel("/opt/cellforge")
        self._agent_state_root_model = ui.SimpleStringModel("/var/lib/cellforge")
        self._project_window = ui.Window(PROJECT_WINDOW, width=360, height=420)
        self._component_window = ui.Window(COMPONENT_WINDOW, width=460, height=520)
        self._connection_window = ui.Window(CONNECTION_WINDOW, width=520, height=620)
        self._simulation_window = ui.Window(SIMULATION_WINDOW, width=460, height=620)
        self._task_window = ui.Window(TASK_WINDOW, width=480, height=520)
        self._recipe_window = ui.Window(RECIPE_WINDOW, width=480, height=520)
        self._deployment_window = ui.Window(DEPLOYMENT_WINDOW, width=520, height=620)
        self._evidence_window = ui.Window(EVIDENCE_WINDOW, width=480, height=520)
        self._validation_window = ui.Window(VALIDATION_WINDOW, width=460, height=420)
        self._log_window = ui.Window(LOG_WINDOW, width=820, height=220)
        self._render_all()
        ui.dock_window_in_window(VALIDATION_WINDOW, PROJECT_WINDOW, ui.DockPosition.RIGHT, 0.55)
        ui.dock_window_in_window(COMPONENT_WINDOW, PROJECT_WINDOW, ui.DockPosition.LEFT, 0.55)
        ui.dock_window_in_window(CONNECTION_WINDOW, VALIDATION_WINDOW, ui.DockPosition.BOTTOM, 0.55)
        ui.dock_window_in_window(SIMULATION_WINDOW, CONNECTION_WINDOW, ui.DockPosition.RIGHT, 0.5)
        ui.dock_window_in_window(TASK_WINDOW, COMPONENT_WINDOW, ui.DockPosition.BOTTOM, 0.5)
        ui.dock_window_in_window(RECIPE_WINDOW, TASK_WINDOW, ui.DockPosition.RIGHT, 0.5)
        ui.dock_window_in_window(DEPLOYMENT_WINDOW, RECIPE_WINDOW, ui.DockPosition.RIGHT, 0.5)
        ui.dock_window_in_window(EVIDENCE_WINDOW, SIMULATION_WINDOW, ui.DockPosition.BOTTOM, 0.5)
        ui.dock_window_in_window(LOG_WINDOW, PROJECT_WINDOW, ui.DockPosition.BOTTOM, 0.35)

    def on_shutdown(self) -> None:
        """Release all UI references so Kit can unload the extension cleanly."""

        for window_name in (
            "_project_window",
            "_component_window",
            "_connection_window",
            "_simulation_window",
            "_task_window",
            "_recipe_window",
            "_deployment_window",
            "_evidence_window",
            "_validation_window",
            "_log_window",
        ):
            window = getattr(self, window_name, None)
            if window is not None:
                window.visible = False
                window.frame.clear()
                setattr(self, window_name, None)
        self._application = None
        if self._simulation_application is not None:
            self._simulation_application.close()
        self._simulation_application = None
        if self._simulation_host is not None:
            self._simulation_host.close()
        self._simulation_host = None
        self._project_path_model = None

    def _on_open_project(self) -> None:
        application = self._application
        if application is None:
            return
        application.open_project(self._project_path_model.as_string)
        self._render_all()

    def _on_create_project(self) -> None:
        application = self._application
        if application is None:
            return
        application.create_project(self._project_path_model.as_string)
        self._render_all()

    def _on_save_project(self) -> None:
        application = self._application
        if application is None:
            return
        application.save_project()
        self._render_all()

    def _on_guided_create_project(self) -> None:
        application = self._application
        if application is None:
            return
        from cellforge.studio.guided_launcher import CreateProjectRequest

        application.create_guided_project(
            CreateProjectRequest(
                template_id=self._guided_template_model.as_string.strip(),
                destination_directory=Path(self._project_path_model.as_string.strip()),
                cell_display_name=self._guided_name_model.as_string.strip(),
                requested_schema_version=self._guided_schema_model.as_string.strip(),
                seed=self._guided_seed_model.as_int,
            )
        )
        self._render_all()

    def _on_guided_preview_project(self) -> None:
        application = self._application
        preview = application.snapshot.guided_preview if application is not None else None
        if application is None or preview is None:
            return
        application.preview_guided_project(preview)
        self._render_all()

    def _on_guided_open_project(self) -> None:
        application = self._application
        if application is None:
            return
        application.open_guided_project(self._project_path_model.as_string)
        self._render_all()

    def _on_guided_confirm_save(self) -> None:
        application = self._application
        preview = application.snapshot.guided_preview if application is not None else None
        if application is None or preview is None:
            return
        application.confirm_guided_project_save(
            preview,
            preview.confirmation_token,
            confirmed=True,
        )
        self._render_all()

    def _on_guided_cancel_draft(self) -> None:
        application = self._application
        preview = application.snapshot.guided_preview if application is not None else None
        if application is None or preview is None:
            return
        application.cancel_guided_project_draft(preview)
        self._render_all()

    def _on_refresh_components(self) -> None:
        application = self._application
        if application is None:
            return
        application.refresh_components(
            ComponentFilters(
                kind=self._kind_filter_model.as_string.strip() or None,
                capability=self._capability_filter_model.as_string.strip() or None,
                support_level=self._support_filter_model.as_string.strip() or None,
                simulation_level=self._simulation_filter_model.as_string.strip() or None,
            )
        )
        self._render_all()

    def _on_place_component(
        self,
        component: BrowserComponent,
        alias_model: ui.SimpleStringModel,
        variant_models: dict[str, ui.SimpleStringModel],
    ) -> None:
        application = self._application
        if application is None:
            return
        application.place_component(
            component.component,
            component.version,
            alias_model.as_string,
            {name: model.as_string for name, model in variant_models.items()},
        )
        self._render_all()

    def _on_remove_component(self, remove_connections: bool) -> None:
        application = self._application
        if application is None:
            return
        application.remove_component(
            self._remove_instance_model.as_string,
            remove_connections=remove_connections,
        )
        self._render_all()

    def _on_set_transform(self) -> None:
        if self._application is None:
            return
        try:
            matrix = tuple(float(value) for value in json.loads(self._transform_model.as_string))
        except (TypeError, ValueError, json.JSONDecodeError):
            matrix = ()
        self._application.set_component_transform(self._spatial_instance_model.as_string, matrix)
        self._render_all()

    def _on_select_spatial_component(self, component: SpatialComponent) -> None:
        if self._application is None:
            return
        self._spatial_instance_model.set_value(component.instance_id)
        self._transform_model.set_value(json.dumps(component.transform))
        try:
            import omni.usd

            omni.usd.get_context().get_selection().set_selected_prim_paths(
                [component.usd_prim], True
            )
        except Exception:
            pass
        self._render_all()

    def _on_set_configuration(self) -> None:
        if self._application is None:
            return
        try:
            configuration = json.loads(self._configuration_model.as_string)
        except json.JSONDecodeError:
            return
        if not isinstance(configuration, dict):
            return
        self._application.set_component_configuration(
            self._spatial_instance_model.as_string,
            configuration,
        )
        self._render_all()

    def _on_set_variants(self) -> None:
        if self._application is None:
            return
        try:
            variants = json.loads(self._variants_model.as_string)
        except json.JSONDecodeError:
            return
        if not isinstance(variants, dict) or not all(
            isinstance(value, str) for value in variants.values()
        ):
            return
        self._application.set_component_variants(
            self._spatial_instance_model.as_string,
            variants,
        )
        self._render_all()

    def _on_create_calibration(self) -> None:
        if self._application is None:
            return
        try:
            data = json.loads(self._calibration_data_model.as_string)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        self._application.create_calibration(
            self._spatial_instance_model.as_string,
            self._calibration_kind_model.as_string,
            self._calibration_valid_until_model.as_string,
            data,
        )
        self._render_all()

    def _on_import_calibration(self) -> None:
        if self._application is None:
            return
        try:
            calibration = json.loads(self._calibration_record_model.as_string)
        except json.JSONDecodeError:
            return
        if not isinstance(calibration, dict):
            return
        self._application.import_calibration(
            self._spatial_instance_model.as_string,
            calibration,
        )
        self._render_all()

    def _on_undo(self) -> None:
        if self._application is not None:
            self._application.undo()
            self._render_all()

    def _on_redo(self) -> None:
        if self._application is not None:
            self._application.redo()
            self._render_all()

    def _on_refresh_connections(self) -> None:
        if self._application is not None:
            self._application.refresh_connections()
            self._render_all()

    def _on_preview_mechanical_connection(self) -> None:
        if self._application is not None:
            self._application.preview_mechanical_connection(
                self._connection_id_model.as_string,
                self._from_component_model.as_string,
                self._from_port_model.as_string,
                self._to_component_model.as_string,
                self._to_port_model.as_string,
            )
            self._render_all()

    def _on_connect_ports(self) -> None:
        if self._application is not None:
            self._application.connect_ports(
                self._connection_id_model.as_string,
                self._connection_kind_model.as_string,
                self._from_component_model.as_string,
                self._from_port_model.as_string,
                self._to_component_model.as_string,
                self._to_port_model.as_string,
            )
            self._render_all()

    def _on_configure_simulation(self) -> None:
        if self._simulation_application is not None:
            self._simulation_application.configure(
                self._simulation_project_path_model.as_string,
                self._scenario_path_model.as_string,
            )
            self._render_all()

    def _on_simulation_control(self, command: str) -> None:
        if self._simulation_application is not None:
            self._simulation_application.control(command, self._step_count_model.as_int)
            self._render_all()

    def _on_inject_simulation_fault(self) -> None:
        if self._simulation_application is not None:
            self._simulation_application.inject_fault(
                self._fault_at_model.as_string,
                self._fault_target_model.as_string,
                self._fault_code_model.as_string,
                self._fault_parameters_model.as_string,
            )
            self._render_all()

    def _on_finalize_simulation(self) -> None:
        if self._simulation_application is not None:
            self._simulation_application.finalize(
                self._final_status_model.as_string,
                self._evidence_path_model.as_string,
            )
            self._render_all()

    def _on_refresh_tasks(self) -> None:
        if self._application is not None:
            self._application.refresh_tasks()
            self._render_all()

    def _on_save_task(self) -> None:
        if self._application is not None:
            self._application.set_task_tree(
                self._task_id_model.as_string,
                self._task_xml_model.as_string,
            )
            self._render_all()

    def _on_refresh_recipes(self) -> None:
        if self._application is not None:
            self._application.refresh_recipes()
            self._render_all()

    def _on_edit_recipe(self) -> None:
        if self._application is None:
            return
        try:
            data = json.loads(self._recipe_data_model.as_string)
        except json.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        self._application.edit_recipe(
            self._recipe_id_model.as_string,
            self._recipe_version_model.as_int,
            data,
        )
        self._render_all()

    def _on_create_recipe_version(self) -> None:
        if self._application is not None:
            self._application.create_recipe_version(
                self._recipe_id_model.as_string,
                base_version=self._recipe_version_model.as_int,
            )
            self._render_all()

    def _on_transition_recipe_lifecycle(self) -> None:
        if self._application is not None:
            ev_str = self._recipe_evidence_model.as_string.strip()
            evidence = [ev_str] if ev_str else None
            self._application.transition_recipe_lifecycle(
                self._recipe_id_model.as_string,
                self._recipe_version_model.as_int,
                self._recipe_status_model.as_string,
                evidence=evidence,
            )
            self._render_all()

    def _on_diff_recipes(self) -> None:
        if self._application is not None:
            result = self._application.diff_recipes(
                self._recipe_id_model.as_string,
                self._recipe_version_model.as_int,
                self._recipe_diff_version_b_model.as_int,
            )
            if result is not None:
                self._recipe_diff_output_model.set_value(
                    f"Breaking changes: {result.breaking}\n"
                    f"Parameter diffs: {len(result.parameter_diffs)}\n"
                    f"Trajectory diffs: {len(result.trajectory_diffs)}\n"
                    f"Tolerance diffs: {len(result.tolerance_diffs)}"
                )
            self._render_all()

    def _on_refresh_scenarios(self) -> None:
        if self._application is not None:
            self._application.refresh_scenarios()
            self._render_all()

    def _on_run_scenario_service(self) -> None:
        if self._application is not None:
            self._application.execute_scenario(
                self._selected_scenario_model.as_string,
                seed_override=self._scenario_seed_model.as_int,
                available_backend_fidelity=self._scenario_fidelity_model.as_string,
            )
            self._render_all()

    def _on_refresh_evidence(self) -> None:
        if self._application is not None:
            self._application.refresh_evidence()
            self._render_all()

    def _on_inspect_evidence(self) -> None:
        if self._application is not None:
            self._application.inspect_evidence(self._selected_evidence_path_model.as_string)
            self._render_all()

    def _on_replay_evidence(self) -> None:
        if self._application is not None:
            self._application.replay_evidence(self._selected_evidence_path_model.as_string)
            self._render_all()

    def _on_refresh_deployments(self) -> None:
        if self._application is not None:
            self._application.refresh_deployment_profiles()
            self._render_all()

    def _on_assemble_bundle(self) -> None:
        if self._application is not None:
            self._application.assemble_bundle(
                target_profile=self._deployment_target_profile_model.as_string,
                mode=self._deployment_mode_model.as_string,
                source_revision=self._deployment_revision_model.as_string,
                output_dir=Path(self._deployment_output_dir_model.as_string),
                signing_key_path=Path(self._deployment_signing_key_model.as_string),
            )
            self._render_all()

    def _on_diff_bundles(self) -> None:
        if self._application is not None:
            base_p = Path(self._diff_base_bundle_model.as_string)
            cand_p = Path(self._diff_candidate_bundle_model.as_string)
            self._application.diff_bundles(base_p, cand_p)
            diff = self._application.snapshot.last_bundle_diff
            if diff is not None:
                self._diff_output_model.set_value(diff.summary)
            self._render_all()

    def _on_verify_bundle_signature(self) -> None:
        if self._application is not None:
            root_p = Path(self._signature_bundle_path_model.as_string)
            keys_p = (
                Path(self._signature_trusted_keys_model.as_string)
                if self._signature_trusted_keys_model.as_string
                else None
            )
            self._application.verify_bundle_signature(root_p, keys_p)
            self._render_all()

    def _on_preflight_target_compatibility(self) -> None:
        if self._application is not None:
            root_p = Path(self._compat_bundle_path_model.as_string)
            facts_p = Path(self._compat_target_facts_model.as_string)
            self._application.preflight_target_compatibility(root_p, facts_p)
            self._render_all()

    def _on_refresh_deployment_status(self) -> None:
        if self._application is not None:
            from cellforge.studio.deployment_service import AgentPaths

            paths = AgentPaths(
                install_root=Path(self._agent_install_root_model.as_string),
                state_root=Path(self._agent_state_root_model.as_string),
            )
            self._application.refresh_deployment_status(paths)
            self._render_all()

    def _on_install_bundle(self) -> None:
        if self._application is not None:
            from cellforge.studio.deployment_service import AgentPaths

            paths = AgentPaths(
                install_root=Path(self._agent_install_root_model.as_string),
                state_root=Path(self._agent_state_root_model.as_string),
            )
            bundle_p = Path(self._deployment_output_dir_model.as_string)
            self._application.install_bundle(bundle_p, paths)
            self._render_all()

    def _on_rollback_deployment(self) -> None:
        if self._application is not None:
            from cellforge.studio.deployment_service import AgentPaths

            paths = AgentPaths(
                install_root=Path(self._agent_install_root_model.as_string),
                state_root=Path(self._agent_state_root_model.as_string),
            )
            self._application.rollback_deployment(paths)
            self._render_all()

    def _render_all(self) -> None:
        self._render_project_panel()
        self._render_component_panel()
        self._render_connection_panel()
        self._render_task_panel()
        self._render_recipe_panel()
        self._render_simulation_panel()
        self._render_evidence_panel()
        self._render_deployment_panel()
        self._render_validation_panel()
        self._render_log_panel()

    def _render_project_panel(self) -> None:
        snapshot = self._application.snapshot
        self._project_window.frame.clear()
        with self._project_window.frame:
            with ui.VStack(spacing=8):
                ui.Label("Cell Studio", style={"font_size": 20})
                ui.Label(snapshot.headline, word_wrap=True)
                ui.Label(snapshot.detail, word_wrap=True)
                ui.Spacer(height=4)
                ui.Label("Project directory")
                ui.StringField(model=self._project_path_model)
                with ui.HStack(spacing=6, height=28):
                    ui.Button("Create", clicked_fn=self._on_create_project)
                    ui.Button("Open / Refresh", clicked_fn=self._on_open_project)
                    ui.Button("Save", clicked_fn=self._on_save_project)
                ui.Separator(height=8)
                ui.Label("Guided Studio launcher", style={"font_size": 16})
                ui.Label(
                    "Create and review a simulation-only candidate. "
                    "No canonical file is written until Confirm Guided Save.",
                    word_wrap=True,
                )
                ui.Label("Template ID (blank, pen_engraving, or kitting)")
                ui.StringField(model=self._guided_template_model)
                ui.Label("Cell display name")
                ui.StringField(model=self._guided_name_model)
                ui.Label("Requested schema version")
                ui.StringField(model=self._guided_schema_model)
                ui.Label("Deterministic seed")
                ui.IntField(model=self._guided_seed_model)
                with ui.HStack(spacing=6, height=28):
                    ui.Button("Guided Create", clicked_fn=self._on_guided_create_project)
                    ui.Button("Review / Refresh", clicked_fn=self._on_guided_preview_project)
                    ui.Button("Guided Open", clicked_fn=self._on_guided_open_project)
                with ui.HStack(spacing=6, height=28):
                    ui.Button("Confirm Guided Save", clicked_fn=self._on_guided_confirm_save)
                    ui.Button("Cancel Draft", clicked_fn=self._on_guided_cancel_draft)
                guided_preview = snapshot.guided_preview
                if guided_preview is not None:
                    ui.Separator(height=8)
                    ui.Label(
                        f"Preview {guided_preview.draft_id} — {guided_preview.template_id}",
                        word_wrap=True,
                    )
                    ui.Label(
                        f"Mode: {guided_preview.starting_mode}; "
                        f"simulation-only: {guided_preview.simulation_only}"
                    )
                    save_label = (
                        "available after confirmation" if guided_preview.can_save else "blocked"
                    )
                    ui.Label(f"Save: {save_label}", word_wrap=True)
                    ui.Label(
                        f"Candidate SHA-256: {guided_preview.candidate_hash}",
                        word_wrap=True,
                    )
                    ui.Label(
                        f"Generated files ({len(guided_preview.generated_paths)}): "
                        + ", ".join(guided_preview.generated_paths),
                        word_wrap=True,
                    )
                    if guided_preview.required_choices:
                        ui.Label("Required choices:")
                        for choice in guided_preview.required_choices:
                            ui.Label(f"- {choice.key}: {choice.prompt}", word_wrap=True)
                    if guided_preview.findings:
                        ui.Label("Findings:")
                        for finding in guided_preview.findings:
                            ui.Label(
                                f"{finding.severity.upper()} {finding.code}: {finding.message}",
                                word_wrap=True,
                            )
                if snapshot.project is not None:
                    project = snapshot.project
                    ui.Separator(height=8)
                    ui.Label(f"Cell ID: {project.cell_id}", word_wrap=True)
                    ui.Label(f"Scene: {project.scene}", word_wrap=True)
                    ui.Label(f"Dirty: {'yes' if snapshot.dirty else 'no'}")
                    ui.Label(f"Components: {project.component_count}")
                    ui.Label(f"Connections: {project.connection_count}")
                    ui.Label(f"Tasks: {project.task_count}")
                    ui.Label(f"Recipes: {project.recipe_count}")
                    ui.Label(f"Scenarios: {project.scenario_count}")
                    ui.Separator(height=8)
                    ui.Label("Spatial configuration", style={"font_size": 16})
                    ui.Label("Selected component instance ID")
                    ui.StringField(model=self._spatial_instance_model)
                    ui.Label("Viewport selection and spatial metadata")
                    for component in snapshot.spatial_components:
                        ui.Label(
                            f"{component.alias} [{component.instance_id}] {component.usd_prim}",
                            word_wrap=True,
                        )
                        ui.Label(
                            "Frames: " + (", ".join(component.frames) or "none"),
                            word_wrap=True,
                        )
                        ui.Label(f"Collision asset: {component.collision_asset}", word_wrap=True)
                        ui.Button(
                            f"Select {component.alias}",
                            clicked_fn=lambda item=component: self._on_select_spatial_component(
                                item
                            ),
                        )
                    ui.Label("4x4 transform JSON (viewport selection)")
                    ui.StringField(model=self._transform_model)
                    ui.Button(
                        "Apply transform and visualize frames/collision",
                        clicked_fn=self._on_set_transform,
                    )
                    ui.Label("Configuration JSON")
                    ui.StringField(model=self._configuration_model)
                    ui.Button(
                        "Apply schema-backed configuration", clicked_fn=self._on_set_configuration
                    )
                    ui.Label("Variant selections JSON")
                    ui.StringField(model=self._variants_model)
                    ui.Button("Apply variants", clicked_fn=self._on_set_variants)
                    ui.Label("Calibration kind / valid until / data JSON")
                    ui.StringField(model=self._calibration_kind_model)
                    ui.StringField(model=self._calibration_valid_until_model)
                    ui.StringField(model=self._calibration_data_model)
                    ui.Button(
                        "Create immutable calibration", clicked_fn=self._on_create_calibration
                    )
                    ui.Label("Import immutable calibration JSON")
                    ui.StringField(model=self._calibration_record_model)
                    ui.Button("Import calibration", clicked_fn=self._on_import_calibration)

    def _render_component_panel(self) -> None:
        snapshot = self._application.snapshot
        self._component_window.frame.clear()
        with self._component_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Component browser", style={"font_size": 18})
                    ui.Label("Kind")
                    ui.StringField(model=self._kind_filter_model)
                    ui.Label("Capability")
                    ui.StringField(model=self._capability_filter_model)
                    ui.Label("Support level")
                    ui.StringField(model=self._support_filter_model)
                    ui.Label("Simulation level")
                    ui.StringField(model=self._simulation_filter_model)
                    ui.Button("Apply filters", clicked_fn=self._on_refresh_components)
                    with ui.HStack(spacing=6, height=28):
                        ui.Button("Undo", clicked_fn=self._on_undo)
                        ui.Button("Redo", clicked_fn=self._on_redo)
                    ui.Separator(height=8)
                    for component in snapshot.browser:
                        self._render_component_detail(component)
                    ui.Separator(height=8)
                    ui.Label("Remove instance ID")
                    ui.StringField(model=self._remove_instance_model)
                    ui.Button(
                        "Remove (refuse connected)",
                        clicked_fn=lambda: self._on_remove_component(False),
                    )
                    ui.Button(
                        "Remove and resolve by deleting connections",
                        clicked_fn=lambda: self._on_remove_component(True),
                    )

    def _render_component_detail(self, component: BrowserComponent) -> None:
        ui.Label(f"{component.name}  {component.version}", word_wrap=True)
        ui.Label(f"{component.kind} | {component.support_level} | {component.simulation_level}")
        ui.Label(f"Type: {component.component}", word_wrap=True)
        if component.manufacturer or component.model:
            ui.Label(
                f"Manufacturer/model: {component.manufacturer or 'unspecified'} / "
                f"{component.model or 'unspecified'}",
                word_wrap=True,
            )
        if component.description:
            ui.Label(component.description, word_wrap=True)
        ui.Label(f"License: {component.license or 'unspecified'}", word_wrap=True)
        ui.Label(
            "Capabilities: " + (", ".join(component.capabilities) or "none"),
            word_wrap=True,
        )
        ui.Label(
            "Compatible modes: " + (", ".join(component.compatible_modes) or "none"),
            word_wrap=True,
        )
        for warning in component.warnings:
            ui.Label(f"WARNING: {warning}", word_wrap=True)
        alias_model = ui.SimpleStringModel(component.kind)
        ui.Label("Alias")
        ui.StringField(model=alias_model)
        variant_models: dict[str, ui.SimpleStringModel] = {}
        for variant in component.variants:
            ui.Label(f"Variant {variant.name}: {', '.join(variant.selections)}")
            model = ui.SimpleStringModel(variant.selections[0] if variant.selections else "")
            ui.StringField(model=model)
            variant_models[variant.name] = model
        ui.Button(
            "Place",
            clicked_fn=lambda item=component, alias=alias_model, variants=variant_models: (
                self._on_place_component(item, alias, variants)
            ),
        )
        ui.Separator(height=6)

    def _render_connection_panel(self) -> None:
        snapshot = self._application.snapshot
        self._connection_window.frame.clear()
        with self._connection_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Typed connection graph", style={"font_size": 18})
                    ui.Button("Refresh ports and edges", clicked_fn=self._on_refresh_connections)
                    for kind in ("mechanical", "software", "industrial_io", "safety"):
                        title = "MODELED SAFETY (NON-EXECUTABLE)" if kind == "safety" else kind
                        style = {"color": 0xFF4AA3FF} if kind == "safety" else {}
                        ui.Label(title, style=style)
                        for port in (
                            item for item in snapshot.connection_ports if item.kind == kind
                        ):
                            ui.Label(
                                f"{port.component_alias} [{port.component_instance}] / {port.port} "
                                f"{port.direction} : {port.port_type}",
                                word_wrap=True,
                                style=style,
                            )
                    ui.Separator(height=8)
                    ui.Label("Existing edges")
                    for edge in snapshot.connection_edges:
                        marker = "MODELED-ONLY SAFETY" if edge.modeled_only else edge.kind
                        style = {"color": 0xFF4AA3FF} if edge.modeled_only else {}
                        ui.Label(
                            f"{marker}: {edge.connection_id} | "
                            f"{edge.from_component}/{edge.from_port} -> "
                            f"{edge.to_component}/{edge.to_port}",
                            word_wrap=True,
                            style=style,
                        )
                    ui.Separator(height=8)
                    ui.Label("Create typed edge")
                    for label, model in (
                        ("Connection ID", self._connection_id_model),
                        ("Kind", self._connection_kind_model),
                        ("From component instance ID", self._from_component_model),
                        ("From port", self._from_port_model),
                        ("To component instance ID", self._to_component_model),
                        ("To port", self._to_port_model),
                    ):
                        ui.Label(label)
                        ui.StringField(model=model)
                    with ui.HStack(spacing=6, height=28):
                        ui.Button(
                            "Preview mechanical snap",
                            clicked_fn=self._on_preview_mechanical_connection,
                        )
                        ui.Button("Create connection", clicked_fn=self._on_connect_ports)
                    if snapshot.mechanical_preview is not None:
                        preview = snapshot.mechanical_preview
                        ui.Label(
                            f"Snap preview: {preview.current_target_prim} -> "
                            f"{preview.snapped_target_prim}; adapter required: "
                            f"{'yes' if preview.adapter_required else 'no'}",
                            word_wrap=True,
                        )
                    ui.Separator(height=8)
                    ui.Label(
                        snapshot.safety_disclaimer
                        or "Modeled safety dependencies are never executable wiring.",
                        word_wrap=True,
                        style={"color": 0xFF4AA3FF},
                    )

    def _render_task_panel(self) -> None:
        snapshot = self._application.snapshot
        self._task_window.frame.clear()
        with self._task_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Task Authoring", style={"font_size": 18})
                    with ui.HStack(spacing=6, height=28):
                        ui.Button("Refresh tasks", clicked_fn=self._on_refresh_tasks)
                    ui.Separator(height=8)
                    ui.Label("Tasks in Project")
                    if not snapshot.tasks:
                        ui.Label("No tasks declared in project.")
                    for task in snapshot.tasks:
                        valid_badge = "VALID" if task.valid else "INVALID"
                        color = 0xFF44AA44 if task.valid else 0xFF4444FF
                        ui.Label(
                            f"[{valid_badge}] {task.task_id} ({task.file_name}) — "
                            f"{task.node_count} nodes",
                            style={"color": color},
                        )
                        if task.capabilities_required:
                            ui.Label(
                                f"  Required capabilities: {', '.join(task.capabilities_required)}",
                                style={"font_size": 12},
                            )
                        if task.errors:
                            for err in task.errors:
                                ui.Label(f"  * {err}", style={"color": 0xFF4444FF, "font_size": 12})
                    ui.Separator(height=8)
                    ui.Label("Available Plugin Nodes")
                    for spec in snapshot.available_node_specs:
                        ui.Label(f"• {spec.node_type} [{spec.category}]")
                        for port in spec.ports:
                            ui.Label(
                                f"    {port.direction}: {port.name} ({port.port_type})",
                                style={"font_size": 12},
                            )
                    ui.Separator(height=8)
                    ui.Label("Task BehaviorTree XML Editor")
                    ui.Label("Task ID")
                    ui.StringField(model=self._task_id_model)
                    ui.Label("Tree XML")
                    ui.StringField(model=self._task_xml_model, multiline=True)
                    with ui.HStack(spacing=6, height=28):
                        ui.Button("Save Task XML", clicked_fn=self._on_save_task)

    def _render_recipe_panel(self) -> None:
        snapshot = self._application.snapshot
        self._recipe_window.frame.clear()
        with self._recipe_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Recipe Authoring & Lifecycle", style={"font_size": 18})
                    with ui.HStack(spacing=6, height=28):
                        ui.Button("Refresh recipes", clicked_fn=self._on_refresh_recipes)
                    ui.Separator(height=8)
                    ui.Label("Recipes in Project")
                    if not snapshot.recipes:
                        ui.Label("No recipes found in project.")
                    for rec in snapshot.recipes:
                        imm_badge = "IMMUTABLE" if rec.is_immutable else "EDITABLE"
                        ui.Label(
                            f"[{rec.status}] {rec.recipe_id} v{rec.version} "
                            f"({rec.file_path}) [{imm_badge}]",
                            word_wrap=True,
                        )
                        ui.Label(f"  Component: {rec.component_type} | Mode: {rec.process_mode}")
                        if rec.parameters:
                            ui.Label(f"  Params: {rec.parameters}")
                        if rec.validation_errors:
                            for err in rec.validation_errors:
                                ui.Label(f"  * {err}", style={"color": 0xFF4444FF, "font_size": 12})
                    ui.Separator(height=8)
                    ui.Label("Edit / Transition Recipe")
                    for label, model in (
                        ("Recipe ID", self._recipe_id_model),
                        ("Recipe version", self._recipe_version_model),
                        ("Recipe data (JSON)", self._recipe_data_model),
                        (
                            "Target status (VALIDATED, TESTED, APPROVED, RETIRED)",
                            self._recipe_status_model,
                        ),
                        (
                            "Transition evidence (e.g. scenario / test run ID)",
                            self._recipe_evidence_model,
                        ),
                    ):
                        ui.Label(label)
                        if isinstance(model, ui.SimpleIntModel):
                            ui.IntField(model=model)
                        else:
                            ui.StringField(model=model)
                    with ui.HStack(spacing=6, height=28):
                        ui.Button("Apply Edits (Draft)", clicked_fn=self._on_edit_recipe)
                        ui.Button(
                            "Create Next Version (N+1)", clicked_fn=self._on_create_recipe_version
                        )
                        ui.Button(
                            "Transition Status", clicked_fn=self._on_transition_recipe_lifecycle
                        )
                    ui.Separator(height=8)
                    ui.Label("Diff Recipe Versions")
                    ui.Label("Compare Version A (above) with Version B:")
                    ui.IntField(model=self._recipe_diff_version_b_model)
                    ui.Button("Compute Diff", clicked_fn=self._on_diff_recipes)
                    if self._recipe_diff_output_model.as_string:
                        ui.Label(self._recipe_diff_output_model.as_string, word_wrap=True)

    def _render_validation_panel(self) -> None:
        snapshot = self._application.snapshot
        self._validation_window.frame.clear()
        with self._validation_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Validation", style={"font_size": 18})
                    if not snapshot.validation:
                        ui.Label(
                            "No validation findings. Open a project to run the backend validator.",
                            word_wrap=True,
                        )
                    for finding in snapshot.validation:
                        ui.Label(f"[{finding.severity.upper()}] {finding.code}", word_wrap=True)
                        ui.Label(finding.message, word_wrap=True)
                        ui.Label(finding.path, word_wrap=True, style={"font_size": 12})
                        ui.Separator(height=4)

    def _render_simulation_panel(self) -> None:
        snapshot = self._simulation_application.snapshot
        self._simulation_window.frame.clear()
        with self._simulation_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Simulation control", style={"font_size": 18})
                    ui.Label(f"State: {snapshot.state}")
                    ui.Label(f"{snapshot.code}: {snapshot.detail}", word_wrap=True)
                    ui.Label(snapshot.safety_disclaimer, word_wrap=True)
                    ui.Separator(height=8)
                    ui.Label("Canonical project directory")
                    ui.StringField(model=self._simulation_project_path_model)
                    ui.Label("Scenario path")
                    ui.StringField(model=self._scenario_path_model)
                    ui.Button("Configure", clicked_fn=self._on_configure_simulation)
                    with ui.HStack(spacing=4, height=28):
                        ui.Button("Reset", clicked_fn=lambda: self._on_simulation_control("RESET"))
                        ui.Button("Start", clicked_fn=lambda: self._on_simulation_control("START"))
                        ui.Button("Pause", clicked_fn=lambda: self._on_simulation_control("PAUSE"))
                    ui.Label("Step count")
                    ui.IntField(model=self._step_count_model)
                    ui.Button("Step", clicked_fn=lambda: self._on_simulation_control("STEP"))
                    ui.Separator(height=8)
                    for label, model in (
                        ("Fault schedule point", self._fault_at_model),
                        ("Fault target instance ID", self._fault_target_model),
                        ("Fault code", self._fault_code_model),
                        ("Fault parameters JSON", self._fault_parameters_model),
                    ):
                        ui.Label(label)
                        ui.StringField(model=model)
                    ui.Button("Inject fault", clicked_fn=self._on_inject_simulation_fault)
                    ui.Separator(height=8)
                    ui.Label("Final status")
                    ui.StringField(model=self._final_status_model)
                    ui.Label("Evidence JSON path")
                    ui.StringField(model=self._evidence_path_model)
                    ui.Button(
                        "Finalize and store evidence", clicked_fn=self._on_finalize_simulation
                    )
                    if snapshot.evidence_path:
                        ui.Label(f"Evidence: {snapshot.evidence_path}", word_wrap=True)
                    ui.Separator(height=8)
                    ui.Label("Declared Scenarios", style={"font_size": 16})
                    app_snapshot = self._application.snapshot
                    for sc in app_snapshot.scenarios:
                        ui.Label(f"• {sc.id} [{sc.requested_fidelity}] - {sc.name}", word_wrap=True)
                    ui.Label("Selected Scenario ID")
                    ui.StringField(model=self._selected_scenario_model)
                    ui.Label("Seed")
                    ui.IntField(model=self._scenario_seed_model)
                    ui.Label("Simulation Backend Fidelity")
                    ui.StringField(model=self._scenario_fidelity_model)
                    with ui.HStack(spacing=4, height=28):
                        ui.Button("Refresh Scenarios", clicked_fn=self._on_refresh_scenarios)
                        ui.Button("Run Scenario Engine", clicked_fn=self._on_run_scenario_service)
                    if app_snapshot.last_execution_result is not None:
                        exec_res = app_snapshot.last_execution_result
                        ui.Separator(height=4)
                        ui.Label(f"Result: {exec_res.final_status} (Passed: {exec_res.passed})")
                        ui.Label(
                            f"Achieved Fidelity: [{exec_res.fidelity.achieved}]", word_wrap=True
                        )
                        ui.Label(
                            f"Limitations: {exec_res.fidelity.limitations}",
                            word_wrap=True,
                            style={"font_size": 12},
                        )
                        ui.Label(
                            exec_res.fidelity.safety_disclaimer,
                            word_wrap=True,
                            style={"font_size": 12},
                        )
                        ui.Label(f"Trace events captured: {len(exec_res.trace_events)}")
                        for evt in exec_res.trace_events[-8:]:
                            line_txt = (
                                f"  {evt.sequence:02d}. {evt.event_type} "
                                f"({evt.component_instance_id}) -> {evt.result_code}"
                            )
                            ui.Label(line_txt, word_wrap=True)

    def _render_evidence_panel(self) -> None:
        app_snapshot = self._application.snapshot
        self._evidence_window.frame.clear()
        with self._evidence_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Simulation Evidence", style={"font_size": 18})
                    disclaimer_msg = (
                        "Simulation status and evidence are standard-control engineering "
                        "data only. Functional safety remains independently enforced "
                        "and validated by rated hardware."
                    )
                    ui.Label(
                        disclaimer_msg,
                        word_wrap=True,
                        style={"font_size": 12},
                    )
                    ui.Separator(height=4)
                    ui.Button("Refresh Evidence Files", clicked_fn=self._on_refresh_evidence)
                    for ev in app_snapshot.evidence_records:
                        ev_summary_txt = (
                            f"• {ev.path}: {ev.scenario_id} "
                            f"[{ev.achieved_fidelity}] -> {ev.final_status}"
                        )
                        ui.Label(ev_summary_txt, word_wrap=True)
                    ui.Separator(height=4)
                    ui.Label("Evidence File Path")
                    ui.StringField(model=self._selected_evidence_path_model)
                    with ui.HStack(spacing=4, height=28):
                        ui.Button("Inspect Evidence", clicked_fn=self._on_inspect_evidence)
                        ui.Button("Replay & Verify", clicked_fn=self._on_replay_evidence)
                    if app_snapshot.selected_evidence is not None:
                        ed = app_snapshot.selected_evidence
                        ui.Separator(height=4)
                        ui.Label(f"Scenario: {ed.summary.scenario_id} (Seed: {ed.summary.seed})")
                        ui.Label(
                            f"Outcome: {ed.summary.final_status} (Passed: {ed.summary.passed})"
                        )
                        ui.Label(f"Project Cell SHA: {ed.project_cell_sha256[:16]}...")
                        ui.Label(f"Project Scene SHA: {ed.project_scene_sha256[:16]}...")
                        ui.Label(f"Trace events: {len(ed.trace_events)}")
                    if app_snapshot.last_replay_result is not None:
                        rep = app_snapshot.last_replay_result
                        ui.Label(f"Replay Matched: {rep.events_matched} (Passed: {rep.passed})")

    def _render_deployment_panel(self) -> None:
        app_snapshot = self._application.snapshot
        self._deployment_window.frame.clear()
        with self._deployment_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=6):
                    ui.Label("Deployment and Release", style={"font_size": 18})
                    ui.Label("Deployment Profiles", style={"font_size": 16})
                    for p in app_snapshot.deployment_profiles:
                        ui.Label(
                            f"• {p.id} [{p.execution_mode}] target: {p.target_profile}",
                            word_wrap=True,
                        )
                    ui.Button("Refresh Profiles", clicked_fn=self._on_refresh_deployments)
                    ui.Separator(height=6)
                    ui.Label("Signed Bundle Assembly", style={"font_size": 16})
                    ui.Label("Target Profile")
                    ui.StringField(model=self._deployment_target_profile_model)
                    ui.Label("Mode")
                    ui.StringField(model=self._deployment_mode_model)
                    ui.Label("Source Revision")
                    ui.StringField(model=self._deployment_revision_model)
                    ui.Label("Output Directory")
                    ui.StringField(model=self._deployment_output_dir_model)
                    ui.Label("Signing Key (PEM)")
                    ui.StringField(model=self._deployment_signing_key_model)
                    ui.Button("Assemble Signed Bundle", clicked_fn=self._on_assemble_bundle)
                    if app_snapshot.last_bundle_assembly is not None:
                        assemb = app_snapshot.last_bundle_assembly
                        ui.Label(f"Assembly Status: {'SUCCESS' if assemb.success else 'FAILED'}")
                        if assemb.success:
                            ui.Label(f"Bundle ID: {assemb.bundle_id}", word_wrap=True)
                            ui.Label(f"Key ID: {assemb.key_id}", word_wrap=True)
                        else:
                            ui.Label(f"Error: {assemb.error}", word_wrap=True)
                    ui.Separator(height=6)
                    ui.Label("Deterministic Diff & Comparison", style={"font_size": 16})
                    ui.Label("Base Bundle (Active Release)")
                    ui.StringField(model=self._diff_base_bundle_model)
                    ui.Label("Candidate Bundle")
                    ui.StringField(model=self._diff_candidate_bundle_model)
                    ui.Button("Compute Bundle Diff", clicked_fn=self._on_diff_bundles)
                    if app_snapshot.last_bundle_diff is not None:
                        bd = app_snapshot.last_bundle_diff
                        ui.Label(f"Diff: {bd.summary}", word_wrap=True)
                        ui.Label(f"Compatible: {bd.is_compatible}")
                    ui.Separator(height=6)
                    ui.Label("Signature Verification", style={"font_size": 16})
                    ui.Label("Bundle Path")
                    ui.StringField(model=self._signature_bundle_path_model)
                    ui.Label("Trusted Keys Dir (optional)")
                    ui.StringField(model=self._signature_trusted_keys_model)
                    ui.Button(
                        "Verify Ed25519 Signature", clicked_fn=self._on_verify_bundle_signature
                    )
                    if app_snapshot.last_signature_verification is not None:
                        sv = app_snapshot.last_signature_verification
                        ui.Label(
                            f"Signature: {'[VALID]' if sv.valid else '[INVALID]'}", word_wrap=True
                        )
                        ui.Label(f"Message: {sv.message}", word_wrap=True)
                    ui.Separator(height=6)
                    ui.Label("Target Compatibility Preflight", style={"font_size": 16})
                    ui.Label("Bundle Path")
                    ui.StringField(model=self._compat_bundle_path_model)
                    ui.Label("Target Facts File")
                    ui.StringField(model=self._compat_target_facts_model)
                    ui.Button(
                        "Check Target Compatibility",
                        clicked_fn=self._on_preflight_target_compatibility,
                    )
                    if app_snapshot.last_compatibility_result is not None:
                        cr = app_snapshot.last_compatibility_result
                        compat_badge = "[COMPATIBLE]" if cr.compatible else "[INCOMPATIBLE]"
                        ui.Label(f"Compatibility: {compat_badge}")
                    ui.Separator(height=6)
                    ui.Label("Agent Status, Install & Rollback", style={"font_size": 16})
                    ui.Label("Install Root")
                    ui.StringField(model=self._agent_install_root_model)
                    ui.Label("State Root")
                    ui.StringField(model=self._agent_state_root_model)
                    with ui.HStack(spacing=4, height=28):
                        ui.Button("Agent Status", clicked_fn=self._on_refresh_deployment_status)
                        ui.Button("Install Candidate", clicked_fn=self._on_install_bundle)
                        ui.Button("Rollback Release", clicked_fn=self._on_rollback_deployment)
                    if app_snapshot.last_deployment_status is not None:
                        st = app_snapshot.last_deployment_status
                        ui.Label(
                            f"Agent State: {st.state} (Active: {st.active_bundle_id or 'none'})",
                            word_wrap=True,
                        )

    def _render_log_panel(self) -> None:
        snapshot = self._application.snapshot
        self._log_window.frame.clear()
        with self._log_window.frame:
            with ui.ScrollingFrame():
                with ui.VStack(spacing=4):
                    ui.Label("Session log", style={"font_size": 18})
                    for entry in snapshot.logs:
                        ui.Label(
                            f"{entry.sequence:04d} {entry.level.value.upper()}  {entry.message}",
                            word_wrap=True,
                        )
