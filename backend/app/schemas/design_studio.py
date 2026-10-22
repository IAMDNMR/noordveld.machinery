from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FieldType = Literal["text", "number", "email", "telephone", "date", "select", "checkbox", "file"]


class ValidationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["required", "email", "min_length", "max_length", "pattern"]
    value: str | int | bool | None = None
    message: str | None = None

    @model_validator(mode="after")
    def safe_pattern(self):
        if self.kind == "pattern" and self.value not in ("digits", "letters", "alphanumeric"):
            raise ValueError("Pattern must be digits, letters, or alphanumeric")
        return self


class ScreenField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    type: FieldType
    label: str = Field(min_length=1, max_length=120)
    help_text: str | None = Field(default=None, max_length=500)
    options: list[str] = Field(default_factory=list, max_length=100)
    validations: list[ValidationRule] = Field(default_factory=list, max_length=20)


class ScreenSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=120)
    fields: list[ScreenField] = Field(default_factory=list, max_length=100)


class ScreenTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,63}$")
    title: str = Field(min_length=1, max_length=120)
    columns: list[str] = Field(min_length=1, max_length=30)
    searchable: bool = False
    filters: list[str] = Field(default_factory=list, max_length=20)
    page_size: int = Field(default=20, ge=1, le=100)


class ScreenSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    purpose: str = Field(default="", max_length=1000)
    layout: Literal["single", "two-column"] = "single"
    sections: list[ScreenSection] = Field(min_length=1, max_length=30)
    tables: list[ScreenTable] = Field(default_factory=list, max_length=20)
    buttons: list[str] = Field(default_factory=lambda: ["Save"], max_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        section_ids = [section.id for section in self.sections]
        field_ids = [field.id for section in self.sections for field in section.fields]
        if len(set(section_ids)) != len(section_ids) or len(set(field_ids)) != len(field_ids):
            raise ValueError("Section and field IDs must be unique")
        if len({table.id for table in self.tables}) != len(self.tables):
            raise ValueError("Table IDs must be unique")
        return self


class DesignDraft(BaseModel):
    id: str
    owner_id: str
    spec: ScreenSpec
    created_at: datetime
    updated_at: datetime
    revision: int = Field(default=1, ge=1)


class DesignGenerateRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    design_id: str | None = None
    current_spec: ScreenSpec | None = None
    provider: Literal["nvidia", "nvidia-lightning", "groq", "gemini"] | None = None


class DesignGenerateResponse(BaseModel):
    spec: ScreenSpec
    assistant_message: str
    provider: str
    model: str


class DesignDraftRequest(BaseModel):
    spec: ScreenSpec
    expected_revision: int | None = Field(default=None, ge=1)
