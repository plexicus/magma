# Magma — Code Property Graph Query Engine

Magma is a vulnerability detection engine that represents source code as sparse matrices and detects security bugs through matrix algebra. It parses C source files via [Joern](https://joern.io/), builds Code Property Graphs, and detects Use-After-Free vulnerabilities through sparse matrix reachability. Phase 1 adds GPU acceleration via Mojo SIMD and Metal, plus binary CPG export via Apache Parquet.

See [ROADMAP.md](ROADMAP.md) for the full development plan through MQL query language, multi-language analysis, and autonomous LLM agent integration.

## Prerequisites

- Python 3.10+
- [Joern](https://joern.io/) (Java-based code analysis platform, requires JVM 11+)
- [Mojo](https://www.modular.com/mojo) (optional, for GPU/SIMD acceleration — installed via [pixi](https://pixi.sh/))

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick Start

```bash
# Scan a C file for Use-After-Free vulnerabilities
magma scan path/to/file.c

# Parse a C file and export its Code Property Graph (Parquet by default)
magma parse path/to/file.c

# JSON output for programmatic use
magma scan --json-output path/to/file.c

# Export as DOT (backward compat)
magma parse --format dot path/to/file.c

# GPU-accelerated detection (requires Mojo)
# detect_uaf(graph, device="gpu")
```

## Architecture

```
C Source File
    │
    ▼
┌─────────────┐
│ Joern CLI   │  (parse + export as DOT)
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│ CPG (DOT /  │────>│ scipy sparse │────>│ Mojo CSR +    │
│  Parquet)   │     │ adjacency    │     │ SIMD / GPU    │
└─────────────┘     │ matrices     │     │ (optional)    │
                    └──────┬──────┘     └───────┬───────┘
                           │                    │
                    ┌──────▼────────────────────▼───┐
                    │ UAF Query Engine               │
                    │ (matrix power iteration        │
                    │  on CPU or GPU via device=)    │
                    └──────────────┬────────────────┘
                                  │
                    ┌─────────────▼─────────┐
                    │ Findings              │  (file:line coordinates)
                    └───────────────────────┘
```

### Modules

| Module | Purpose |
|--------|---------|
| `ingest.py` | Joern CLI wrapper + CPG DOT parser + Parquet bridge |
| `parquet.py` | Binary CPG export/load via Apache Parquet with CSR index |
| `graph.py` | CPG → scipy sparse adjacency matrices |
| `query.py` | UAF detection via sparse matrix reachability (`device='cpu'/'gpu'`) |
| `gpu.py` | GPU SparseMatrix + VRAM sharding (`ShardedSparseMatrix`, `VRAMConfig`) |
| `mojo_bridge.py` | Python↔Mojo bridge for CSR matvec (scalar + SIMD) |
| `mojo/csr.mojo` | Native Mojo CSR struct with SIMD-accelerated matvec |
| `cli.py` | Click CLI with `parse` and `scan` commands |
| `types.py` | Shared data types (CPGNode, CPGEdge, Finding) |

## Running Tests

```bash
# All tests (119 passed, 2 skipped)
pytest tests/ -v

# Unit tests only (no Joern required)
pytest tests/test_ingest.py tests/test_graph.py tests/test_query.py tests/test_cli.py -v

# GPU + Mojo tests
pytest tests/test_gpu.py tests/test_mojo.py tests/test_vram.py -v

# E2E tests (requires Joern)
pytest tests/test_e2e.py -v
```

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **M1** | UAF detection via sparse matrix reachability (Python + scipy) | Complete |
| **Phase 1** | Parquet export, Mojo CSR, SIMD, GPU GraphBLAS, VRAM sharding | **Complete** |
| **Phase 2** | MQL query language (JSON-based declarative queries + optimizer) | Planned |
| **Phase 3** | Multi-file project analysis and cross-language support | Planned |
| **Phase 4** | Advanced vulnerability classes (VSA, concurrency, transitive closure) | Planned |
| **Phase 5** | Autonomous LLM agent integration | Planned |

See [ROADMAP.md](ROADMAP.md) for detailed phase breakdowns and tasks.
