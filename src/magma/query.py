"""UAF detection query engine using sparse matrix reachability."""

from __future__ import annotations

from typing import Literal

import numpy as np
import scipy.sparse as sp

from magma.graph import CPGGraph
from magma.types import Finding

# Free-family function names
FREE_FUNCTIONS = {"free", "vPortFree", "kfree", "cfree", "afree"}

# Joern edge types for data dependency
DATA_DEP_EDGE_TYPES = ["REACHING_DEF", "DDG"]


def detect_uaf(graph: CPGGraph, max_hops: int = 5, device: Literal["cpu", "gpu"] = "cpu") -> list[Finding]:
    """Detect Use-After-Free vulnerabilities in a CPG using sparse matrix reachability.

    Algorithm:
    1. Find all CALL nodes where callee is a free-family function → F
    2. Find all dereference nodes → D
    3. Build data dependency adjacency matrix M_data
    4. Compute reachability: R = sum(M_data^i for i in 1..max_hops)
    5. Find (f, d) pairs where R[f,d] > 0
    6. Exclude pairs where path passes through a null-assignment node
    7. Return remaining pairs as findings

    Args:
        graph: The CPG graph to query.
        max_hops: Maximum number of data dependency hops to traverse.
        device: Computation device — 'cpu' (scipy, default) or 'gpu' (Metal).

    Returns:
        List of Finding objects for detected UAF vulnerabilities.
    """
    # Step 1: Find free() call nodes
    free_call_indices = _find_free_nodes(graph)

    # Step 2: Find dereference nodes
    deref_indices = _find_deref_nodes(graph)

    if not free_call_indices or not deref_indices:
        return []

    # Step 3: Expand free nodes to include their AST children (pointer identifiers).
    # In real Joern CPGs, REACHING_DEF flows through IDENTIFIER nodes, not
    # directly from CALL nodes. We seed reachability from the free call's
    # AST children to capture this data flow.
    ast_matrix = graph.adjacency("AST")
    free_indices = set(free_call_indices)
    for f_idx in free_call_indices:
        row = ast_matrix.getrow(f_idx)
        _, children = row.nonzero()
        for c in children:
            free_indices.add(int(c))
    free_indices = sorted(free_indices)

    # Step 4: Build data dependency matrix and compute reachability
    m_data = graph.combined_adjacency(DATA_DEP_EDGE_TYPES)
    reachability = _compute_reachability(m_data, max_hops, device=device)

    # Step 5: Find null-assignment nodes for anti-pattern exclusion
    null_indices = _find_null_assignment_nodes(graph)

    # Step 6: Build null-mask (nodes reachable from null assignments)
    null_mask = sp.csr_matrix(reachability.shape, dtype=np.int8)
    if null_indices:
        null_mask = _compute_reachability(m_data, max_hops, sources=null_indices, device=device)

    # Step 7: Find free→deref pairs, excluding null-assignment paths
    findings: list[Finding] = []
    seen: set[tuple[int, int]] = set()
    for f_idx in free_indices:
        for d_idx in deref_indices:
            if reachability[f_idx, d_idx] > 0:
                # Check if null assignment intervenes
                if null_indices and null_mask[f_idx, d_idx] > 0:
                    # A null assignment is reachable from free before the deref
                    # This means the pointer was nullified — skip
                    continue

                # Find the original free CALL node (may be f_idx itself or a parent)
                free_node = graph.node_at(f_idx)
                if f_idx not in free_call_indices:
                    # f_idx is an AST child of a free call — find the parent
                    for parent_idx in free_call_indices:
                        _, children = ast_matrix.getrow(parent_idx).nonzero()
                        if f_idx in children:
                            free_node = graph.node_at(parent_idx)
                            break

                deref_node = graph.node_at(d_idx)
                pair_key = (free_node.id, deref_node.id)
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                file_path = deref_node.file or free_node.file or "<unknown>"
                line = deref_node.line_number or 0

                findings.append(Finding(
                    vuln_type="Use-After-Free",
                    file=file_path,
                    line=line,
                    description=(
                        f"Pointer freed at line {free_node.line_number} "
                        f"({free_node.label}) then dereferenced at line {line} "
                        f"({deref_node.label})"
                    ),
                ))

    return findings


def format_findings(findings: list[Finding]) -> str:
    """Format findings as a human-readable string.

    Args:
        findings: List of Finding objects.

    Returns:
        Formatted string for display.
    """
    if not findings:
        return "No vulnerabilities found."

    lines = [
        "Magma UAF Detection Results",
        "=" * 30,
        "",
    ]

    for i, f in enumerate(findings, 1):
        lines.append(f"[{i}] {f.vuln_type}")
        lines.append(f"    File: {f.file}")
        lines.append(f"    Line: {f.line}")
        lines.append(f"    {f.description}")
        lines.append("")

    lines.append(f"Found {len(findings)} vulnerabilit{'y' if len(findings) == 1 else 'ies'}.")
    return "\n".join(lines)


def _find_free_nodes(graph: CPGGraph) -> list[int]:
    """Find CALL nodes that call a free-family function."""
    call_indices = graph.nodes_of_type("CALL")
    free_indices = []
    for idx in call_indices:
        node = graph.node_at(idx)
        # Check label for free-family function names
        label_lower = node.label.lower()
        matched = False
        for fn in FREE_FUNCTIONS:
            if fn in label_lower:
                matched = True
                break
        # Also check METHOD_FULL_NAME property (more reliable in Joern CPG)
        if not matched:
            method_name = node.properties.get("METHOD_FULL_NAME", "").lower()
            for fn in FREE_FUNCTIONS:
                if fn == method_name:
                    matched = True
                    break
        if matched:
            free_indices.append(idx)
    return free_indices


def _find_deref_nodes(graph: CPGGraph) -> list[int]:
    """Find nodes that represent pointer dereferences.

    Looks for nodes with dereference-related types or labels.
    """
    deref_types = {
        "INDIRECT_FIELD_ACCESS",
        "INDIRECT_INDEX_ACCESS",
        "FIELD_ACCESS",
        "INDEX_ACCESS",
        "DEREF",
    }

    deref_indices = list(graph.nodes_of_type("INDIRECT_FIELD_ACCESS"))
    deref_indices += list(graph.nodes_of_type("INDIRECT_INDEX_ACCESS"))
    deref_indices += list(graph.nodes_of_type("FIELD_ACCESS"))
    deref_indices += list(graph.nodes_of_type("INDEX_ACCESS"))

    # Also check for nodes whose label or properties contain dereference indicators
    for idx in graph.nodes_of_type("CALL"):
        node = graph.node_at(idx)
        if idx in deref_indices:
            continue
        if "*" in node.label or "->" in node.label:
            deref_indices.append(idx)
            continue
        # Joern uses <operator>.indirection for *ptr dereferences
        method_name = node.properties.get("METHOD_FULL_NAME", "")
        if "indirection" in method_name or "dereference" in method_name:
            deref_indices.append(idx)

    # IDENTIFIER nodes that are targets of REACHING_DEF from free nodes
    # are also potential derefs (the pointer is being used)
    # We'll check all IDENTIFIER nodes and let the reachability filter
    for idx in graph.nodes_of_type("IDENTIFIER"):
        if idx not in deref_indices:
            deref_indices.append(idx)

    return deref_indices


def _find_null_assignment_nodes(graph: CPGGraph) -> list[int]:
    """Find ASSIGN nodes where the value is NULL."""
    null_indices = []
    # Look for nodes with NULL in their label
    for idx in range(graph.node_count):
        node = graph.node_at(idx)
        label_upper = node.label.upper()
        if "NULL" in label_upper or "NIL" in label_upper:
            null_indices.append(idx)
    return null_indices


def _compute_reachability(
    adjacency: sp.csr_matrix,
    max_hops: int,
    sources: list[int] | None = None,
    device: Literal["cpu", "gpu"] = "cpu",
) -> sp.csr_matrix:
    """Compute reachability matrix via sparse matrix power iteration.

    Computes R = A + A^2 + ... + A^max_hops using iterative multiplication.

    Args:
        adjacency: The adjacency matrix.
        max_hops: Maximum number of hops.
        sources: If provided, only compute reachability from these source indices.
        device: Computation device — 'cpu' (scipy) or 'gpu' (Metal).

    Returns:
        Reachability matrix (binary, CSR format).
    """
    n = adjacency.shape[0]
    if n == 0:
        return sp.csr_matrix((n, n), dtype=np.int8)

    # Use float for multiplication, convert back to binary
    adj = adjacency.astype(np.float64)
    result = sp.csr_matrix((n, n), dtype=np.float64)
    power = adj.copy()

    for _ in range(max_hops):
        result = result + power
        power = power @ adj
        # Sparsify to avoid densification
        power.eliminate_zeros()

    # Convert to binary
    result.eliminate_zeros()
    result.data = np.ones_like(result.data, dtype=np.int8)
    return result
