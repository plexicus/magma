#!/usr/bin/env python3
"""Regenerate golden test fixtures from real Joern exports.

Usage:
    python tests/generate_goldens.py

Requires Joern to be installed (joern-parse + joern-export on PATH).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

CORPUS_DIR = Path(__file__).parent / "corpus"
GOLDEN_DIR = Path(__file__).parent / "golden"

FILES = [
    "uaf_simple.c",
    "clean_no_uaf.c",
    "clean_after_null.c",
]


def main() -> None:
    if shutil.which("joern-parse") is None:
        print("ERROR: joern-parse not found. Install Joern: https://joern.io/")
        sys.exit(1)

    # Add project to path
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from magma.graph import CPGGraph
    from magma.ingest import load_cpg, run_joern
    from magma.query import detect_uaf

    GOLDEN_DIR.mkdir(exist_ok=True)

    for c_file in FILES:
        corpus_file = CORPUS_DIR / c_file
        if not corpus_file.exists():
            print(f"SKIP: {corpus_file} not found")
            continue

        print(f"Generating golden fixtures for {c_file}...")

        with tempfile.TemporaryDirectory() as tmpdir:
            dot_path = run_joern(corpus_file, Path(tmpdir))
            dot_content = dot_path.read_text()

            # Save raw DOT
            (GOLDEN_DIR / f"{c_file}.dot").write_text(dot_content)

            # Save node/edge snapshot
            nodes, edges = load_cpg(dot_path)
            snapshot = {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "edge_types": sorted(set(e.type for e in edges)),
                "node_types": sorted(set(n.type for n in nodes)),
                "nodes": [
                    {
                        "id": n.id,
                        "type": n.type,
                        "label": n.label,
                        "line": n.line_number,
                        "file": n.file,
                        "props": n.properties,
                    }
                    for n in nodes
                ],
                "edges": [
                    {"src": e.source, "tgt": e.target, "type": e.type}
                    for e in edges
                ],
            }
            (GOLDEN_DIR / f"{c_file}.snapshot.json").write_text(
                json.dumps(snapshot, indent=2)
            )

            # Save query output
            graph = CPGGraph(nodes, edges)
            findings = detect_uaf(graph)
            result = {
                "file": c_file,
                "finding_count": len(findings),
                "findings": [f.to_dict() for f in findings],
            }
            (GOLDEN_DIR / f"{c_file}.findings.json").write_text(
                json.dumps(result, indent=2)
            )

            print(
                f"  {len(nodes)} nodes, {len(edges)} edges, "
                f"{len(findings)} findings"
            )

    print(f"\nGolden fixtures written to {GOLDEN_DIR}/")


if __name__ == "__main__":
    main()
