# Architecture

## Overview

Magma represents C source code as sparse matrices and detects security vulnerabilities through matrix algebra. The pipeline flows: **C source → Joern CPG → sparse matrices → reachability query → findings**.

## Pipeline

```
C Source File
    │
    ▼
┌─────────────┐
│ Joern CLI   │  joern-parse + joern-export --format dot
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│ CPG DOT     │────>│ scipy sparse │
│ (nodes +    │     │ adjacency    │
│  edges)     │     │ matrices     │
└─────────────┘     └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ UAF Query   │  matrix power iteration
                    │ Engine      │  for reachability
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Findings    │  file:line coordinates
                    └─────────────┘
```

## Module Responsibilities

| Module | Role | Key Interface |
|--------|------|---------------|
| `types.py` | Shared data types | `CPGNode`, `CPGEdge`, `Finding` |
| `ingest.py` | Joern CLI wrapper + DOT parser | `run_joern()`, `load_cpg()` |
| `graph.py` | CPG → sparse matrices | `CPGGraph` class |
| `query.py` | UAF detection via reachability | `detect_uaf()` |
| `cli.py` | User-facing CLI | `magma parse`, `magma scan` |

## Data Flow

1. **`cli.py`** orchestrates the pipeline. `magma scan file.c` calls each stage in sequence.
2. **`ingest.py:run_joern()`** shells out to `joern-parse` and `joern-export`, producing a DOT file.
3. **`ingest.py:load_cpg()`** parses the DOT into `list[CPGNode]` and `list[CPGEdge]`.
4. **`graph.py:CPGGraph`** builds per-edge-type scipy sparse CSR matrices from the node/edge lists.
5. **`query.py:detect_uaf()`** computes reachability via matrix power iteration and returns `list[Finding]`.
6. **`cli.py`** formats output (human-readable or JSON) and sets exit code.

## Design Decisions

### Sparse matrices over graph traversal

Traditional graph engines traverse edges one at a time. Magma encodes the entire graph as a sparse adjacency matrix and uses matrix multiplication for reachability. This enables:
- Batch path discovery in O(n) matrix ops instead of O(n²) BFS calls
- Natural parallelism (GPU/BLAS offload in future phases)
- Composable queries via matrix algebra (union = addition, intersection = Hadamard product)

### Per-edge-type matrices

Each edge type (AST, CFG, REACHING_DEF, etc.) gets its own sparse matrix. Queries combine edge types with `combined_adjacency()` rather than operating on a single mixed graph. This avoids false-positive data flow across unrelated edge types.

### DOT format over JSON

Joern v4.0.470 does not support `--format json`. DOT is the only format that exports node attributes (CODE, LINE_NUMBER, METHOD_FULL_NAME) alongside edges with typed labels. The DOT parser uses regex matching with edge-first priority (edge lines contain `->`, making them distinguishable from node lines).

### AST children expansion for REACHING_DEF seeding

In real Joern CPGs, REACHING_DEF edges flow through IDENTIFIER child nodes, not directly from CALL nodes. A `free(ptr)` call node has no outgoing REACHING_DEF edges — the data flow goes through the `ptr` IDENTIFIER node that is an AST child of the CALL. The query engine expands free CALL nodes to include their AST children before seeding reachability, while keeping the reachability matrix itself REACHING_DEF-only to avoid false positives from AST parent→child traversal.
