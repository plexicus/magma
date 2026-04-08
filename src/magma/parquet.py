"""Parquet-based CPG serialization for fast binary ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from magma.types import CPGEdge, CPGNode


def export_parquet(
    nodes: list[CPGNode],
    edges: list[CPGEdge],
    path: str | Path,
) -> None:
    """Export CPG nodes and edges to a Parquet directory.

    Writes three Parquet files into a directory:
    - nodes.parquet: id, type, label, line_number, file, properties (JSON string)
    - edges.parquet: source, target, type
    - csr.parquet: edge_type, row_ptr (JSON string), col_idx (JSON string)

    Args:
        nodes: List of CPG nodes.
        edges: List of CPG edges.
        path: Output path. If it ends with .parquet, a directory is created
              at that path (e.g., "out.cpg.parquet/"). Otherwise used as-is.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # Nodes table
    nodes_table = pa.table({
        "id": pa.array([n.id for n in nodes], type=pa.int64()),
        "type": pa.array([n.type for n in nodes], type=pa.string()),
        "label": pa.array([n.label for n in nodes], type=pa.string()),
        "line_number": pa.array(
            [n.line_number for n in nodes], type=pa.int64()
        ),
        "file": pa.array([n.file for n in nodes], type=pa.string()),
        "properties": pa.array(
            [json.dumps(n.properties) for n in nodes], type=pa.string()
        ),
    })

    # Edges table
    edges_table = pa.table({
        "source": pa.array([e.source for e in edges], type=pa.int64()),
        "target": pa.array([e.target for e in edges], type=pa.int64()),
        "type": pa.array([e.type for e in edges], type=pa.string()),
    })

    # CSR index table (Mojo-ready precomputed CSR per edge type)
    csr_table = _build_csr_index(nodes, edges)

    # Write each table as a separate Parquet file
    pq.write_table(nodes_table, str(path / "nodes.parquet"))
    pq.write_table(edges_table, str(path / "edges.parquet"))
    pq.write_table(csr_table, str(path / "csr.parquet"))


def load_parquet(
    path: str | Path,
) -> tuple[list[CPGNode], list[CPGEdge]]:
    """Load CPG nodes and edges from a Parquet directory.

    Args:
        path: Path to the Parquet directory.

    Returns:
        Tuple of (nodes, edges) lists.
    """
    path = Path(path)

    nodes_table = pq.read_table(str(path / "nodes.parquet"))
    edges_table = pq.read_table(str(path / "edges.parquet"))

    nodes = []
    for i in range(nodes_table.num_rows):
        props_str = nodes_table.column("properties")[i].as_py()
        props = json.loads(props_str) if props_str else {}
        nodes.append(CPGNode(
            id=nodes_table.column("id")[i].as_py(),
            type=nodes_table.column("type")[i].as_py(),
            label=nodes_table.column("label")[i].as_py(),
            line_number=nodes_table.column("line_number")[i].as_py(),
            file=nodes_table.column("file")[i].as_py(),
            properties=props,
        ))

    edges = []
    for i in range(edges_table.num_rows):
        edges.append(CPGEdge(
            source=edges_table.column("source")[i].as_py(),
            target=edges_table.column("target")[i].as_py(),
            type=edges_table.column("type")[i].as_py(),
        ))

    return nodes, edges


def _build_csr_index(
    nodes: list[CPGNode],
    edges: list[CPGEdge],
) -> pa.Table:
    """Build per-edge-type CSR index for Mojo-ready access.

    Returns:
        PyArrow table with columns: edge_type, row_ptr (JSON), col_idx (JSON).
    """
    node_id_to_idx = {n.id: i for i, n in enumerate(nodes)}
    n = len(nodes)

    # Group edges by type
    edges_by_type: dict[str, list[tuple[int, int]]] = {}
    for edge in edges:
        src_idx = node_id_to_idx.get(edge.source)
        tgt_idx = node_id_to_idx.get(edge.target)
        if src_idx is not None and tgt_idx is not None:
            edges_by_type.setdefault(edge.type, []).append((src_idx, tgt_idx))

    edge_types = []
    row_ptrs = []
    col_idxs = []

    for edge_type, pairs in sorted(edges_by_type.items()):
        # Sort by (row, col)
        sorted_pairs = sorted(pairs)
        sorted_rows = [p[0] for p in sorted_pairs]
        sorted_cols = [p[1] for p in sorted_pairs]

        # Build row_ptr
        row_ptr = [0] * (n + 1)
        for r in sorted_rows:
            row_ptr[r + 1] += 1
        for i in range(1, n + 1):
            row_ptr[i] += row_ptr[i - 1]

        edge_types.append(edge_type)
        row_ptrs.append(json.dumps(row_ptr))
        col_idxs.append(json.dumps(sorted_cols))

    return pa.table({
        "edge_type": pa.array(edge_types, type=pa.string()),
        "row_ptr": pa.array(row_ptrs, type=pa.string()),
        "col_idx": pa.array(col_idxs, type=pa.string()),
    })
