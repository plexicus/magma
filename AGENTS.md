# AGENTS.md

> Primary source of truth for AI coding assistants operating in this repository.

---

## PROJECT_CONTEXT

**What:** Magma is a vulnerability detection engine that represents C source code as sparse matrices and detects security bugs through matrix algebra. It parses C files via Joern, builds Code Property Graphs (CPGs), and detects Use-After-Free (UAF) vulnerabilities through sparse matrix reachability.

**Vision:** GPU-accelerated Universal Code Property Graph (UCPG) engine for detecting 0-day vulnerabilities via tensor algebra.

**Current phase:** M1 complete (UAF detection prototype). See ROADMAP.md for phases 1-5.

**Package name:** `magma-engine` (v0.1.0)
**Entry point:** `magma.cli:main` (Click CLI)

---

## TECH_STACK

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.10+ | `from __future__ import annotations` in all modules |
| Sparse matrices | scipy >= 1.11 | CSR format, `sp.csr_matrix` |
| Numerical | numpy >= 1.25 | Matrix operations, dtype management |
| CLI | Click >= 8.0 | `@click.group()` with `parse` and `scan` subcommands |
| Testing | pytest | `testpaths = ["tests"]` in pyproject.toml |
| External | Joern (JVM 11+) | `joern-parse` + `joern-export` for C parsing |
| Build | setuptools >= 68.0 | `src/magma/` layout |
| Columnar storage | pyarrow >= 14.0 | Apache Parquet for binary CPG export |
| GPU compute | Mojo 0.26+ | Native CSR struct, SIMD matvec via subprocess bridge |
| GPU runtime | Metal (Apple Silicon) | GPU GraphBLAS via Mojo/Metal kernels |

---

## ARCHITECTURE_&_FILE_MAPPING

### Directory layout

```
src/magma/
├── __init__.py        # Version string only
├── types.py           # Shared data types (CPGNode, CPGEdge, Finding)
├── ingest.py          # Joern CLI wrapper + DOT parser + Parquet bridge
├── parquet.py         # Binary CPG export/load via Apache Parquet + CSR index
├── graph.py           # CPGGraph: CPG → scipy sparse CSR matrices
├── query.py           # UAF detection via matrix power iteration (device='cpu'/'gpu')
├── gpu.py             # GPU SparseMatrix + VRAM sharding (ShardedSparseMatrix)
├── mojo_bridge.py     # Python↔Mojo bridge for CSR matvec (scalar + SIMD)
├── mojo/
│   ├── __init__.mojo  # Package init
│   ├── hello.mojo     # Hello-world verification
│   └── csr.mojo       # Native Mojo CSR struct with SIMD matvec
└── cli.py             # Click CLI entry point

tests/
├── conftest.py        # Shared fixtures (joern_available, corpus_path, sample_cpg_graph)
├── corpus/            # Hand-crafted C files (uaf_*.c = vulnerable, clean_*.c = safe)
├── golden/            # Golden Parquet fixtures for regression testing
├── test_ingest.py     # DOT parser + mocked Joern tests
├── test_parquet.py    # Parquet round-trip + file size tests
├── test_graph.py      # CPGGraph sparse matrix tests
├── test_query.py      # UAF detection algorithm tests
├── test_gpu.py        # GPU SparseMatrix operations (matvec, hadamard, detect_uaf)
├── test_mojo.py       # Mojo CSR + SIMD tests (US-106/107/108)
├── test_vram.py       # VRAM sharding tests (US-110)
├── test_cli.py        # CLI integration tests (CliRunner)
├── test_e2e.py        # Full pipeline with real Joern (9 files, parametrized)
├── test_golden_ingest.py  # Golden fixture regression (ingest)
├── test_golden_query.py   # Golden fixture regression (query)
└── test_benchmark.py      # Parquet vs DOT performance benchmarks

doc/                   # Technical documentation
examples/              # Example C files
```

### Module dependency chain

```
types.py ← ingest.py ← graph.py ← query.py ← cli.py
                ↑
           parquet.py
                ↑
         mojo_bridge.py  ←  mojo/csr.mojo
                ↑
            gpu.py  ←  query.py (device parameter)
```

- `types.py` has zero internal dependencies
- `ingest.py` depends on `types.py` and `parquet.py`
- `parquet.py` depends on `types.py` (pyarrow for I/O)
- `graph.py` depends on `types.py`
- `query.py` depends on `graph.py`, `types.py`, and `gpu.py` (for device parameter)
- `gpu.py` depends on `mojo_bridge.py` (for GPU matvec)
- `mojo_bridge.py` wraps `mojo/csr.mojo` via subprocess
- `cli.py` orchestrates all modules

### Data flow

```
C file → run_joern() → DOT file → load_cpg() → (nodes, edges)
→ CPGGraph(nodes, edges) → detect_uaf(graph, device="cpu"|"gpu") → list[Finding]
                                       │
                            ┌──────────┴──────────┐
                            │ CPU: scipy CSR       │ GPU: MojoCSR
                            │ power iteration      │ SIMD matvec +
                            │                      │ VRAM sharding
                            └──────────────────────┘
```

---

## GUIDELINES_&_BEST_PRACTICES

### Code style

- Use `from __future__ import annotations` in every module
- All public functions have type hints on parameters and return values
- Docstrings use Google style: Args, Returns, Raises sections
- Frozen dataclasses for immutable types (`CPGNode`, `CPGEdge`)
- Mutable dataclass only for `Finding` (it has a `to_dict()` method)
- No `any` types — use `dict`, `list[...]`, `tuple[...]` with specific inner types
- Constants use UPPER_SNAKE_CASE at module level

### Testing

- Unit tests run WITHOUT Joern — use fixtures and mocks
- E2E tests require Joern — skip gracefully with `pytest.importorskip` / `joern_available` fixture
- Test file naming: `test_<module>.py` mirrors `src/magma/<module>.py`
- Corpus files: `uaf_*.c` for vulnerable, `clean_*.c` for safe patterns
- New corpus files must be added to the parametrized list in `test_e2e.py`

### Sparse matrix conventions

- Always use `sp.csr_matrix` (Compressed Sparse Row)
- Call `eliminate_zeros()` after matrix multiplication to prevent densification
- Use `np.int8` for binary adjacency matrices, `np.float64` for multiplication
- Clamp combined matrices to binary: `result.data = np.clip(result.data, 0, 1)`

### Joern integration

- Joern v4.0.470 does NOT support `--format json` — use `--format dot` only
- `joern-export` requires output directory to NOT exist — generate unique child path
- JVM warnings go to stderr even on success — only check `returncode`
- REACHING_DEF edges flow through IDENTIFIER child nodes, not directly from CALL nodes
- AST edges in reachability matrix cause false positives — exclude from `DATA_DEP_EDGE_TYPES`

---

## COMMAND_CHEATSHEET

```bash
# Install in dev mode
pip install -e .

# Run CLI
magma scan path/to/file.c              # Full pipeline
magma scan --json-output path/to/file.c # JSON output
magma scan --max-hops 10 path/to/file.c # Tune sensitivity
magma parse path/to/file.c             # Export CPG as Parquet (default)
magma parse --format dot path/to/file.c # Export CPG as DOT (backward compat)

# Tests
pytest tests/ -v                        # All tests (119 passed, 2 skipped)
pytest tests/test_gpu.py tests/test_mojo.py tests/test_vram.py -v  # GPU/Mojo only
pytest tests/test_e2e.py -v            # E2E (requires Joern)

# Lint (if ruff configured)
ruff check src/

# Mojo verification
mojo run src/magma/mojo/hello.mojo      # Hello world
mojo run src/magma/mojo/csr.mojo        # CSR self-test
```

---

## ANTI_PATTERNS

1. **Do NOT include AST edges in reachability matrix.** AST parent→child traversal makes all descendants reachable, producing false positives. Use AST only for expanding source nodes (free CALL → AST children).

2. **Do NOT assume Joern exports JSON.** Joern v4.0.470 only supports DOT and GraphML. The `--format json` flag is silently ignored or errors.

3. **Do NOT create the joern-export output directory.** `joern-export` fails with "output directory already exists". Generate a path that doesn't exist and let Joern create it.

4. **Do NOT check stderr for JVM warnings.** JVM prints warnings to stderr even on success. Only trust `returncode`.

5. **Do NOT match node lines as edges.** Edge regex (`->`) must be checked before node regex in DOT parsing. Edge target lines like `"68719476738"` match the node pattern.

6. **Do NOT hardcode query logic in cli.py.** Query logic belongs in `query.py`. CLI only orchestrates the pipeline.

7. **Do NOT use dense matrices.** Always use sparse CSR. Densification kills performance on real CPGs.

8. **Do NOT use `let` or `owned` in Mojo 0.26.** Mojo 0.26 requires `var` for mutable bindings. `let` and `owned` keywords are not supported. Use `.copy()` for value copies and `^` for ownership transfer.

9. **Do NOT convert PythonObject to Mojo native types directly.** `Int(pyobj)` and `Float64(pyobj)` don't work in Mojo 0.26. Stay in PythonObject land or embed data as native Mojo literals via the data-baking approach.

10. **Do NOT install pyarrow into Mojo's pixi environment.** It corrupts the libpython link. Keep pyarrow in the project's `.venv` only.

---

## RECENT_DECISIONS

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-08 | Chose DOT format over JSON for Joern export | Joern v4.0.470 doesn't support `--format json` |
| 2026-04-08 | AST children expansion for REACHING_DEF seeding | Real CPGs: REACHING_DEF flows through IDENTIFIER children, not from CALL nodes directly |
| 2026-04-08 | REACHING_DEF-only in reachability matrix (not AST) | Including AST causes false positives via parent→child traversal |
| 2026-04-08 | UUID-based temp dirs for joern-export | joern-export requires output dir to NOT exist |
| 2026-04-08 | Regex-based DOT parser over full grammar | Joern's DOT output is structured enough for regex; simpler and faster |
| 2026-04-08 | Apache Parquet for binary CPG export | Columnar format, ≤50% of DOT size, CSR index for zero-copy Mojo access |
| 2026-04-08 | Mojo via pixi + Modular conda channel | `dl.modular.com` and `brew modular` are 404; pixi is the only working install path |
| 2026-04-08 | Data baking for Mojo bridge | PythonObject can't convert to Mojo Int/Float64; embed values as native List append calls |
| 2026-04-08 | Subprocess bridge over FFI | Mojo 0.26 Python interop is via `Python.import_module()`, not direct C FFI; subprocess is simpler and more reliable |
| 2026-04-08 | VRAM budget default 256 MB with Unified Memory fallback | Conservative default; Unified Memory ensures correctness when budget exceeded |

---

## OMC_WORKFLOW_CONVENTIONS

This project uses [oh-my-claudecode](https://github.com/anthropics/claude-code) (OMC) for AI-assisted development workflows.

### Key workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| **ralph** | "ralph", "don't stop", "must complete" | PRD-driven persistence loop — works until all user stories pass verification |
| **autopilot** | "autopilot", full autonomous execution | Idea → plan → implement → QA → validate |
| **ultrawork** | "ulw" | Parallel execution engine for high-throughput task completion |
| **ralplan** | "ralplan", vague requests | Consensus planning: Planner → Architect → Critic loop |
| **deep-interview** | "deep interview", vague ideas | Socratic requirements gathering with ambiguity gating |
| **team** | "/team" | N coordinated agents on shared task list |

### PRD-driven development (ralph)

When working with ralph:

1. Stories live in `.omc/prd.json` with concrete acceptance criteria
2. Progress tracked in `.omc/progress.txt`
3. Each story must have `passes: true` before completion
4. Architect verification against specific acceptance criteria (not vague "is it done?")
5. Deslop pass on changed files after reviewer approval

### Agent delegation tiers

| Tier | Model | Use for |
|------|-------|---------|
| LOW | Haiku | Simple lookups, exploration, search |
| MEDIUM | Sonnet | Standard implementation, refactoring, testing |
| HIGH | Opus | Architecture, deep analysis, security review |

### State files

```
.omc/
├── prd.json          # User stories with acceptance criteria
├── progress.txt      # Iteration log and learnings
├── plans/            # Generated work plans
├── state/            # Mode state (ralph, autopilot, etc.)
└── specs/            # Deep interview specs
```

### Commit protocol

- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
- Never commit `.env`, credentials, or `.omc/state/` files

---

## ROADMAP_CONTEXT

For AI assistants working on future phases:

**Phase 1 — GPU Acceleration (COMPLETE):** Apache Parquet binary CPG export, native Mojo CSR struct with SIMD matvec, GPU SparseMatrix with device='cpu'/'gpu', VRAM sharding with configurable budget + Unified Memory fallback. 119 tests passing.

**Phase 2 — MQL Compiler:** Declarative JSON query schema, query optimizer, dynamic masking (subtract paths through sanitizer functions), path reconstruction.

**Phase 3 — Multi-File & Cross-Language:** Project-level ingestion, cross-file linker for `extern` calls, UCPG homogenization (language-agnostic node mapping), polyglot edge stitching.

**Phase 4 — Advanced Vulnerability Classes:** Value-Set Analysis tensors (buffer overflows), 3D tensors for concurrency (TOCTOU, race conditions), transitive closure ($A^n$) for second-order vulnerabilities.

**Phase 5 — Autonomous AppSec Agents:** LLM API gateway (gRPC/REST), context-optimized findings, automated PoC loop.

See `ROADMAP.md` for detailed task breakdowns per phase.
