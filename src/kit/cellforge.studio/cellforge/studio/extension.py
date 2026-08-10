"""Isaac Sim 6 / Omniverse Kit UI adapter for the Cell Studio shell."""

import omni.ext
import omni.ui as ui

from cellforge.studio.application import BrowserComponent, ComponentFilters, StudioApplication
from cellforge.studio.backend import create_default_application

PROJECT_WINDOW = "CellForge Project"
VALIDATION_WINDOW = "CellForge Validation"
LOG_WINDOW = "CellForge Log"
COMPONENT_WINDOW = "CellForge Components"


class CellForgeStudioExtension(omni.ext.IExt):
    """Own the three shell windows for the lifetime of the Kit extension."""

    def on_startup(self, ext_id: str) -> None:
        """Create a read-only empty shell; startup never opens a project."""

        self._ext_id = ext_id
        self._application: StudioApplication | None = create_default_application()
        self._project_path_model = ui.SimpleStringModel("")
        self._kind_filter_model = ui.SimpleStringModel("")
        self._capability_filter_model = ui.SimpleStringModel("")
        self._support_filter_model = ui.SimpleStringModel("")
        self._simulation_filter_model = ui.SimpleStringModel("")
        self._remove_instance_model = ui.SimpleStringModel("")
        self._project_window = ui.Window(PROJECT_WINDOW, width=360, height=420)
        self._component_window = ui.Window(COMPONENT_WINDOW, width=460, height=520)
        self._validation_window = ui.Window(VALIDATION_WINDOW, width=460, height=420)
        self._log_window = ui.Window(LOG_WINDOW, width=820, height=220)
        self._render_all()
        ui.dock_window_in_window(VALIDATION_WINDOW, PROJECT_WINDOW, ui.DockPosition.RIGHT, 0.55)
        ui.dock_window_in_window(COMPONENT_WINDOW, PROJECT_WINDOW, ui.DockPosition.LEFT, 0.55)
        ui.dock_window_in_window(LOG_WINDOW, PROJECT_WINDOW, ui.DockPosition.BOTTOM, 0.35)

    def on_shutdown(self) -> None:
        """Release all UI references so Kit can unload the extension cleanly."""

        for window_name in (
            "_project_window",
            "_component_window",
            "_validation_window",
            "_log_window",
        ):
            window = getattr(self, window_name, None)
            if window is not None:
                window.visible = False
                window.frame.clear()
                setattr(self, window_name, None)
        self._application = None
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

    def _on_undo(self) -> None:
        if self._application is not None:
            self._application.undo()
            self._render_all()

    def _on_redo(self) -> None:
        if self._application is not None:
            self._application.redo()
            self._render_all()

    def _render_all(self) -> None:
        self._render_project_panel()
        self._render_component_panel()
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
