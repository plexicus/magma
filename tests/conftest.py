"""Shared test fixtures for Magma tests."""

from __future__ import annotations

import shutil
import warnings
from pathlib import Path

import pytest

from magma.graph import CPGGraph
from magma.types import CPGEdge, CPGNode

# Suppress deprecation warnings from load_cpg() in tests — we still test the
# deprecated path works.  Tests for convert_to_parquet verify the new path.
warnings.filterwarnings("ignore", message="load_cpg.*deprecated", category=DeprecationWarning)
warnings.simplefilter("ignore", DeprecationWarning)


@pytest.fixture
def corpus_path() -> Path:
    """Return the path to the test corpus directory."""
    return Path(__file__).parent / "corpus"


@pytest.fixture
def joern_available() -> bool:
    """Check if Joern is installed and available."""
    return shutil.which("joern-parse") is not None


@pytest.fixture
def skip_if_no_joern(joern_available: bool) -> None:
    """Skip test if Joern is not available."""
    if not joern_available:
        pytest.skip("Joern not installed")


@pytest.fixture
def sample_cpg_graph() -> CPGGraph:
    """Hand-crafted CPG graph for unit tests (not dependent on Joern).

    Graph structure:
        Node 0: CALL "free(ptr)"     line 3
        Node 1: IDENTIFIER "ptr"     line 3
        Node 2: CALL "*ptr = 1"      line 4  (dereference)
        Node 3: IDENTIFIER "ptr"     line 4
        Node 4: LITERAL "NULL"       line 5
        Node 5: CALL "ptr = NULL"    line 5  (null assignment)
        Node 6: CALL "free(ptr)"     line 6  (second free)

    Edges:
        0 -> 1: AST          (free call has ptr as argument)
        2 -> 3: AST          (assign has ptr as target)
        0 -> 2: REACHING_DEF (ptr from free reaches assign)
        2 -> 6: REACHING_DEF (ptr from assign reaches second free)
        0 -> 5: REACHING_DEF (ptr from free reaches null)
        5 -> 6: REACHING_DEF (ptr from null reaches second free)
    """
    nodes = [
        CPGNode(id=0, type="CALL", label="free(ptr)", line_number=3, file="test.c"),
        CPGNode(id=1, type="IDENTIFIER", label="ptr", line_number=3, file="test.c"),
        CPGNode(id=2, type="CALL", label="*ptr = 1", line_number=4, file="test.c"),
        CPGNode(id=3, type="IDENTIFIER", label="ptr", line_number=4, file="test.c"),
        CPGNode(id=4, type="LITERAL", label="NULL", line_number=5, file="test.c"),
        CPGNode(id=5, type="CALL", label="ptr = NULL", line_number=5, file="test.c"),
        CPGNode(id=6, type="CALL", label="free(ptr)", line_number=6, file="test.c"),
    ]
    edges = [
        CPGEdge(source=0, target=1, type="AST"),
        CPGEdge(source=2, target=3, type="AST"),
        CPGEdge(source=0, target=2, type="REACHING_DEF"),
        CPGEdge(source=2, target=6, type="REACHING_DEF"),
        CPGEdge(source=0, target=5, type="REACHING_DEF"),
        CPGEdge(source=5, target=6, type="REACHING_DEF"),
    ]
    return CPGGraph(nodes, edges)


@pytest.fixture
def sample_cpg_with_uaf() -> CPGGraph:
    """Hand-crafted CPG with a clear free→deref UAF.

    Graph:
        Node 0: CALL "free(ptr)"    line 3  (free)
        Node 1: IDENTIFIER "ptr"    line 4  (deref - use after free)
        Edges:
        0 -> 1: REACHING_DEF
    """
    nodes = [
        CPGNode(id=0, type="CALL", label="free(ptr)", line_number=3, file="test.c"),
        CPGNode(id=1, type="IDENTIFIER", label="ptr", line_number=4, file="test.c"),
    ]
    edges = [
        CPGEdge(source=0, target=1, type="REACHING_DEF"),
    ]
    return CPGGraph(nodes, edges)


@pytest.fixture
def sample_cpg_clean() -> CPGGraph:
    """Hand-crafted CPG with no UAF (free but no deref after).

    Graph:
        Node 0: IDENTIFIER "ptr"    line 3  (use before free)
        Node 1: CALL "free(ptr)"    line 4  (free - last use)
        Edges:
        0 -> 1: REACHING_DEF
    """
    nodes = [
        CPGNode(id=0, type="IDENTIFIER", label="ptr", line_number=3, file="test.c"),
        CPGNode(id=1, type="CALL", label="free(ptr)", line_number=4, file="test.c"),
    ]
    edges = [
        CPGEdge(source=0, target=1, type="REACHING_DEF"),
    ]
    return CPGGraph(nodes, edges)
