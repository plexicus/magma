# UAF Detection Algorithm

## Problem Statement

A Use-After-Free (UAF) occurs when memory is freed (via `free()`) and then accessed (dereferenced) afterward. Detecting this requires tracking data flow from the free call through intervening code to the dereference.

## Approach: Sparse Matrix Reachability

Instead of traversing the graph edge-by-edge, Magma encodes the entire data dependency graph as a sparse adjacency matrix and computes reachability through matrix power iteration.

## Step-by-Step Algorithm

### Step 1: Identify free-family calls

Find all CALL nodes whose callee matches one of: `free`, `vPortFree`, `kfree`, `cfree`, `afree`. Matching uses both label substring and `METHOD_FULL_NAME` property (exact match preferred).

### Step 2: Identify dereference nodes

Find nodes that represent pointer dereferences:
- `INDIRECT_FIELD_ACCESS`, `INDIRECT_INDEX_ACCESS` — `->` and `[]` on pointers
- `FIELD_ACCESS`, `INDEX_ACCESS` — general field/array access
- `IDENTIFIER` — all identifier nodes (filtered by reachability later)
- CALL nodes with `*` or `->` in label, or `<operator>.indirection`/`<operator>.dereference` in `METHOD_FULL_NAME`

### Step 3: Expand free nodes for REACHING_DEF seeding

In Joern CPGs, REACHING_DEF edges flow through IDENTIFIER child nodes, not directly from CALL nodes. The expansion step:

```python
ast_matrix = graph.adjacency("AST")
free_indices = set(free_call_indices)
for f_idx in free_call_indices:
    _, children = ast_matrix.getrow(f_idx).nonzero()
    for c in children:
        free_indices.add(int(c))
```

This captures the pointer identifier that the free call operates on, which is the actual source of REACHING_DEF data flow.

### Step 4: Build data dependency matrix

Combine `REACHING_DEF` and `DDG` edge types into a single adjacency matrix:

```python
m_data = graph.combined_adjacency(["REACHING_DEF", "DDG"])
```

AST and CFG edges are intentionally excluded — AST causes false positives (parent→child traversal makes all descendants reachable), and CFG represents control flow, not data flow.

### Step 5: Compute reachability via power iteration

```
R = A + A² + A³ + ... + A^max_hops
```

Each matrix multiplication advances one hop along data dependency edges. The sum captures all paths up to `max_hops` length.

```python
result = zero_matrix
power = adj.copy()
for _ in range(max_hops):
    result = result + power
    power = power @ adj
    power.eliminate_zeros()  # sparsify to avoid densification
```

The `eliminate_zeros()` call is critical — without it, intermediate matrices densify and performance degrades to dense matrix operations.

### Step 6: Null-assignment anti-pattern exclusion

A common safe pattern is `free(ptr); ptr = NULL; use(ptr)`. To avoid false positives, compute reachability from NULL-labeled nodes and exclude free→deref pairs where a null assignment intervenes:

```python
null_mask = _compute_reachability(m_data, max_hops, sources=null_indices)
# Skip (f, d) if null_mask[f, d] > 0
```

### Step 7: Extract findings

For each `(free_idx, deref_idx)` pair where `R[free, deref] > 0` and the null mask does not intervene:
- Resolve the original free CALL node (may be a parent of the expanded AST child)
- Deduplicate by `(free_node.id, deref_node.id)`
- Create a `Finding` with file, line, and description

## Complexity

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Matrix multiply (sparse) | O(nnz) per hop | nnz = number of non-zeros |
| Reachability sum | O(max_hops × nnz) | Linear in hops |
| Finding extraction | O(|F| × |D|) | F = free nodes, D = deref nodes |

For typical C files (<10K nodes), this completes in under 1 second on CPU.

## Known Limitations (M1)

- **Single file only** — no cross-file data flow
- **Intraprocedural REACHING_DEF** — Joern's REACHING_DEF edges are intraprocedural; interprocedural UAF (free in function A, deref in function B) is not detected
- **Hardcoded free functions** — only detects `{free, vPortFree, kfree, cfree, afree}`
- **No alias analysis** — two pointers to the same allocation are treated independently
- **max_hops truncation** — paths longer than `max_hops` are missed
