"""Spark composes existing read-only tools; the model supplies language, never facts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.agent import AgentResponse
from app.schemas.intelligence import QueryResponse, SelectedEntity


class SparkPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    intelligence: str | None = Field(min_length=2, max_length=300)
    shopping: str | None = Field(min_length=2, max_length=400)
    account: str | None = Field(min_length=2, max_length=500)
    clarification: str | None = Field(max_length=500)
    #: what the user wants to see: a direct answer (default), options side by side, numbers as a chart, or the graph
    view: Literal["answer", "compare", "chart", "graph"] = "answer"
    reuse_previous: bool = False
    #: the offered part label the user wants to order now; the server resolves it and starts the guided order
    order: str | None = Field(default=None, max_length=80)

    @field_validator("view", mode="before")
    @classmethod
    def _plain_view(cls, value):
        # presentation is a preference, not a fact: an unknown value falls back to a plain answer instead of failing the request
        return value if value in ("answer", "compare", "chart", "graph") else "answer"


class SparkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=500)
    context: str | None = Field(default=None, max_length=24000)
    selected: list[SelectedEntity] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=12, ge=1, le=40)
    #: the part of the order the user is in the middle of, so 'it' can mean that part; the server re-reads it
    order_part: dict[str, str] | None = Field(default=None, max_length=3)


class SparkStep(BaseModel):
    label: str
    status: Literal["completed", "failed", "sign_in_required", "access_denied"]
    ms: int


class TableRow(BaseModel):
    key: str
    title: str
    part_number: str | None = None
    cells: list[str | None]


class TableSpec(BaseModel):
    columns: list[str]
    rows: list[TableRow]


class ChartRow(BaseModel):
    name: str
    value: float


class ChartSpec(BaseModel):
    metric: str
    rows: list[ChartRow]


class SparkPresentation(BaseModel):
    """How each part of the reply is shown. Chosen by the server from the plan and the verified records; text is the default."""

    intelligence: Literal["text", "table", "cards", "chart", "graph", "choices"] | None = None
    shopping: Literal["text", "product", "compare"] | None = None
    account: Literal["text", "detail"] | None = None
    table: TableSpec | None = None
    chart: ChartSpec | None = None
    #: why a requested presentation was not used (for example nothing numeric to chart)
    note: str | None = None


class SparkResponse(BaseModel):
    message: str
    context: str
    intelligence: QueryResponse | None = None
    shopping: AgentResponse | None = None
    account: dict | None = None
    sign_in_required: bool = False
    warnings: list[str] = Field(default_factory=list)
    steps: list[SparkStep] = Field(default_factory=list)
    view: Literal["answer", "compare", "chart", "graph"] = "answer"
    presentation: SparkPresentation = Field(default_factory=SparkPresentation)
    #: consented profile details Spark used to complete this request, shown to the user
    profile_used: list[str] = Field(default_factory=list)
    #: set when the user asked to order an offered part: the client starts the guided order with it
    order_part: dict | None = None
