"""Tests for the Joern ingestion layer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from magma.ingest import JoernError, load_cpg, run_joern


SAMPLE_DOT = """\
digraph {
  "0" [label="CALL" CODE="free(ptr)" LINE_NUMBER="3"];
  "1" [label="IDENTIFIER" CODE="ptr" LINE_NUMBER="3"];
  "2" [label="CALL" CODE="*ptr = 1" LINE_NUMBER="4"];
  "0" -> "1" [label="AST"];
  "0" -> "2" [label="REACHING_DEF" property="free(ptr)"];
}
"""


class TestLoadCpg:
    """Tests for load_cpg DOT parser."""

    def test_loads_nodes_and_edges(self, tmp_path: Path) -> None:
        """Test parsing a Joern-format DOT with nodes and edges."""
        dot_path = tmp_path / "cpg.dot"
        dot_path.write_text(SAMPLE_DOT)

        nodes, edges = load_cpg(dot_path)

        assert len(nodes) == 3
        assert len(edges) == 2
        assert nodes[0].type == "CALL"
        assert nodes[0].label == "free(ptr)"
        assert nodes[0].line_number == 3
        assert edges[0].source == 0
        assert edges[0].target == 1
        assert edges[0].type == "AST"
        assert edges[1].type == "REACHING_DEF"

    def test_handles_missing_file(self, tmp_path: Path) -> None:
        """Test that missing file raises JoernError."""
        with pytest.raises(JoernError, match="not found"):
            load_cpg(tmp_path / "nonexistent.dot")

    def test_handles_empty_dot(self, tmp_path: Path) -> None:
        """Test parsing an empty DOT graph."""
        dot_path = tmp_path / "empty.dot"
        dot_path.write_text("digraph {\n}\n")

        nodes, edges = load_cpg(dot_path)
        assert len(nodes) == 0
        assert len(edges) == 0

    def test_preserves_extra_properties(self, tmp_path: Path) -> None:
        """Test that extra DOT attributes are preserved in CPGNode properties."""
        dot_text = 'digraph {\n  "1" [label="CALL" CODE="free(ptr)" LINE_NUMBER="3" METHOD_FULL_NAME="free" DISPATCH_TYPE="STATIC_DISPATCH"];\n}\n'
        dot_path = tmp_path / "props.dot"
        dot_path.write_text(dot_text)

        nodes, _ = load_cpg(dot_path)
        assert "METHOD_FULL_NAME" in nodes[0].properties
        assert nodes[0].properties["METHOD_FULL_NAME"] == "free"
        assert nodes[0].properties["DISPATCH_TYPE"] == "STATIC_DISPATCH"

    def test_handles_nodes_without_line_numbers(self, tmp_path: Path) -> None:
        """Test that nodes without LINE_NUMBER parse correctly."""
        dot_text = 'digraph {\n  "1" [label="METHOD" CODE="main"];\n}\n'
        dot_path = tmp_path / "no_line.dot"
        dot_path.write_text(dot_text)

        nodes, _ = load_cpg(dot_path)
        assert len(nodes) == 1
        assert nodes[0].line_number is None

    def test_handles_filename_attribute(self, tmp_path: Path) -> None:
        """Test that FILENAME attribute is captured."""
        dot_text = 'digraph {\n  "1" [label="FILE" CODE="" FILENAME="test.c"];\n}\n'
        dot_path = tmp_path / "file.dot"
        dot_path.write_text(dot_text)

        nodes, _ = load_cpg(dot_path)
        assert nodes[0].file == "test.c"

    def test_parses_real_joern_export(self, tmp_path: Path) -> None:
        """Test parsing a realistic DOT export from Joern."""
        dot_text = """\
digraph {
  "30064771076" [label="CALL" CODE="free(ptr)" LINE_NUMBER="5" METHOD_FULL_NAME="free"];
  "68719476738" [label="IDENTIFIER" CODE="ptr" LINE_NUMBER="5" NAME="ptr"];
  "30064771077" [label="CALL" CODE="*ptr = 1" LINE_NUMBER="6" METHOD_FULL_NAME="<operator>.assignment"];
  "30064771076" -> "68719476738" [label="AST" ];
  "30064771076" -> "30064771077" [label="REACHING_DEF" property="free(ptr)"];
  "68719476738" -> "30064771077" [label="REACHING_DEF" property="ptr"];
}
"""
        dot_path = tmp_path / "real.dot"
        dot_path.write_text(dot_text)

        nodes, edges = load_cpg(dot_path)
        assert len(nodes) == 3
        assert len(edges) == 3
        assert nodes[0].label == "free(ptr)"
        assert nodes[2].label == "*ptr = 1"


class TestRunJoern:
    """Tests for run_joern subprocess wrapper."""

    def test_raises_on_missing_binary(self, tmp_path: Path) -> None:
        """Test that missing joern-parse raises JoernError."""
        with patch("magma.ingest.subprocess.run") as mock_run:
            from subprocess import CalledProcessError
            mock_run.side_effect = CalledProcessError(1, ["which", "joern-parse"])
            with pytest.raises(JoernError, match="not found"):
                run_joern(tmp_path / "test.c", tmp_path / "out")
