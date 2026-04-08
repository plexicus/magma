# Magma — Code Property Graph Query Engine

Magma is a vulnerability detection engine that represents source code as sparse matrices and detects security bugs through matrix algebra. It parses C source files via [Joern](https://joern.io/), builds Code Property Graphs, and detects Use-After-Free vulnerabilities through sparse matrix reachability.

See [ROADMAP.md](ROADMAP.md) for the full development plan through GPU acceleration, MQL query language, multi-language analysis, and autonomous LLM agent integration.

## Prerequisites

- Python 3.10+
- [Joern](https://joern.io/) (Java-based code analysis platform, requires JVM 11+)

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

# Parse a C file and export its Code Property Graph
magma parse path/to/file.c

# JSON output for programmatic use
magma scan --json-output path/to/file.c
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
┌─────────────┐     ┌──────────────┐
│ CPG DOT     │────>│ scipy sparse │
│ (nodes +    │     │ adjacency    │
│  edges)     │     │ matrices     │
└─────────────┘     └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ UAF Query   │  (matrix power iteration
                    │ Engine      │   for reachability)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Findings    │  (file:line coordinates)
                    └─────────────┘
```

### Modules

| Module | Purpose |
|--------|---------|
| `ingest.py` | Joern CLI wrapper + CPG DOT parser |
| `graph.py` | CPG → scipy sparse adjacency matrices |
| `query.py` | UAF detection via sparse matrix reachability |
| `cli.py` | Click CLI with `parse` and `scan` commands |
| `types.py` | Shared data types (CPGNode, CPGEdge, Finding) |

## Running Tests

```bash
# Unit tests (no Joern required)
pytest tests/test_ingest.py tests/test_graph.py tests/test_query.py tests/test_cli.py -v

# E2E tests (requires Joern)
pytest tests/test_e2e.py -v
```

## M1 Scope (Complete)

The M1 prototype proved the core concept: representing code as sparse matrices and detecting vulnerability patterns through matrix algebra. It is intentionally limited:

- **Language:** C only
- **Input:** Single file per analysis
- **Vulnerability:** Use-After-Free (hardcoded query)
- **No GPU:** CPU-only via scipy
- **No MQL:** Query logic is hardcoded in Python

## Roadmap

| Phase | Focus |
|-------|-------|
| **M1** (complete) | UAF detection via sparse matrix reachability (Python + scipy) |
| **Phase 1** | GPU acceleration (Mojo/MLIR/GraphBLAS), binary CPG export |
| **Phase 2** | MQL query language (JSON-based declarative queries + optimizer) |
| **Phase 3** | Multi-file project analysis and cross-language support |
| **Phase 4** | Advanced vulnerability classes (VSA, concurrency, transitive closure) |
| **Phase 5** | Autonomous LLM agent integration |

See [ROADMAP.md](ROADMAP.md) for detailed phase breakdowns and tasks.
