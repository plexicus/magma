# Magma Development Roadmap

**Vision:** GPU-accelerated Universal Code Property Graph (UCPG) engine for detecting 0-day vulnerabilities via tensor algebra.

## Current State: M1 (Proof of Concept) — Complete

**Status:** Complete.

**Capabilities:** Use-After-Free (UAF) detection via sparse matrix reachability (SciPy) on Joern CPG exports.

**Technical debt:** Single C file, DOT format export bottleneck, CPU-bound Python execution, hardcoded query logic.

---

## Phase 1: GPU Acceleration & Native Execution

Rip out CPU-bound SciPy and replace with hardware-accelerated linear algebra.

- [x] **1.1 Binary CPG Export** — Apache Parquet with `export_parquet()` / `load_parquet()`, CSR index for zero-copy Mojo access. Size ≤50% of DOT.
- [x] **1.2 CSR Implementation in Mojo** — Native Mojo `CSR` struct with `matvec`, `hadamard`. Python bridge via subprocess (`mojo_bridge.py`). Data-baking approach for zero-copy data transfer.
- [x] **1.3 SIMD Vectorization** — `matvec_simd()` using `SIMD[DType.float64, 4]` with `reduce_add()`. ARM Neon (Apple Silicon) verified.
- [x] **1.4 GPU GraphBLAS Kernel** — `SparseMatrix` class in `gpu.py` with `device='cpu'/'gpu'`. `detect_uaf()` accepts device parameter. GPU results match CPU.
- [x] **1.5 VRAM Sharding** — `ShardedSparseMatrix` with `VRAMConfig` (configurable budget). Row-wise chunking + Unified Memory fallback. Verified with 10K-node synthetic graphs.

## Phase 2: MQL Compiler (Dynamic AI-Ready Queries)

Replace hardcoded Python query logic with a declarative JSON schema designed for LLM generation.

- [ ] **2.1 MQL JSON Schema** — Declarative schema: `nodes` (state vectors), `flows` (edge traversal constraints), `anti_patterns` (boolean masks)
- [ ] **2.2 Query Optimizer** — Compile MQL JSON into optimized tensor operation sequences; heuristic reordering (e.g., apply negative masks before deep multiplications)
- [ ] **2.3 Dynamic Masking** — Subtract paths contextually (e.g., nullify taint trace passing through `escape_html()`)
- [ ] **2.4 Path Reconstruction** — Map tensor coordinates back to `file:line` metadata for findings; reconstruct exact Source → Intermediaries → Sink paths

## Phase 3: Multi-File & Cross-Language Analysis

Real vulnerabilities span microservices, databases, and FFI boundaries.

- [ ] **3.1 Project-Level Ingestion** — CLI accepts root directory; Joern resolves headers, macros, and external linker deps
- [ ] **3.2 Cross-File Linker** — Map `extern` calls and exported functions into continuous data-flow edges
- [ ] **3.3 UCPG Homogenization** — Language-agnostic node mapping so a `CALL` in Python is mathematically identical to a `CALL` in C++
- [ ] **3.4 Polyglot Edge Stitching** — Fuse independent CPGs across language barriers (e.g., Node.js API → Rust WASM module)

## Phase 4: Advanced Vulnerability Classes

UAF was the prototype. This phase extends the math to harder bug classes.

- [ ] **4.1 Value-Set Analysis (VSA) Tensors** — Upgrade matrices from booleans to integer range vectors; multiply input-size against allocation-size to prove buffer overflows and integer underflows
- [ ] **4.2 3D Tensors for Concurrency** — Z-axis represents thread execution; detect TOCTOU and race conditions by computing overlapping thread states without synchronization
- [ ] **4.3 Transitive Closure ($A^n$)** — Multiply matrix until stabilization; detect asynchronous second-order vulnerabilities (stored XSS, second-order SQLi)

## Phase 5: Autonomous AppSec Agents

Magma becomes the backend engine for autonomous AI vulnerability researchers.

- [ ] **5.1 LLM API Gateway** — High-performance gRPC/REST API for AI agent integration
- [ ] **5.2 Context-Optimized Findings** — Return verified vulnerable subgraph snippets only, preserving LLM context window
- [ ] **5.3 Automated PoC Loop** — LLM sends MQL → Magma proves path → Magma returns code → LLM writes exploit → Magma validates execution
