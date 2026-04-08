"""Tests for the UAF query engine."""

from __future__ import annotations

from magma.graph import CPGGraph
from magma.query import detect_uaf, format_findings
from magma.types import CPGEdge, CPGNode, Finding


class TestDetectUaf:
    """Tests for detect_uaf using synthetic CPGs."""

    def test_uaf_reachability(self, sample_cpg_with_uaf: CPGGraph) -> None:
        """Test that free→deref UAF is detected via data dependency."""
        findings = detect_uaf(sample_cpg_with_uaf)
        assert len(findings) == 1
        assert findings[0].vuln_type == "Use-After-Free"
        assert findings[0].line == 4

    def test_no_false_positive(self, sample_cpg_clean: CPGGraph) -> None:
        """Test that clean code (use before free) produces no findings."""
        findings = detect_uaf(sample_cpg_clean)
        assert len(findings) == 0

    def test_multiple_free_deref_pairs(self) -> None:
        """Test detection of multiple UAF pairs in the same graph."""
        nodes = [
            CPGNode(id=0, type="CALL", label="free(p)", line_number=3, file="test.c"),
            CPGNode(id=1, type="IDENTIFIER", label="p", line_number=4, file="test.c"),
            CPGNode(id=2, type="CALL", label="free(q)", line_number=5, file="test.c"),
            CPGNode(id=3, type="IDENTIFIER", label="q", line_number=6, file="test.c"),
        ]
        edges = [
            CPGEdge(source=0, target=1, type="REACHING_DEF"),
            CPGEdge(source=2, target=3, type="REACHING_DEF"),
        ]
        graph = CPGGraph(nodes, edges)

        findings = detect_uaf(graph)
        assert len(findings) == 2

    def test_null_assignment_exclusion(self) -> None:
        """Test that null assignment anti-pattern excludes UAF."""
        nodes = [
            CPGNode(id=0, type="CALL", label="free(ptr)", line_number=3, file="test.c"),
            CPGNode(id=1, type="LITERAL", label="NULL", line_number=4, file="test.c"),
            CPGNode(id=2, type="CALL", label="ptr = NULL", line_number=4, file="test.c"),
            CPGNode(id=3, type="IDENTIFIER", label="ptr", line_number=5, file="test.c"),
        ]
        edges = [
            CPGEdge(source=0, target=2, type="REACHING_DEF"),
            CPGEdge(source=2, target=3, type="REACHING_DEF"),
        ]
        graph = CPGGraph(nodes, edges)

        findings = detect_uaf(graph)
        # The null assignment should cause this to be excluded
        # (ptr = NULL between free and deref)
        assert len(findings) == 0

    def test_max_hops_parameter(self) -> None:
        """Test that max_hops limits reachability depth."""
        # Create a chain: free(0) -> 1 -> 2 -> 3 -> 4 -> 5 (deref)
        # Hop distances from node 0: node1=1, node2=2, node3=3, node4=4, node5=5
        nodes = [
            CPGNode(id=0, type="CALL", label="free(ptr)", line_number=1, file="test.c"),
            CPGNode(id=1, type="LITERAL", label="x", line_number=2, file="test.c"),
            CPGNode(id=2, type="LITERAL", label="x", line_number=3, file="test.c"),
            CPGNode(id=3, type="LITERAL", label="x", line_number=4, file="test.c"),
            CPGNode(id=4, type="LITERAL", label="x", line_number=5, file="test.c"),
            CPGNode(id=5, type="IDENTIFIER", label="ptr", line_number=6, file="test.c"),
        ]
        edges = [
            CPGEdge(source=i, target=i + 1, type="REACHING_DEF") for i in range(5)
        ]
        graph = CPGGraph(nodes, edges)

        # With max_hops=3, node 5 (at hop 5) should NOT be reachable
        findings_short = detect_uaf(graph, max_hops=3)
        assert len(findings_short) == 0

        # With max_hops=5, node 5 should be reachable
        findings_long = detect_uaf(graph, max_hops=5)
        assert len(findings_long) == 1

    def test_no_free_nodes(self) -> None:
        """Test that graph with no free calls returns no findings."""
        nodes = [
            CPGNode(id=0, type="IDENTIFIER", label="ptr", line_number=1, file="test.c"),
            CPGNode(id=1, type="IDENTIFIER", label="ptr", line_number=2, file="test.c"),
        ]
        edges = [CPGEdge(source=0, target=1, type="REACHING_DEF")]
        graph = CPGGraph(nodes, edges)

        findings = detect_uaf(graph)
        assert len(findings) == 0

    def test_no_deref_nodes(self) -> None:
        """Test that graph with free but no derefs returns no findings."""
        nodes = [
            CPGNode(id=0, type="CALL", label="free(ptr)", line_number=1, file="test.c"),
            CPGNode(id=1, type="LITERAL", label="42", line_number=2, file="test.c"),
        ]
        edges = [CPGEdge(source=0, target=1, type="REACHING_DEF")]
        graph = CPGGraph(nodes, edges)

        findings = detect_uaf(graph)
        assert len(findings) == 0

    def test_empty_graph(self) -> None:
        """Test that empty graph returns no findings."""
        graph = CPGGraph([], [])
        findings = detect_uaf(graph)
        assert len(findings) == 0


class TestFormatFindings:
    """Tests for format_findings output formatter."""

    def test_no_findings(self) -> None:
        """Test formatting when no vulnerabilities found."""
        result = format_findings([])
        assert "No vulnerabilities found" in result

    def test_single_finding(self) -> None:
        """Test formatting a single finding."""
        findings = [
            Finding(vuln_type="Use-After-Free", file="test.c", line=5,
                    description="ptr freed at 3, dereferenced at 5"),
        ]
        result = format_findings(findings)
        assert "Use-After-Free" in result
        assert "test.c" in result
        assert "line: 5" in result.lower() or "Line: 5" in result
        assert "1 vulnerabilit" in result

    def test_multiple_findings(self) -> None:
        """Test formatting multiple findings."""
        findings = [
            Finding(vuln_type="Use-After-Free", file="a.c", line=5, description="desc1"),
            Finding(vuln_type="Use-After-Free", file="b.c", line=10, description="desc2"),
        ]
        result = format_findings(findings)
        assert "[1]" in result
        assert "[2]" in result
        assert "2 vulnerabilit" in result


class TestFindingToDict:
    """Tests for Finding.to_dict() serialization."""

    def test_basic_dict(self) -> None:
        """Test basic to_dict output."""
        f = Finding(vuln_type="UAF", file="test.c", line=5, description="test")
        d = f.to_dict()
        assert d["vuln_type"] == "UAF"
        assert d["file"] == "test.c"
        assert d["line"] == 5
        assert d["description"] == "test"
        assert "path" not in d

    def test_dict_with_path(self) -> None:
        """Test to_dict with path included."""
        f = Finding(vuln_type="UAF", file="test.c", line=5, description="test",
                    path=[0, 1, 2])
        d = f.to_dict()
        assert d["path"] == [0, 1, 2]
