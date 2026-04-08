# Testing Guide

## Test Structure

```
tests/
├── conftest.py            # Shared fixtures
├── corpus/                # Hand-crafted C test files
│   ├── uaf_simple.c       # free(ptr); *ptr = 1;
│   ├── uaf_branch.c       # Conditional free
│   ├── uaf_loop.c         # Free then loop-use
│   ├── uaf_function_call.c  # Free then func(ptr)
│   ├── uaf_struct_member.c  # Free then obj->field
│   ├── uaf_double_free.c    # Double free
│   ├── clean_no_uaf.c       # Correct malloc/use/free
│   ├── clean_after_null.c   # free; ptr=NULL; use
│   └── clean_realloc.c      # Realloc pattern
├── golden/                # Parquet golden fixtures for regression
├── test_ingest.py         # DOT parser + Joern CLI tests (11 tests)
├── test_parquet.py        # Parquet round-trip + file size tests (6 tests)
├── test_graph.py          # CPGGraph sparse matrix tests (9 tests)
├── test_query.py          # UAF detection algorithm tests (13 tests)
├── test_gpu.py            # GPU SparseMatrix operations (8 tests)
├── test_mojo.py           # Mojo CSR + SIMD tests (22 tests, requires Mojo)
├── test_vram.py           # VRAM sharding tests (17 tests)
├── test_cli.py            # CLI integration tests (6 tests)
├── test_e2e.py            # End-to-end with real Joern (9 files, parametrized)
├── test_golden_ingest.py  # Golden fixture regression (ingest)
├── test_golden_query.py   # Golden fixture regression (query)
└── test_benchmark.py      # Parquet vs DOT performance benchmarks
```

## Running Tests

```bash
# Full suite (119 passed, 2 skipped)
pytest tests/ -v

# Unit tests only (no Joern required)
pytest tests/test_ingest.py tests/test_graph.py tests/test_query.py tests/test_cli.py -v

# GPU + Mojo tests (requires Mojo installed)
pytest tests/test_gpu.py tests/test_mojo.py tests/test_vram.py -v

# E2E tests (requires Joern installed)
pytest tests/test_e2e.py -v
```

## Test Categories

### Unit tests (`test_ingest.py`, `test_graph.py`, `test_query.py`, `test_cli.py`)

Run without Joern. Use mocked data and fixtures.

- **test_ingest.py** — DOT parsing with `SAMPLE_DOT` fixture, error handling for missing files, mocked `run_joern` subprocess calls
- **test_parquet.py** — Parquet round-trip (nodes, edges, properties, null fields, empty graph, multi-edge types), file size vs DOT
- **test_graph.py** — Hand-crafted CPGNode/CPGEdge lists → CPGGraph → verify adjacency matrix sparsity patterns, node type filtering, edge type enumeration, empty/single-node edge cases
- **test_query.py** — Synthetic CPG graphs with known free/deref/null patterns → verify detect_uaf finds/excludes expected pairs, max_hops behavior, multi-pair detection
- **test_cli.py** — Click CliRunner tests for parse/scan commands, exit codes, JSON output format

### GPU tests (`test_gpu.py`, `test_mojo.py`, `test_vram.py`)

- **test_gpu.py** — SparseMatrix CPU/GPU matvec, hadamard, boolean_mask equivalence. `detect_uaf(device='cpu')` vs `detect_uaf(device='gpu')` produce identical results.
- **test_mojo.py** — Mojo setup (version, hello-world, Python interop), CSR matvec (identity, sparse, random), hadamard, SIMD matvec (matches scalar exactly), Mojo bridge from Parquet. Requires Mojo installed; skips gracefully otherwise.
- **test_vram.py** — Memory estimation, chunk row calculation, CSR chunking, ShardedSparseMatrix matvec/hadamard (chunked vs single-shot equivalence), Unified Memory fallback, 10K-node synthetic graph, budget constraint verification.

### E2E tests (`test_e2e.py`)

Require Joern installed. Run the full pipeline: C file → Joern parse → DOT export → ingest → graph → query → findings.

- Parametrized over all corpus files
- Assert vulnerable files produce ≥1 finding
- Assert clean files produce 0 findings
- Skip gracefully with `pytest.importorskip` when Joern is not installed

## Fixtures

### `conftest.py`

| Fixture | Scope | Description |
|---------|-------|-------------|
| `joern_available` | session | `True` if `joern-parse` is on PATH |
| `corpus_path` | session | Path to `tests/corpus/` directory |
| `sample_cpg_graph` | function | Pre-built CPGGraph with known structure for unit tests |

## Writing New Tests

### Adding a new corpus file

1. Create the C file in `tests/corpus/`
2. Add it to the parametrized list in `test_e2e.py`
3. Classify as `vulnerable` or `clean`
4. For vulnerable files, verify the expected finding details (line number, description pattern)

### Testing a new query

1. Build a synthetic CPGGraph with `CPGNode`/`CPGEdge` lists
2. Call `detect_uaf()` (or your new query function)
3. Assert specific Finding properties
4. Test both positive (vulnerability found) and negative (no false positive) cases
