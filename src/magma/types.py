"""Shared data types for the Magma query engine."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CPGNode:
    """A node in the Code Property Graph."""

    id: int
    type: str
    label: str
    line_number: int | None = None
    file: str | None = None
    properties: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CPGEdge:
    """An edge in the Code Property Graph."""

    source: int
    target: int
    type: str


@dataclass
class Finding:
    """A detected vulnerability finding."""

    vuln_type: str
    file: str
    line: int
    description: str
    path: list[int] | None = None

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for future MQL integration."""
        result = {
            "vuln_type": self.vuln_type,
            "file": self.file,
            "line": self.line,
            "description": self.description,
        }
        if self.path is not None:
            result["path"] = self.path
        return result
