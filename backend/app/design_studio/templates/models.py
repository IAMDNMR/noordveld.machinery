"""Application templates: a versioned, validated definition of one domain application's look, navigation and pages.

A template is configuration, not code. The template engine (frontend/src/templates) renders any valid definition, so a new
template is a new JSON file in `library/`, never a new UI architecture. Each part is kept separate on purpose: the theme
(design tokens), navigation, pages and their components, the modules the template supports, the abstract record roles it
expects (a "part", a "shipment"), and what it cannot do without an integration.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.schemas.application_definition import Strict

ID = r"^[a-z][a-z0-9_]{1,63}$"
HEX = r"^#[0-9a-fA-F]{6}$"


class ThemeColors(Strict):
    primary: str = Field(pattern=HEX)
    primary_text: str = Field(pattern=HEX)
    accent: str = Field(pattern=HEX)
    background: str = Field(pattern=HEX)
    surface: str = Field(pattern=HEX)
    surface_alt: str = Field(pattern=HEX)
    text: str = Field(pattern=HEX)
    muted: str = Field(pattern=HEX)
    border: str = Field(pattern=HEX)
    nav_background: str = Field(pattern=HEX)
    nav_text: str = Field(pattern=HEX)
    success: str = Field(pattern=HEX)
    warning: str = Field(pattern=HEX)
    danger: str = Field(pattern=HEX)


class ThemePreset(Strict):
    """The design tokens of one visual direction. Fonts are system stacks: generated apps load nothing from the network."""

    id: str = Field(pattern=ID)
    label: str = Field(min_length=1, max_length=60)
    direction: str = Field(min_length=1, max_length=200)
    colors: ThemeColors
    font_heading: Literal["grotesk", "humanist", "serif", "mono", "system"]
    font_body: Literal["grotesk", "humanist", "serif", "system"]
    density: Literal["compact", "comfortable", "spacious"]
    radius: int = Field(ge=0, le=20)
    shadow: Literal["none", "soft", "crisp"]
    card_style: Literal["flat", "outlined", "elevated"]
    table_style: Literal["lined", "striped", "dense"]
    touch: bool = False  # large touch targets for warehouse and field tablets


NavStyle = Literal["sidebar", "dark_sidebar", "topbar", "rail", "bottom_tabs"]
Layout = Literal["overview", "catalogue", "detail", "table", "board", "timeline", "queue", "comparison", "schedule", "form", "split"]
ComponentType = Literal[
    "metric_strip",
    "product_grid",
    "data_table",
    "detail_panel",
    "status_board",
    "timeline",
    "task_queue",
    "comparison_table",
    "alert_panel",
    "record_form",
    "schedule_week",
    "filter_bar",
]


class EntityRole(Strict):
    """A kind of record the template expects; configuration maps it to one of the project's entities."""

    id: str = Field(pattern=ID)
    label: str = Field(min_length=1, max_length=60)
    matches: list[str] = Field(min_length=1, max_length=20)  # words that identify a project entity for this role
    fields: list[str] = Field(min_length=1, max_length=20)  # the field roles its components read, in display order


class Component(Strict):
    type: ComponentType
    title: str = Field(default="", max_length=80)
    role: str | None = Field(default=None, pattern=ID)  # the entity role it shows
    fields: list[str] = Field(default_factory=list, max_length=12)
    group_by: str | None = Field(default=None, pattern=ID)  # status field for boards, metrics and alerts
    span: Literal[1, 2, 3] = 3  # columns of a three-column page grid


class Page(Strict):
    id: str = Field(pattern=ID)
    title: str = Field(min_length=1, max_length=60)
    icon: str = Field(min_length=1, max_length=40)  # a lucide-react icon name
    layout: Layout
    purpose: str = Field(min_length=1, max_length=200)
    users: list[str] = Field(default_factory=list, max_length=6)
    components: list[Component] = Field(min_length=1, max_length=8)


class Module(Strict):
    id: str = Field(pattern=ID)
    name: str = Field(min_length=1, max_length=80)
    status: Literal["supported", "configurable", "requires_integration"]
    keywords: list[str] = Field(min_length=1, max_length=20)
    note: str = Field(default="", max_length=240)  # for requires_integration: what is needed and who provides it


class Template(Strict):
    id: str = Field(pattern=ID)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=600)
    status: Literal["stable", "preview"]
    domain_ids: list[str] = Field(min_length=1, max_length=10)
    app_type: str = Field(min_length=1, max_length=40)
    users: list[str] = Field(min_length=1, max_length=8)
    keywords: list[str] = Field(min_length=1, max_length=40)
    theme: ThemePreset
    nav_style: NavStyle
    # How the generated application names its home and work queue ("Control tower", "Service desk"); wording only, never screens.
    profile: Literal["operations", "service", "requests", "workspace"] = "workspace"
    entity_roles: list[EntityRole] = Field(min_length=1, max_length=12)
    pages: list[Page] = Field(min_length=2, max_length=14)
    modules: list[Module] = Field(min_length=1, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    # Clearly fictional rows for the gallery preview only; never copied into an application.
    sample: dict[str, list[dict[str, str | int | float | bool]]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def coherent(self):
        roles = {role.id: role for role in self.entity_roles}
        if len(roles) != len(self.entity_roles):
            raise ValueError("Duplicate entity role")
        if len({page.id for page in self.pages}) != len(self.pages):
            raise ValueError("Duplicate page")
        if len({module.id for module in self.modules}) != len(self.modules):
            raise ValueError("Duplicate module")
        for page in self.pages:
            for component in page.components:
                if component.role is None:
                    if component.type not in ("metric_strip", "filter_bar"):
                        raise ValueError(f"{page.id}: {component.type} needs a role")
                    continue
                role = roles.get(component.role)
                if role is None:
                    raise ValueError(f"{page.id}: unknown role {component.role}")
                unknown = [field for field in [*component.fields, component.group_by] if field and field not in role.fields]
                if unknown:
                    raise ValueError(f"{page.id}: {component.role} has no field {', '.join(unknown)}")
        for role_id, rows in self.sample.items():
            if role_id not in roles:
                raise ValueError(f"Sample data for unknown role {role_id}")
            for row in rows:
                if set(row) - set(roles[role_id].fields) - {"id"}:
                    raise ValueError(f"Sample row for {role_id} has fields the role does not declare")
        for module in self.modules:
            if module.status == "requires_integration" and not module.note:
                raise ValueError(f"{module.id}: say what the integration needs")
        return self
