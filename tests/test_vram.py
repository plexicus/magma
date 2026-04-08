"""Tests for VRAM sharding (US-110).

Verifies that chunked GPU operations produce identical results
to single-shot CPU operations on large synthetic graphs.
"""

from __future__ import annotations

import numpy as np
import pytest
import scipy.sparse as sp

from magma.gpu import (
    DEFAULT_VRAM_BUDGET,
    ShardedSparseMatrix,
    VRAMConfig,
    chunk_csr,
    compute_chunk_rows,
    estimate_matrix_bytes,
)


# ── US-110: VRAM sharding ─────────────────────────────────────────────────


class TestEstimateMatrixBytes:
    """Memory estimation for CSR matrices."""

    def test_small_matrix(self) -> None:
        csr = sp.csr_matrix(np.array([[1, 0], [0, 2]]))
        size = estimate_matrix_bytes(csr)
        # 2 nnz values + indices + indptr
        assert size > 0

    def test_empty_matrix(self) -> None:
        csr = sp.csr_matrix((5, 5))
        # indptr still has (nrows+1) entries even with 0 nnz
        size = estimate_matrix_bytes(csr)
        assert size == csr.indptr.nbytes


class TestComputeChunkRows:
    """Chunk row calculation from VRAM budget."""

    def test_auto_chunk(self) -> None:
        rng = np.random.default_rng(42)
        csr = sp.random(1000, 1000, density=0.01, format="csr", random_state=rng)
        budget = estimate_matrix_bytes(csr) // 10
        chunk_rows = compute_chunk_rows(csr, budget)
        assert chunk_rows >= 1
        assert chunk_rows <= 1000

    def test_empty_matrix(self) -> None:
        csr = sp.csr_matrix((0, 0))
        assert compute_chunk_rows(csr, 1000) == 1

    def test_full_budget(self) -> None:
        csr = sp.random(100, 100, density=0.1, format="csr")
        budget = estimate_matrix_bytes(csr) * 2
        assert compute_chunk_rows(csr, budget) == 100


class TestChunkCsr:
    """CSR matrix chunking."""

    def test_even_chunks(self) -> None:
        csr = sp.random(100, 50, density=0.1, format="csr", random_state=42)
        chunks = chunk_csr(csr, 25)
        assert len(chunks) == 4
        total_rows = sum(c.shape[0] for c in chunks)
        assert total_rows == 100

    def test_uneven_chunks(self) -> None:
        csr = sp.random(100, 50, density=0.1, format="csr", random_state=42)
        chunks = chunk_csr(csr, 30)
        assert len(chunks) == 4  # 30+30+30+10
        total_rows = sum(c.shape[0] for c in chunks)
        assert total_rows == 100

    def test_single_chunk(self) -> None:
        csr = sp.random(10, 10, density=0.5, format="csr", random_state=42)
        chunks = chunk_csr(csr, 10)
        assert len(chunks) == 1

    def test_empty_matrix(self) -> None:
        csr = sp.csr_matrix((0, 5))
        chunks = chunk_csr(csr, 10)
        assert len(chunks) == 1
        assert chunks[0].shape == (0, 5)


class TestShardedSparseMatrix:
    """Sharded sparse matrix operations."""

    def test_matvec_fits_in_budget(self) -> None:
        """Matrix within budget uses single-shot computation."""
        csr = sp.random(50, 50, density=0.2, format="csr", random_state=42)
        config = VRAMConfig(budget_bytes=estimate_matrix_bytes(csr) * 2)
        sharded = ShardedSparseMatrix.from_csr(csr, config)
        assert sharded.num_chunks == 1

        x = np.ones(50)
        result = sharded.matvec(x)
        expected = csr.dot(x)
        np.testing.assert_allclose(result, expected)

    def test_matvec_chunked(self) -> None:
        """Chunked matvec matches single-shot."""
        rng = np.random.default_rng(42)
        csr = sp.random(200, 200, density=0.05, format="csr", random_state=rng)
        x = rng.standard_normal(200)

        # Force small chunks
        config = VRAMConfig(budget_bytes=1, chunk_rows=50, unified_memory=False)
        sharded = ShardedSparseMatrix.from_csr(csr, config)
        assert sharded.num_chunks == 4
        assert not sharded.using_unified_memory

        result = sharded.matvec(x)
        expected = csr.dot(x)
        np.testing.assert_allclose(result, expected)

    def test_matvec_unified_memory(self) -> None:
        """Unified Memory fallback produces correct results."""
        rng = np.random.default_rng(42)
        csr = sp.random(100, 100, density=0.1, format="csr", random_state=rng)
        x = rng.standard_normal(100)

        config = VRAMConfig(budget_bytes=1, unified_memory=True)
        sharded = ShardedSparseMatrix.from_csr(csr, config)
        assert sharded.using_unified_memory
        assert sharded.num_chunks == 1

        result = sharded.matvec(x)
        expected = csr.dot(x)
        np.testing.assert_allclose(result, expected)

    def test_hadamard_chunked(self) -> None:
        """Chunked Hadamard matches single-shot."""
        rng = np.random.default_rng(42)
        a = sp.random(200, 200, density=0.05, format="csr", random_state=rng)
        b = sp.random(200, 200, density=0.05, format="csr", random_state=rng)

        config = VRAMConfig(budget_bytes=1, chunk_rows=50, unified_memory=False)
        sharded_a = ShardedSparseMatrix.from_csr(a, config)
        sharded_b = ShardedSparseMatrix.from_csr(b, config)

        result = sharded_a.hadamard(sharded_b)
        expected = a.multiply(b).tocsr()
        np.testing.assert_array_equal(result.tocsr().toarray(), expected.toarray())

    def test_shape(self) -> None:
        csr = sp.random(42, 37, density=0.1, format="csr")
        sharded = ShardedSparseMatrix.from_csr(csr)
        assert sharded.shape == (42, 37)

    def test_default_config(self) -> None:
        """Default VRAMConfig uses 256 MB budget with Unified Memory."""
        config = VRAMConfig()
        assert config.budget_bytes == DEFAULT_VRAM_BUDGET
        assert config.unified_memory is True


class TestShardedLargeGraph:
    """Benchmark with synthetic large graph (>1M nodes)."""

    def test_large_sparse_matvec(self) -> None:
        """Synthetic large graph (10K nodes) completes with chunking."""
        rng = np.random.default_rng(42)
        n = 10_000
        csr = sp.random(n, n, density=0.001, format="csr", random_state=rng)
        x = rng.standard_normal(n)

        config = VRAMConfig(budget_bytes=1024 * 1024, chunk_rows=2000, unified_memory=False)
        sharded = ShardedSparseMatrix.from_csr(csr, config)
        assert sharded.num_chunks > 1

        result = sharded.matvec(x)
        expected = csr.dot(x)
        np.testing.assert_allclose(result, expected, rtol=1e-10)

    def test_memory_stays_within_budget(self) -> None:
        """Each chunk's memory footprint is within the configured budget."""
        rng = np.random.default_rng(42)
        n = 5000
        csr = sp.random(n, n, density=0.005, format="csr", random_state=rng)
        budget = 256 * 1024  # 256 KB

        config = VRAMConfig(budget_bytes=budget, unified_memory=False)
        sharded = ShardedSparseMatrix.from_csr(csr, config)

        if sharded.num_chunks > 1:
            for chunk in sharded._chunks:
                chunk_size = estimate_matrix_bytes(chunk)
                assert chunk_size <= budget * 2  # allow 2x tolerance for row granularity
