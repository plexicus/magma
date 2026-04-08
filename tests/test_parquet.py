"""Tests for the Parquet CPG serialization module."""

from __future__ import annotations

from pathlib import Path

import pytest

from magma.parquet import export_parquet, load_parquet
from magma.types import CPGEdge, CPGNode


class TestParquetRoundTrip:
    """Test export → load round-trip preserves data."""

    def test_round_trip_simple(self, tmp_path: Path) -> None:
        """Export and reload produces identical nodes and edges."""
        nodes = [
            CPGNode(id=0, type="CALL", label="free(ptr)", line_number=3, file="test.c"),
            CPGNode(id=1, type="IDENTIFIER", label="ptr", line_number=3, file="test.c"),
            CPGNode(id=2, type="CALL", label="*ptr = 1", line_number=4, file="test.c"),
        ]
        edges = [
            CPGEdge(source=0, target=1, type="AST"),
            CPGEdge(source=0, target=2, type="REACHING_DEF"),
        ]
        path = tmp_path / "test.parquet"
        export_parquet(nodes, edges, path)

        loaded_nodes, loaded_edges = load_parquet(path)

        assert len(loaded_nodes) == len(nodes)
        assert len(loaded_edges) == len(edges)
        for orig, loaded in zip(nodes, loaded_nodes, strict=False):
            assert orig.id == loaded.id
            assert orig.type == loaded.type
            assert orig.label == loaded.label
            assert orig.line_number == loaded.line_number
            assert orig.file == loaded.file
            assert orig.properties == loaded.properties
        for orig, loaded in zip(edges, loaded_edges, strict=False):
            assert orig.source == loaded.source
            assert orig.target == loaded.target
            assert orig.type == loaded.type

    def test_round_trip_with_properties(self, tmp_path: Path) -> None:
        """Properties dict survives round-trip."""
        nodes = [
            CPGNode(
                id=0, type="CALL", label="free(ptr)", line_number=3,
                file="test.c",
                properties={"METHOD_FULL_NAME": "free", "DISPATCH_TYPE": "STATIC"},
            ),
        ]
        edges = []
        path = tmp_path / "props.parquet"
        export_parquet(nodes, edges, path)

        loaded_nodes, _ = load_parquet(path)
        assert loaded_nodes[0].properties["METHOD_FULL_NAME"] == "free"
        assert loaded_nodes[0].properties["DISPATCH_TYPE"] == "STATIC"

    def test_round_trip_null_fields(self, tmp_path: Path) -> None:
        """Nodes with None line_number and file survive round-trip."""
        nodes = [
            CPGNode(id=0, type="METHOD", label="main", line_number=None, file=None),
        ]
        edges = []
        path = tmp_path / "nulls.parquet"
        export_parquet(nodes, edges, path)

        loaded_nodes, _ = load_parquet(path)
        assert loaded_nodes[0].line_number is None
        assert loaded_nodes[0].file is None

    def test_round_trip_empty(self, tmp_path: Path) -> None:
        """Empty graph survives round-trip."""
        path = tmp_path / "empty.parquet"
        export_parquet([], [], path)

        nodes, edges = load_parquet(path)
        assert len(nodes) == 0
        assert len(edges) == 0

    def test_round_trip_multiple_edge_types(self, tmp_path: Path) -> None:
        """Multiple edge types produce correct CSR index."""
        nodes = [
            CPGNode(id=0, type="CALL", label="a", line_number=1, file="t.c"),
            CPGNode(id=1, type="CALL", label="b", line_number=2, file="t.c"),
            CPGNode(id=2, type="CALL", label="c", line_number=3, file="t.c"),
        ]
        edges = [
            CPGEdge(source=0, target=1, type="AST"),
            CPGEdge(source=1, target=2, type="CFG"),
            CPGEdge(source=0, target=2, type="REACHING_DEF"),
        ]
        path = tmp_path / "multi.parquet"
        export_parquet(nodes, edges, path)

        loaded_nodes, loaded_edges = load_parquet(path)
        assert len(loaded_nodes) == 3
        assert len(loaded_edges) == 3
        edge_types = {e.type for e in loaded_edges}
        assert edge_types == {"AST", "CFG", "REACHING_DEF"}


class TestParquetFileSize:
    """Test that Parquet files are smaller than DOT."""

    def test_smaller_than_dot(self, tmp_path: Path) -> None:
        """Parquet file is smaller than equivalent DOT text for larger graphs."""
        # Use realistic data: repeated types, longer labels, many edges
        node_types = ["CALL", "IDENTIFIER", "LITERAL", "METHOD", "BLOCK"]
        nodes = [
            CPGNode(
                id=i,
                type=node_types[i % len(node_types)],
                label=f"some_long_function_name_with_args_{i}(ptr, size, offset)",
                line_number=i * 3 + 10,
                file="src/vulnerability/corner_case_handler.c",
                properties={"METHOD_FULL_NAME": f"com.example.Handler.process{i}"},
            )
            for i in range(500)
        ]
        # Dense edges: each node connects to several others
        edges = []
        for i in range(500):
            for j in range(1, min(5, 500 - i)):
                edges.append(CPGEdge(source=i, target=i + j, type="REACHING_DEF"))
            if i > 0:
                edges.append(CPGEdge(source=i - 1, target=i, type="AST"))
                edges.append(CPGEdge(source=i - 1, target=i, type="CFG"))

        # Write Parquet
        pq_path = tmp_path / "test.parquet"
        export_parquet(nodes, edges, pq_path)

        # Write equivalent DOT
        dot_path = tmp_path / "test.dot"
        dot_lines = ["digraph {"]
        for n in nodes:
            dot_lines.append(f'  "{n.id}" [label="{n.type}" CODE="{n.label}" LINE_NUMBER="{n.line_number}"];')
        for e in edges:
            dot_lines.append(f'  "{e.source}" -> "{e.target}" [label="{e.type}"];')
        dot_lines.append("}")
        dot_path.write_text("\n".join(dot_lines))

        pq_size = sum(f.stat().st_size for f in pq_path.glob("*.parquet"))
        dot_size = dot_path.stat().st_size
        assert pq_size < dot_size, (
            f"Parquet ({pq_size}B) should be smaller than DOT ({dot_size}B)"
        )
