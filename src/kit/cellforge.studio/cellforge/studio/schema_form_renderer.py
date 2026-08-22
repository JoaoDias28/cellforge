"""Reusable presentation renderer for immutable schema form DTOs.

This module deliberately contains no JSON Schema or CellForge domain policy.  It maps the
service-owned :class:`SchemaFormModel` into a small widget-neutral render tree that Kit, a web
surface, or a headless test can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cellforge.studio.schema_authoring import (
    AuthoringChoice,
    SchemaFormField,
    SchemaFormGroup,
    SchemaFormModel,
)


@dataclass(frozen=True, slots=True)
class RenderedSchemaField:
    """One renderer output field with service-provided presentation metadata."""

    path: str
    label: str
    widget: str
    group: str
    value: Any
    required: bool
    advanced: bool
    generated: bool
    unit: str | None
    minimum: float | int | None
    maximum: float | int | None
    exclusive_minimum: float | int | bool | None
    exclusive_maximum: float | int | bool | None
    enum: tuple[Any, ...]
    description: str | None
    help: str | None


@dataclass(frozen=True, slots=True)
class RenderedSchemaGroup:
    """One stable group of renderer fields."""

    name: str
    order: int
    advanced: bool
    fields: tuple[RenderedSchemaField, ...]


@dataclass(frozen=True, slots=True)
class RenderedSchemaForm:
    """Widget-neutral render tree and service-owned validation state."""

    title: str
    schema_kind: str
    schema_version: str | None
    source_path: str
    groups: tuple[RenderedSchemaGroup, ...]
    choices: tuple[AuthoringChoice, ...]
    findings: tuple[Any, ...]
    can_save: bool

    @property
    def fields(self) -> tuple[RenderedSchemaField, ...]:
        return tuple(field for group in self.groups for field in group.fields)


class SchemaFormRenderer:
    """Map :class:`SchemaFormModel` values to reusable presentation data."""

    def render(self, form: SchemaFormModel) -> RenderedSchemaForm:
        """Render a form without evaluating or duplicating any schema/domain rule."""

        groups = tuple(self._render_group(group) for group in form.groups)
        return RenderedSchemaForm(
            title=form.title,
            schema_kind=form.schema_kind,
            schema_version=form.schema_version,
            source_path=form.source_path,
            groups=groups,
            choices=form.choices,
            findings=form.findings,
            can_save=form.can_save,
        )

    def Render(self, form: SchemaFormModel) -> RenderedSchemaForm:
        """Exact command-style alias for headless and Kit callers."""

        return self.render(form)

    @staticmethod
    def _render_group(group: SchemaFormGroup) -> RenderedSchemaGroup:
        return RenderedSchemaGroup(
            name=group.name,
            order=group.order,
            advanced=group.advanced,
            fields=tuple(SchemaFormRenderer._render_field(field) for field in group.fields),
        )

    @staticmethod
    def _render_field(field: SchemaFormField) -> RenderedSchemaField:
        return RenderedSchemaField(
            path=field.path,
            label=field.label,
            widget=field.widget,
            group=field.group,
            value=field.value,
            required=field.required,
            advanced=field.advanced,
            generated=field.generated,
            unit=field.unit,
            minimum=field.minimum,
            maximum=field.maximum,
            exclusive_minimum=field.exclusive_minimum,
            exclusive_maximum=field.exclusive_maximum,
            enum=field.enum,
            description=field.description,
            help=field.help,
        )


def render_schema_form(form: SchemaFormModel) -> RenderedSchemaForm:
    """Convenience function for non-Kit renderers."""

    return SchemaFormRenderer().render(form)


__all__ = [
    "RenderedSchemaField",
    "RenderedSchemaForm",
    "RenderedSchemaGroup",
    "SchemaFormRenderer",
    "render_schema_form",
]
