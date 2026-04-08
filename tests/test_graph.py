"""Tests for the CPG graph layer."""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from magma.graph import CPGGraph
from magma.types import CPGEdge, CPGNode


def _make_node(id: int, type: str = "CALL", label: str = "") -> CPGNode:
    return CPGNode(id=id, type=type, label=label, line_number=id, file="test.c")


class TestCPGGraph:
    """Tests for CPGGraph sparse matrix construction."""

    def test_adjacency_matrix_construction(self) -> None:
        """Test that adjacency matrices have correct sparsity pattern."""
        nodes = [_make_node(0), _make_node(1), _make_node(2)]
        edges = [
            CPGEdge(source=0, target=1, type="AST"),
            CPGEdge(source=1, target=2, type="AST"),
            CPGEdge(source=0, target=2, type="CFG"),
        ]
        graph = CPGGraph(nodes, edges)

        ast = graph.adjacency("AST")
        assert ast.shape == (3, 3)
        assert ast[0, 1] == 1
        assert ast[1, 2] == 1
        assert ast[0, 2] == 0  # No AST edge from 0 to 2

        cfg = graph.adjacency("CFG")
        assert cfg[0, 2] == 1
        assert cfg[0, 1] == 0  # No CFG edge from 0 to 1

    def test_adjacency_unknown_type(self) -> None:
        """Test that unknown edge type returns empty matrix."""
        nodes = [_make_node(0), _make_node(1)]
        graph = CPGGraph(nodes, [])

        result = graph.adjacency("NONEXISTENT")
        assert result.shape == (2, 2)
        assert result.nnz == 0

    def test_nodes_of_type(self) -> None:
        """Test filtering nodes by type."""
        nodes = [
            _make_node(0, "CALL", "free"),
            _make_node(1, "IDENTIFIER", "ptr"),
            _make_node(2, "CALL", "malloc"),
        ]
        graph = CPGGraph(nodes, [])

        calls = graph.nodes_of_type("CALL")
        assert len(calls) == 2
        assert 0 in calls
        assert 2 in calls

        idents = graph.nodes_of_type("IDENTIFIER")
        assert len(idents) == 1
        assert 1 in idents

    def test_node_at(self) -> None:
        """Test reverse lookup from index to node."""
        nodes = [
            _make_node(42, "CALL", "test"),
        ]
        graph = CPGGraph(nodes, [])

        node = graph.node_at(0)
        assert node.id == 42
        assert node.label == "test"

    def test_edge_types(self) -> None:
        """Test that edge_types returns all types present."""
        nodes = [_make_node(0), _make_node(1)]
        edges = [
            CPGEdge(source=0, target=1, type="AST"),
            CPGEdge(source=0, target=1, type="CFG"),
        ]
        graph = CPGGraph(nodes, edges)

        types = graph.edge_types()
        assert types == {"AST", "CFG"}

    def test_empty_graph(self) -> None:
        """Test edge case: empty graph."""
        graph = CPGGraph([], [])
        assert graph.node_count == 0
        assert graph.edge_types() == set()
        assert graph.adjacency("AST").shape == (0, 0)

    def test_single_node_graph(self) -> None:
        """Test edge case: single node, no edges."""
        nodes = [_make_node(0)]
        graph = CPGGraph(nodes, [])
        assert graph.node_count == 1
        assert graph.adjacency("AST").shape == (1, 1)
        assert graph.adjacency("AST").nnz == 0

    def test_combined_adjacency(self) -> None:
        """Test combining multiple edge types."""
        nodes = [_make_node(0), _make_node(1)]
        edges = [
            CPGEdge(source=0, target=1, type="AST"),
            CPGEdge(source=0, target=1, type="CFG"),
        ]
        graph = CPGGraph(nodes, edges)

        combined = graph.combined_adjacency(["AST", "CFG"])
        assert combined[0, 1] == 1

        # Even though both types have the same edge, result should be binary
        assert combined.data.max() == 1

    def test_nodes_with_label(self) -> None:
        """Test finding nodes by label substring."""
        nodes = [
            _make_node(0, "CALL", "free(ptr)"),
            _make_node(1, "CALL", "malloc(size)"),
        ]
        graph = CPGGraph(nodes, [])

        free_nodes = graph.nodes_with_label("free")
        assert len(free_nodes) == 1
        assert free_nodes[0] == 0
