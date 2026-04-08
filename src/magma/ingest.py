"""Joern CLI wrapper and CPG DOT parser."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from magma.types import CPGEdge, CPGNode


class JoernError(Exception):
    """Raised when Joern CLI fails or is not available."""


# Joern node type constants
NODE_TYPE_CALL = "CALL"
NODE_TYPE_IDENTIFIER = "IDENTIFIER"
NODE_TYPE_FIELD_IDENTIFIER = "FIELD_IDENTIFIER"
NODE_TYPE_LITERAL = "LITERAL"
NODE_TYPE_BLOCK = "BLOCK"
NODE_TYPE_METHOD = "METHOD"
NODE_TYPE_METHOD_RETURN = "METHOD_RETURN"
NODE_TYPE_LOCAL = "LOCAL"
NODE_TYPE_UNKNOWN = "UNKNOWN"

# Joern edge type constants
EDGE_TYPE_AST = "AST"
EDGE_TYPE_CFG = "CFG"
EDGE_TYPE_REACHING_DEF = "REACHING_DEF"
EDGE_TYPE_CDG = "CDG"
EDGE_TYPE_EVAL_TYPE = "EVAL_TYPE"
EDGE_TYPE_REF = "REF"

# Regex patterns for parsing Joern DOT export
# Node line:   "25769803776" [label="BLOCK" CODE="..." LINE_NUMBER="3" ...];
_NODE_RE = re.compile(
    r'"(?P<id>\d+)"\s+\[(?P<attrs>[^\]]+)\];'
)
# Edge line:   "30064771076" -> "68719476738" [label="REACHING_DEF" ...];
_EDGE_RE = re.compile(
    r'"(?P<src>\d+)"\s+->\s+"(?P<tgt>\d+)"\s+\[(?P<attrs>[^\]]+)\];'
)
# Key="value" pairs inside node/edge attributes
_ATTR_RE = re.compile(r'(?P<key>\w+)="(?P<value>[^"]*)"')


def _parse_attrs(attr_str: str) -> dict[str, str]:
    """Parse DOT attribute string into a dict."""
    return {m.group("key"): m.group("value") for m in _ATTR_RE.finditer(attr_str)}


def run_joern(file_path: Path, output_dir: Path) -> Path:
    """Run Joern CLI to parse a C file and export the CPG as DOT.

    Args:
        file_path: Path to the C source file.
        output_dir: Directory to write the exported CPG DOT.

    Returns:
        Path to the exported DOT file.

    Raises:
        JoernError: If joern-parse or joern-export fails or is not found.
    """
    file_path = Path(file_path).resolve()
    output_dir = Path(output_dir).resolve()

    # joern-export requires the output directory to NOT exist.
    # Ensure parent exists but use a unique child path that doesn't exist yet.
    import uuid
    output_dir.mkdir(parents=True, exist_ok=True)
    export_dir = output_dir / str(uuid.uuid4())[:8]

    # Check joern-parse is available
    try:
        subprocess.run(
            ["which", "joern-parse"],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise JoernError(
            "joern-parse not found. Install Joern: https://joern.io/"
        ) from None

    # Parse the C file
    parse_result = subprocess.run(
        ["joern-parse", str(file_path)],
        capture_output=True,
        text=True,
    )
    if parse_result.returncode != 0:
        raise JoernError(f"joern-parse failed: {parse_result.stderr}")

    # Export CPG as DOT
    export_result = subprocess.run(
        ["joern-export", "--repr", "all", "--format", "dot", "-o", str(export_dir)],
        capture_output=True,
        text=True,
    )
    if export_result.returncode != 0:
        # Filter JVM warnings from stderr
        stderr_lines = [
            line for line in export_result.stderr.splitlines()
            if not line.startswith("WARNING:")
        ]
        raise JoernError(f"joern-export failed: {''.join(stderr_lines)}")

    # Find the exported DOT files
    dot_files = list(export_dir.glob("*.dot"))
    if not dot_files:
        raise JoernError(f"No DOT files found in {export_dir} after joern-export")

    return dot_files[0]


def load_cpg(dot_path: Path) -> tuple[list[CPGNode], list[CPGEdge]]:
    """Parse a Joern DOT CPG export into node and edge lists.

    Args:
        dot_path: Path to the Joern DOT export file.

    Returns:
        Tuple of (nodes, edges) lists.

    Raises:
        JoernError: If the DOT file cannot be parsed.
    """
    dot_path = Path(dot_path)
    if not dot_path.exists():
        raise JoernError(f"CPG DOT file not found: {dot_path}")

    try:
        text = dot_path.read_text()
    except OSError as e:
        raise JoernError(f"Cannot read {dot_path}: {e}") from e

    nodes: list[CPGNode] = []
    edges: list[CPGEdge] = []

    for line in text.splitlines():
        # Try edge match first (more specific pattern with ->)
        m = _EDGE_RE.search(line)
        if m:
            source = int(m.group("src"))
            target = int(m.group("tgt"))
            attrs = _parse_attrs(m.group("attrs"))
            edge_type = attrs.get("label", "UNKNOWN")
            edges.append(CPGEdge(
                source=source,
                target=target,
                type=edge_type,
            ))
            continue

        # Try node match
        m = _NODE_RE.search(line)
        if m:
            node_id = int(m.group("id"))
            attrs = _parse_attrs(m.group("attrs"))
            node_type = attrs.get("label", NODE_TYPE_UNKNOWN)
            label = attrs.get("CODE", attrs.get("NAME", ""))
            line_number_str = attrs.get("LINE_NUMBER")
            line_number = int(line_number_str) if line_number_str else None
            filename = attrs.get("FILENAME")
            properties = {
                k: v for k, v in attrs.items()
                if k not in ("label", "CODE", "LINE_NUMBER", "FILENAME")
            }
            nodes.append(CPGNode(
                id=node_id,
                type=node_type,
                label=label,
                line_number=line_number,
                file=filename,
                properties=properties,
            ))

    return nodes, edges
