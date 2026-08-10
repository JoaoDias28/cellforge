"""Isaac Sim 6 / Omniverse Kit UI adapter for the Cell Studio shell."""

import omni.ext
import omni.ui as ui

from cellforge.studio.application import StudioApplication
from cellforge.studio.backend import create_default_application

PROJECT_WINDOW = "CellForge Project"
VALIDATION_WINDOW = "CellForge Validation"
LOG_WINDOW = "CellForge Log"


class CellForgeStudioExtension(omni.ext.IExt):
    """Own the three shell windows for the lifetime of the Kit extension."""

    def on_startup(self, ext_id: str) -> None:
        """Create a read-only empty shell; startup never opens a project."""

        self._ext_id = ext_id
        self._application: StudioApplication | None = create_default_application()
        self._project_path_model = ui.SimpleStringModel("")
        self._project_window = ui.Window(PROJECT_WINDOW, width=360, height=420)
        self._validation_window = ui.Window(VALIDATION_WINDOW, width=460, height=420)
        self._log_window = ui.Window(LOG_WINDOW, width=820, height=220)
        self._render_all()
        ui.dock_window_in_window(VALIDATION_WINDOW, PROJECT_WINDOW, ui.DockPosition.RIGHT, 0.55)
        ui.dock_window_in_window(LOG_WINDOW, PROJECT_WINDOW, ui.DockPosition.BOTTOM, 0.35)

    def on_shutdown(self) -> None:
        """Release all UI references so Kit can unload the extension cleanly."""

        for window_name in ("_project_window", "_validation_window", "_log_window"):
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

    def _render_all(self) -> None:
        self._render_project_panel()
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
