"""End-to-end tests against the C test corpus.

These tests require Joern to be installed. They are skipped automatically
when joern-parse is not available on PATH.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from magma.graph import CPGGraph
from magma.ingest import JoernError, load_cpg, run_joern
from magma.query import detect_uaf

# Corpus files that SHOULD produce UAF findings
VULNERABLE_FILES = [
    ("uaf_simple.c", True),
    ("uaf_branch.c", True),
    ("uaf_loop.c", True),
    ("uaf_function_call.c", True),
    ("uaf_struct_member.c", True),
    ("uaf_double_free.c", True),
]

# Corpus files that should NOT produce UAF findings
CLEAN_FILES = [
    ("clean_no_uaf.c", False),
    ("clean_after_null.c", False),
    ("clean_realloc.c", False),
]

ALL_CORPUS_FILES = VULNERABLE_FILES + CLEAN_FILES

joern_missing = shutil.which("joern-parse") is None


@pytest.mark.skipif(joern_missing, reason="Joern not installed")
@pytest.mark.parametrize("filename,should_find", ALL_CORPUS_FILES)
def test_corpus_detection(
    filename: str,
    should_find: bool,
    corpus_path: Path,
    tmp_path: Path,
) -> None:
    """Test that vulnerable files produce findings and clean files don't."""
    file_path = corpus_path / filename
    assert file_path.exists(), f"Corpus file missing: {file_path}"

    try:
        dot_path = run_joern(file_path, tmp_path)
        nodes, edges = load_cpg(dot_path)
        graph = CPGGraph(nodes, edges)
        findings = detect_uaf(graph)

        if should_find:
            assert len(findings) >= 1, (
                f"{filename}: expected UAF findings but got none. "
                f"Nodes: {len(nodes)}, Edges: {len(edges)}, "
                f"Edge types: {graph.edge_types()}"
            )
        else:
            assert len(findings) == 0, (
                f"{filename}: expected no UAF findings but got {len(findings)}: "
                f"{[f.description for f in findings]}"
            )
    except JoernError as e:
        pytest.fail(f"Joern error processing {filename}: {e}")
