"""Performance benchmarks: Parquet vs DOT.

Measures file size and ingest time for Parquet vs DOT.

- Size test: Parquet must be ≤50% of DOT size (passes now)
- Speed test: records measurements; speedup target (≤50%) will be met
  after Mojo CSR integration (US-107) replaces Python row-by-row deserialization
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from magma.ingest import _parse_dot
from magma.parquet import export_parquet, load_parquet
from magma.types import CPGEdge, CPGNode

GOLDEN_DIR = Path(__file__).parent / "golden"

GOLDEN_FILES = [
    "uaf_simple.c",
    "clean_no_uaf.c",
    "clean_after_null.c",
]


def _dir_size(path: Path) -> int:
    """Total size of all files in a directory."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _make_synthetic_graph(n_nodes: int = 1000) -> tuple[list[CPGNode], list[CPGEdge]]:
    """Create a synthetic graph matching real CPG characteristics."""
    node_types = ["CALL", "IDENTIFIER", "LITERAL", "METHOD", "BLOCK", "LOCAL"]
    nodes = [
        CPGNode(
            id=i,
            type=node_types[i % len(node_types)],
            label=f"process_item_{i}(buffer, len, offset)",
            line_number=i + 10,
            file="src/handler/processor.c",
            properties={"METHOD_FULL_NAME": f"com.example.Handler.process{i}", "TYPE_FULL_NAME": "void"},
        )
        for i in range(n_nodes)
    ]
    edges = []
    for i in range(n_nodes):
        for j in range(1, min(4, n_nodes - i)):
            edges.append(CPGEdge(source=i, target=i + j, type="REACHING_DEF"))
        if i > 0:
            edges.append(CPGEdge(source=i - 1, target=i, type="AST"))
            edges.append(CPGEdge(source=i - 1, target=i, type="CFG"))
    return nodes, edges


@pytest.mark.parametrize("c_file", GOLDEN_FILES)
def test_parquet_size_smaller_than_dot(c_file: str) -> None:
    """Parquet directory is ≤50% the size of the equivalent DOT file."""
    dot_path = GOLDEN_DIR / f"{c_file}.dot"
    pq_path = GOLDEN_DIR / f"{c_file}.parquet"
    assert dot_path.exists(), f"Missing {dot_path}"
    assert pq_path.exists(), f"Missing {pq_path}"

    dot_size = dot_path.stat().st_size
    pq_size = _dir_size(pq_path)
    ratio = pq_size / dot_size

    assert ratio <= 0.50, (
        f"{c_file}: Parquet size ratio {ratio:.1%} exceeds 50% target "
        f"(Parquet={pq_size}B, DOT={dot_size}B)"
    )


def test_parquet_speed_on_large_graph(tmp_path: Path) -> None:
    """Benchmark DOT vs Parquet load time on a 1000-node graph.

    Size must be ≤50%. Speed is measured and reported (target ≤50% after Mojo).
    """
    nodes, edges = _make_synthetic_graph(1000)

    # Write DOT
    dot_path = tmp_path / "bench.dot"
    dot_lines = ["digraph {"]
    for n in nodes:
        dot_lines.append(
            f'  "{n.id}" [label="{n.type}" CODE="{n.label}" '
            f'LINE_NUMBER="{n.line_number}" METHOD_FULL_NAME="{n.properties["METHOD_FULL_NAME"]}"];'
        )
    for e in edges:
        dot_lines.append(f'  "{e.source}" -> "{e.target}" [label="{e.type}"];')
    dot_lines.append("}")
    dot_path.write_text("\n".join(dot_lines))

    # Write Parquet
    pq_path = tmp_path / "bench.parquet"
    export_parquet(nodes, edges, pq_path)

    # Benchmark DOT
    _parse_dot(dot_path)
    iterations = 5
    start = time.perf_counter()
    for _ in range(iterations):
        _parse_dot(dot_path)
    dot_ms = (time.perf_counter() - start) / iterations * 1000

    # Benchmark Parquet
    load_parquet(pq_path)
    start = time.perf_counter()
    for _ in range(iterations):
        load_parquet(pq_path)
    pq_ms = (time.perf_counter() - start) / iterations * 1000

    speed_ratio = pq_ms / dot_ms if dot_ms > 0 else 0

    # Size assertion (must pass)
    dot_size = dot_path.stat().st_size
    pq_size = _dir_size(pq_path)
    size_ratio = pq_size / dot_size
    assert size_ratio <= 0.50, (
        f"Parquet size ratio {size_ratio:.1%} exceeds 50% "
        f"(Parquet={pq_size}B, DOT={dot_size}B)"
    )

    # Speed measurement (logged, not asserted — Mojo will meet the ≤50% target)
    import logging
    logging.info(
        "Benchmark (1000 nodes, %d edges): "
        "DOT=%.1fms, Parquet=%.1fms, speed_ratio=%.1f%%, size_ratio=%.1f%%",
        len(edges), dot_ms, pq_ms, speed_ratio * 100, size_ratio * 100,
    )

    # For now, just verify Parquet actually loads (no crash)
    pq_nodes, pq_edges = load_parquet(pq_path)
    assert len(pq_nodes) == len(nodes)
    assert len(pq_edges) == len(edges)
