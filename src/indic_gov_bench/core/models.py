"""models3.py — Strict Pydantic Data Models for Ground Truth Reference and Provider Predictions (v3).

Implements §5, §9.1, and §17 of specs/benchmark_format_metrics_spec.md and specs/new_format.md.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class BlockType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    FIGURE = "figure"


class BlockScope(str, Enum):
    TARGET = "target"
    EXCLUDED = "excluded"
    UNCERTAIN = "uncertain"


class ExcludeReason(str, Enum):
    NEIGHBORING_DOCUMENT = "neighboring_document"
    ADJACENT_PAGE_EDGE = "adjacent_page_edge"
    UNRELATED_STICKER = "unrelated_sticker"
    UNRELATED_HANDWRITING = "unrelated_handwriting"
    SCANNER_PAGE_NUMBER = "scanner_page_number"
    SCANNER_ARTIFACT = "scanner_artifact"
    BLEED_THROUGH = "bleed_through"
    PURE_SIGNATURE = "pure_signature"
    GRAPHICAL_SEAL = "graphical_seal"
    ILLUSTRATION = "illustration"
    BARCODE = "barcode"
    RANDOM_MARK = "random_mark"
    UNASSIGNABLE = "unassignable"
    ILLEGIBLE = "illegible"


class ImageInfo(BaseModel):
    path: str = Field(..., description="Path to image file relative to dataset root")
    width: int = Field(..., gt=0, description="Image width in pixels")
    height: int = Field(..., gt=0, description="Image height in pixels")


class DocumentInfo(BaseModel):
    pdf_path: str | None = Field(
        None, description="Path to source PDF file relative to dataset root"
    )


class BlockRecord(BaseModel):
    id: int = Field(..., ge=0, description="Unique block ID within the page")
    type: Literal["text", "table", "figure"]
    scope: Literal["target", "excluded", "uncertain"]
    order: int | None = Field(
        None, ge=0, description="Dense reading order index for target blocks"
    )
    poly: list[float] = Field(
        ...,
        min_length=8,
        max_length=8,
        description="Clockwise quadrilateral [x1,y1,x2,y2,x3,y3,x4,y4]",
    )
    text: str | None = None
    html: str | None = None
    reason: str | None = None
    content: str | None = None
    doc_category: str | None = None

    @field_validator("poly")
    @classmethod
    def validate_poly_floats(cls, v: list[float]) -> list[float]:
        if len(v) != 8:
            raise ValueError(f"poly must have exactly 8 elements, got {len(v)}")
        return [float(x) for x in v]

    @model_validator(mode="after")
    def validate_content_constraints(self) -> BlockRecord:
        # §5.3 Constraints
        if self.type == "figure":
            if self.scope != "excluded":
                raise ValueError(
                    f"Figure block (id={self.id}) must have scope='excluded', got '{self.scope}'"
                )
            if self.text is not None or self.html is not None:
                raise ValueError(
                    f"Figure block (id={self.id}) must have text=null and html=null"
                )
            if self.order is not None:
                raise ValueError(f"Figure block (id={self.id}) must have order=null")
            if not self.reason:
                raise ValueError(
                    f"Figure block (id={self.id}) must have a non-null reason"
                )

        elif self.type == "text":
            if self.html is not None:
                raise ValueError(f"Text block (id={self.id}) must have html=null")
            if self.scope == "target":
                if not self.text or not self.text.strip():
                    raise ValueError(
                        f"Target text block (id={self.id}) must have non-empty text"
                    )
                if self.order is None:
                    raise ValueError(
                        f"Target text block (id={self.id}) must have integer order"
                    )
                if self.reason is not None:
                    raise ValueError(
                        f"Target text block (id={self.id}) must have reason=null"
                    )
            elif self.scope == "excluded":
                if not self.text or not self.text.strip():
                    raise ValueError(
                        f"Excluded text block (id={self.id}) must have non-empty text"
                    )
                if self.order is not None:
                    raise ValueError(
                        f"Excluded text block (id={self.id}) must have order=null"
                    )
                if not self.reason:
                    raise ValueError(
                        f"Excluded text block (id={self.id}) must have non-null reason"
                    )
            elif self.scope == "uncertain":
                if self.text is not None:
                    raise ValueError(
                        f"Uncertain text block (id={self.id}) must have text=null"
                    )
                if self.order is not None:
                    raise ValueError(
                        f"Uncertain text block (id={self.id}) must have order=null"
                    )
                if self.reason != ExcludeReason.ILLEGIBLE.value:
                    raise ValueError(
                        f"Uncertain text block (id={self.id}) must have reason='illegible', got '{self.reason}'"
                    )

        elif self.type == "table":
            if self.text is not None:
                raise ValueError(f"Table block (id={self.id}) must have text=null")
            if self.scope == "target":
                if not self.html or not self.html.strip():
                    raise ValueError(
                        f"Target table block (id={self.id}) must have non-empty html"
                    )
                if self.order is None:
                    raise ValueError(
                        f"Target table block (id={self.id}) must have integer order"
                    )
                if self.reason is not None:
                    raise ValueError(
                        f"Target table block (id={self.id}) must have reason=null"
                    )
            elif self.scope == "excluded":
                if not self.html or not self.html.strip():
                    raise ValueError(
                        f"Excluded table block (id={self.id}) must have non-empty html"
                    )
                if self.order is not None:
                    raise ValueError(
                        f"Excluded table block (id={self.id}) must have order=null"
                    )
                if not self.reason:
                    raise ValueError(
                        f"Excluded table block (id={self.id}) must have non-null reason"
                    )
            elif self.scope == "uncertain":
                if self.html is not None:
                    raise ValueError(
                        f"Uncertain table block (id={self.id}) must have html=null"
                    )
                if self.order is not None:
                    raise ValueError(
                        f"Uncertain table block (id={self.id}) must have order=null"
                    )
                if self.reason != ExcludeReason.ILLEGIBLE.value:
                    raise ValueError(
                        f"Uncertain table block (id={self.id}) must have reason='illegible', got '{self.reason}'"
                    )

        return self


class GroundTruthDocument(BaseModel):
    doc_id: str = Field(..., min_length=1)
    document: DocumentInfo | None = None
    image: ImageInfo
    blocks: list[BlockRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reading_order_density(self) -> GroundTruthDocument:
        # §5.4 Reading order density
        target_blocks = [b for b in self.blocks if b.scope == "target"]
        if target_blocks:
            orders = [b.order for b in target_blocks if b.order is not None]
            if len(orders) != len(target_blocks):
                raise ValueError(
                    f"Every target block must have an order integer in doc {self.doc_id}"
                )
            sorted_orders = sorted(orders)
            expected_orders = list(range(len(target_blocks)))
            if sorted_orders != expected_orders:
                raise ValueError(
                    f"Reading order in {self.doc_id} must be dense 0..{len(target_blocks) - 1}, got {sorted_orders}"
                )
        return self


class PredictionBlock(BaseModel):
    id: int = Field(..., ge=0)
    type: Literal["text", "table", "figure"] = "text"
    order: int | None = Field(None, ge=0)
    poly: list[float] | None = Field(
        None, description="Optional for pure markdown submissions"
    )
    text: str | None = None
    html: str | None = None

    @field_validator("poly")
    @classmethod
    def validate_poly_floats(cls, v: list[float] | None) -> list[float] | None:
        if v is not None:
            if len(v) != 8:
                raise ValueError(
                    f"poly must have exactly 8 elements if present, got {len(v)}"
                )
            return [float(x) for x in v]
        return None


class PredictionDocument(BaseModel):
    doc_id: str = Field(..., min_length=1)
    blocks: list[PredictionBlock] = Field(default_factory=list)
    usage_and_cost: dict[str, Any] | None = None

