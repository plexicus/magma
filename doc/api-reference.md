# API Reference

## `magma.types`

### `CPGNode`

A node in the Code Property Graph. Frozen dataclass.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `int` | Unique node ID from Joern |
| `type` | `str` | Node type (e.g., `"CALL"`, `"IDENTIFIER"`, `"METHOD"`) |
| `label` | `str` | Node label — typically the CODE attribute or NAME |
| `line_number` | `int \| None` | Source line number, or `None` if unavailable |
| `file` | `str \| None` | Source file path |
| `properties` | `dict` | All other DOT attributes (METHOD_FULL_NAME, etc.) |

### `CPGEdge`

An edge in the Code Property Graph. Frozen dataclass.

| Field | Type | Description |
|-------|------|-------------|
| `source` | `int` | Source node ID |
| `target` | `int` | Target node ID |
| `type` | `str` | Edge type (e.g., `"AST"`, `"REACHING_DEF"`, `"CFG"`) |

### `Finding`

A detected vulnerability. Mutable dataclass.

| Field | Type | Description |
|-------|------|-------------|
| `vuln_type` | `str` | Vulnerability class (e.g., `"Use-After-Free"`) |
| `file` | `str` | Source file path |
| `line` | `int` | Line number of the dereference |
| `description` | `str` | Human-readable explanation |
| `path` | `list[int] \| None` | Node IDs along the path (future MQL use) |

**Methods:**
- `to_dict() -> dict` — JSON-serializable representation

---

## `magma.ingest`

### `JoernError`

Exception raised when Joern CLI fails or is not installed.

### `run_joern(file_path: Path, output_dir: Path) -> Path`

Run Joern CLI to parse a C file and export the CPG as DOT.

**Parameters:**
- `file_path` — Path to the C source file
- `output_dir` — Parent directory for Joern output

**Returns:** Path to the exported `.dot` file.

**Raises:** `JoernError` if `joern-parse`/`joern-export` fails or is not found.

**Implementation notes:**
- Creates a unique subdirectory under `output_dir` (UUID prefix) because `joern-export` requires the output directory to NOT exist
- Filters JVM warnings from stderr — only checks `returncode` for actual failures

### `load_cpg(dot_path: Path) -> tuple[list[CPGNode], list[CPGEdge]]`

Parse a Joern DOT export into node and edge lists.

**Parameters:**
- `dot_path` — Path to the `.dot` file

**Returns:** Tuple of `(nodes, edges)`.

**Raises:** `JoernError` if the file cannot be read or parsed.

**Parser details:**
- Edge lines are matched first (regex contains `->`) to avoid misclassifying edge targets as nodes
- Node attributes: `label` → node type, `CODE`/`NAME` → node label, `LINE_NUMBER` → line, `FILENAME` → file
- All other attributes go into `CPGNode.properties`

### Constants

**Node types:** `NODE_TYPE_CALL`, `NODE_TYPE_IDENTIFIER`, `NODE_TYPE_FIELD_IDENTIFIER`, `NODE_TYPE_LITERAL`, `NODE_TYPE_BLOCK`, `NODE_TYPE_METHOD`, `NODE_TYPE_METHOD_RETURN`, `NODE_TYPE_LOCAL`, `NODE_TYPE_UNKNOWN`

**Edge types:** `EDGE_TYPE_AST`, `EDGE_TYPE_CFG`, `EDGE_TYPE_REACHING_DEF`, `EDGE_TYPE_CDG`, `EDGE_TYPE_EVAL_TYPE`, `EDGE_TYPE_REF`

---

## `magma.graph`

### `CPGGraph`

Code Property Graph backed by per-edge-type scipy sparse CSR matrices.

#### `__init__(self, nodes: list[CPGNode], edges: list[CPGEdge])`

Build the graph from node and edge lists. Constructs:
- `node_id → matrix_index` mapping
- Per-edge-type CSR adjacency matrices

Edges referencing unknown node IDs are silently dropped.

#### `adjacency(self, edge_type: str) -> sp.csr_matrix`

Return the sparse adjacency matrix for a given edge type.

**Returns:** CSR matrix of shape `(N, N)` where `M[i,j] = 1` if an edge of the given type exists from node `i` to node `j`. Returns a zero matrix if the edge type is absent.

#### `combined_adjacency(self, edge_types: list[str]) -> sp.csr_matrix`

Return a combined adjacency matrix for multiple edge types. Result is binary-clamped — `M[i,j] = 1` if ANY of the specified edge types has an edge from `i` to `j`.

#### `node_at(self, idx: int) -> CPGNode`

Return the node at a given matrix index.

#### `nodes_of_type(self, node_type: str) -> list[int]`

Return matrix indices for all nodes of a given type.

#### `nodes_with_label(self, label_substring: str) -> list[int]`

Return matrix indices for nodes whose label contains the given substring.

#### `edge_types(self) -> set[str]`

Return all edge types present in the graph.

#### `node_count: int` (property)

Number of nodes in the graph.

---

## `magma.query`

### `detect_uaf(graph: CPGGraph, max_hops: int = 5, device: Literal["cpu", "gpu"] = "cpu") -> list[Finding]`

Detect Use-After-Free vulnerabilities via sparse matrix reachability.

**Algorithm:**
1. Find all CALL nodes where callee is a free-family function (`free`, `vPortFree`, `kfree`, `cfree`, `afree`)
2. Find all dereference nodes (INDIRECT_FIELD_ACCESS, INDIRECT_INDEX_ACCESS, FIELD_ACCESS, INDEX_ACCESS, IDENTIFIER, operator indirection calls)
3. Expand free CALL nodes to include AST children (pointer identifiers) for REACHING_DEF seeding
4. Build data dependency adjacency matrix from REACHING_DEF/DDG edges
5. Compute reachability: `R = A + A² + ... + A^max_hops`
6. Compute null-assignment mask (reachability from NULL-labeled nodes)
7. Find `(free, deref)` pairs where `R[free, deref] > 0` and null mask does not intervene

**Parameters:**
- `graph` — The CPG graph to query
- `max_hops` — Maximum data dependency hops (default: 5)
- `device` — Computation device: `'cpu'` (scipy, default) or `'gpu'` (Mojo SIMD / Metal)

**Returns:** List of `Finding` objects.

### `format_findings(findings: list[Finding]) -> str`

Format findings as a human-readable string with numbered entries showing file, line, and description.

### Internal functions

- `_find_free_nodes(graph)` — Match CALL nodes by label substring or `METHOD_FULL_NAME` property
- `_find_deref_nodes(graph)` — Find dereference-related node types + operator indirection calls + all IDENTIFIER nodes
- `_find_null_assignment_nodes(graph)` — Find nodes with "NULL" or "NIL" in label
- `_compute_reachability(adjacency, max_hops, sources=None, device='cpu')` — Matrix power iteration. If `sources` is provided, only computes reachability from those source indices. `device='gpu'` uses Mojo SIMD for large matrices.

---

## `magma.gpu`

### `SparseMatrix`

Device-agnostic sparse matrix wrapper. Wraps scipy CSR for CPU and provides GPU backend.

#### `__init__(self, matrix: sp.csr_matrix, device: Device = "cpu")`

#### `from_csr(cls, matrix, device='cpu') -> SparseMatrix`

#### `matvec(self, x: np.ndarray) -> np.ndarray`

Sparse matrix-vector multiply. GPU path uses Mojo SIMD for matrices with 1000+ rows.

#### `hadamard(self, other: SparseMatrix) -> SparseMatrix`

Element-wise (Hadamard) product.

#### `boolean_mask(self, mask: SparseMatrix) -> SparseMatrix`

Keep entries where mask is nonzero (equivalent to hadamard).

### `VRAMConfig`

Configuration for VRAM sharding.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `budget_bytes` | `int` | 256 MB | Maximum VRAM budget |
| `chunk_rows` | `int` | 0 (auto) | Rows per chunk |
| `unified_memory` | `bool` | `True` | Enable Unified Memory fallback |

### `ShardedSparseMatrix`

Sparse matrix with VRAM-aware chunked operations.

#### `from_csr(cls, csr, config=None) -> ShardedSparseMatrix`

#### `matvec(self, x: np.ndarray) -> np.ndarray`

Chunked matvec — processes row chunks independently, concatenates results.

#### `hadamard(self, other: ShardedSparseMatrix) -> ShardedSparseMatrix`

Chunked Hadamard product.

#### Properties: `shape`, `using_unified_memory`, `num_chunks`

### Utility functions

- `estimate_matrix_bytes(csr)` — Estimate CSR memory in bytes
- `compute_chunk_rows(csr, budget_bytes)` — Auto-calculate chunk size
- `chunk_csr(csr, chunk_rows)` — Split CSR into row-wise sub-matrices
- `make_reachability_gpu(adjacency, max_hops, device)` — Reachability computation on specified device

---

## `magma.mojo_bridge`

### `MojoCSR`

Python wrapper around Mojo CSR operations via subprocess.

#### `__init__(self, row_ptr, col_idx, nrows, ncols)`

#### `from_csr_parquet(cls, csr_path, edge_type) -> MojoCSR`

Load CSR from Parquet CSR index table.

#### `matvec(self, x: list[float]) -> list[float]`

Scalar sparse matrix-vector multiply via Mojo.

#### `matvec_simd(self, x: list[float]) -> list[float]`

SIMD-accelerated matvec using `SIMD[DType.float64, 4]` with `reduce_add()`.

#### `hadamard(self, other: MojoCSR) -> MojoCSR`

Hadamard product with two-pointer intersection of sorted columns.

#### `boolean_mask(self, mask: MojoCSR) -> MojoCSR`

Equivalent to hadamard.

### `mojo_available() -> bool`

Check if Mojo is installed and the CSR module exists.

---

## `magma.cli`

### Commands

#### `magma parse <file> [-o OUTPUT]`

Parse a C file and export its CPG as DOT. Default output: `<file>.cpg.dot`.

Exit codes: `0` success, `2` error.

#### `magma scan <file> [--max-hops N] [--json-output]`

Scan a C file for Use-After-Free vulnerabilities. Full pipeline: parse → ingest → graph → query → output.

Exit codes: `0` clean, `1` vulnerabilities found, `2` error.

**Options:**
- `--max-hops` — Maximum data dependency hops (default: 5)
- `--json-output` — Emit JSON array of findings instead of human-readable format
