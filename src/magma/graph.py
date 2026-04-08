"""CPG graph representation using scipy sparse matrices."""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from magma.types import CPGEdge, CPGNode


class CPGGraph:
    """Code Property Graph backed by per-edge-type sparse adjacency matrices."""

    def __init__(self, nodes: list[CPGNode], edges: list[CPGEdge]) -> None:
        """Build the graph from node and edge lists.

        Args:
            nodes: List of CPG nodes.
            edges: List of CPG edges.
        """
        self._nodes = nodes
        self._node_id_to_idx: dict[int, int] = {}
        self._idx_to_node: dict[int, CPGNode] = {}

        for idx, node in enumerate(nodes):
            self._node_id_to_idx[node.id] = idx
            self._idx_to_node[idx] = node

        # Build per-edge-type adjacency matrices
        self._adjacency: dict[str, sp.csr_matrix] = {}
        self._edge_types_set: set[str] = set()

        # Group edges by type
        edges_by_type: dict[str, list[tuple[int, int]]] = {}
        for edge in edges:
            self._edge_types_set.add(edge.type)
            if edge.type not in edges_by_type:
                edges_by_type[edge.type] = []
            src_idx = self._node_id_to_idx.get(edge.source)
            tgt_idx = self._node_id_to_idx.get(edge.target)
            if src_idx is not None and tgt_idx is not None:
                edges_by_type[edge.type].append((src_idx, tgt_idx))

        n = len(nodes)
        for edge_type, pairs in edges_by_type.items():
            if not pairs:
                self._adjacency[edge_type] = sp.csr_matrix((n, n), dtype=np.int8)
                continue
            rows, cols = zip(*pairs, strict=False)
            data = np.ones(len(rows), dtype=np.int8)
            self._adjacency[edge_type] = sp.csr_matrix(
                (data, (rows, cols)), shape=(n, n)
            )

    def adjacency(self, edge_type: str) -> sp.csr_matrix:
        """Return the sparse adjacency matrix for a given edge type.

        Args:
            edge_type: The edge type (e.g., "AST", "CFG", "REACHING_DEF").

        Returns:
            CSR sparse matrix of shape (N, N) where entry (i,j) = 1 if an edge
            of the given type exists from node i to node j.
        """
        n = len(self._nodes)
        return self._adjacency.get(edge_type, sp.csr_matrix((n, n), dtype=np.int8))

    def combined_adjacency(self, edge_types: list[str]) -> sp.csr_matrix:
        """Return a combined adjacency matrix for multiple edge types.

        Args:
            edge_types: List of edge types to combine.

        Returns:
            CSR sparse matrix where entry (i,j) = 1 if any of the specified
            edge types has an edge from node i to node j.
        """
        n = len(self._nodes)
        result = sp.csr_matrix((n, n), dtype=np.int8)
        for et in edge_types:
            result = result + self.adjacency(et)
        # Clamp to binary
        result.data = np.clip(result.data, 0, 1)
        return result

    def node_at(self, idx: int) -> CPGNode:
        """Return the node at a given matrix index.

        Args:
            idx: Matrix row/column index.

        Returns:
            The CPGNode at that index.
        """
        return self._idx_to_node[idx]

    def nodes_of_type(self, node_type: str) -> list[int]:
        """Return matrix indices for all nodes of a given type.

        Args:
            node_type: The node type string to filter by.

        Returns:
            List of matrix indices where the node type matches.
        """
        return [
            idx for idx, node in self._idx_to_node.items()
            if node.type == node_type
        ]

    def nodes_with_label(self, label_substring: str) -> list[int]:
        """Return matrix indices for nodes whose label contains the given substring.

        Args:
            label_substring: Substring to match against node labels.

        Returns:
            List of matching matrix indices.
        """
        return [
            idx for idx, node in self._idx_to_node.items()
            if label_substring in node.label
        ]

    def edge_types(self) -> set[str]:
        """Return all edge types present in the graph."""
        return self._edge_types_set.copy()

    @property
    def node_count(self) -> int:
        """Number of nodes in the graph."""
        return len(self._nodes)
