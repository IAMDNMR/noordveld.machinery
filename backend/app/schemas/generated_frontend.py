"""Versioned source and build output, written only by the frontend generation service."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class FrontendPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=500)
    step_ids: list[str] = Field(default_factory=list, max_length=200)
    entity_ids: list[str] = Field(default_factory=list, max_length=100)
    surface_ids: list[str] = Field(default_factory=list)


class FrontendProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    design_summary: str = Field(min_length=20, max_length=2000)
    pages: list[FrontendPage] = Field(min_length=1)
    files: dict[str, str] = Field(min_length=2)


class GeneratedFrontend(FrontendProposal):
    version: Literal[1] = 1
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider: str = Field(max_length=120)
    generated_at: str
    bundle_js: str = Field(max_length=8_000_000)
    bundle_css: str = Field(max_length=500_000)
    checks: list[str]
    sdk_source: str = Field(max_length=100_000)
    entry_source: str = Field(max_length=20_000)
