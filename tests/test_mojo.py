"""Tests for Mojo integration (US-106 through US-110).

Verifies that Mojo is installed, compiles, can interop with Python,
and that Mojo CSR matches scipy CSR behavior.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

MOJO_DIR = Path(__file__).parent.parent / "src" / "magma" / "mojo"
GOLDEN_DIR = Path(__file__).parent / "golden"

# Mojo binary — look on PATH first, then pixi global install
_MOJO_BIN = shutil.which("mojo") or str(Path.home() / ".pixi" / "bin" / "mojo")


def _mojo_available() -> bool:
    """Check if Mojo is installed and runnable."""
    if not Path(_MOJO_BIN).exists():
        return False
    result = subprocess.run(
        [_MOJO_BIN, "--version"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _run_mojo(path: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a Mojo file and return the result."""
    return subprocess.run(
        [_MOJO_BIN, "run", str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _skip_no_mojo():
    """Skip test if Mojo not available."""
    return pytest.mark.skipif(not _mojo_available(), reason="Mojo not installed")


# ── US-106: Mojo environment setup ──────────────────────────────────────────

@_skip_no_mojo()
class TestMojoSetup:
    """US-106: Mojo installed, hello-world compiles, Python interop works."""

    def test_mojo_version(self) -> None:
        """Mojo installed and 'mojo --version' prints version."""
        result = subprocess.run(
            [_MOJO_BIN, "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Mojo" in result.stdout

    def test_mojo_dir_exists(self) -> None:
        """src/magma/mojo/ directory exists."""
        assert MOJO_DIR.is_dir()

    def test_init_mojo_exists(self) -> None:
        """__init__.mojo exists in the mojo package."""
        init_path = MOJO_DIR / "__init__.mojo"
        assert init_path.exists()

    def test_hello_world_compiles(self) -> None:
        """Hello-world Mojo file compiles and runs."""
        hello_path = MOJO_DIR / "hello.mojo"
        assert hello_path.exists()
        result = _run_mojo(hello_path)
        assert result.returncode == 0, f"Mojo hello-world failed: {result.stderr}"
        assert "Hello from Magma Mojo" in result.stdout

    def test_python_interop(self) -> None:
        """Mojo can import Python modules."""
        test_file = Path("/tmp/magma_mojo_pytest_interop.mojo")
        test_file.write_text(
            'from std.python import Python\n'
            'fn main() raises:\n'
            '    var sys = Python.import_module("sys")\n'
            '    print("python_ok")\n'
        )
        result = _run_mojo(test_file)
        assert result.returncode == 0, f"Python interop failed: {result.stderr}"
        assert "python_ok" in result.stdout


# ── US-107: Mojo CSR implementation ─────────────────────────────────────────

def _scipy_csr_from_lists(row_ptr: list[int], col_idx: list[int], nrows: int, ncols: int):
    """Build scipy CSR from explicit row_ptr/col_idx arrays."""
    return sparse.csr_matrix(
        (np.ones(len(col_idx), dtype=np.float64), np.array(col_idx), np.array(row_ptr)),
        shape=(nrows, ncols),
    )


@_skip_no_mojo()
class TestMojoCSR:
    """US-107: Mojo CSR matches scipy CSR behavior."""

    def test_csr_module_exists(self) -> None:
        """src/magma/mojo/csr.mojo exists."""
        assert (MOJO_DIR / "csr.mojo").exists()

    def test_mojo_bridge_available(self) -> None:
        """mojo_bridge module is importable and mojo_available returns True."""
        from magma.mojo_bridge import MojoCSR, mojo_available
        assert mojo_available()

    def test_matvec_identity(self) -> None:
        """Mojo CSR matvec on identity matrix matches scipy."""
        from magma.mojo_bridge import MojoCSR

        n = 5
        row_ptr = list(range(n + 1))
        col_idx = list(range(n))
        x = [float(i + 1) for i in range(n)]

        mojo_result = MojoCSR(row_ptr, col_idx, n, n).matvec(x)
        scipy_result = _scipy_csr_from_lists(row_ptr, col_idx, n, n).dot(np.array(x))

        np.testing.assert_allclose(mojo_result, scipy_result.tolist(), rtol=1e-10)

    def test_matvec_sparse(self) -> None:
        """Mojo CSR matvec on sparse matrix matches scipy."""
        from magma.mojo_bridge import MojoCSR

        # 4x4 matrix with known structure
        row_ptr = [0, 2, 3, 5, 7]
        col_idx = [0, 2, 1, 1, 3, 0, 2]
        x = [1.0, 2.0, 3.0, 4.0]

        mojo_result = MojoCSR(row_ptr, col_idx, 4, 4).matvec(x)
        scipy_result = _scipy_csr_from_lists(row_ptr, col_idx, 4, 4).dot(np.array(x))

        np.testing.assert_allclose(mojo_result, scipy_result.tolist(), rtol=1e-10)

    def test_matvec_random(self) -> None:
        """Mojo CSR matvec matches scipy on random sparse boolean matrices."""
        from magma.mojo_bridge import MojoCSR

        rng = np.random.default_rng(42)
        for _ in range(5):
            nrows, ncols = int(rng.integers(5, 20)), int(rng.integers(5, 20))
            density = float(rng.uniform(0.1, 0.4))
            # Use boolean mask to get 0/1 entries (MojoCSR treats all entries as 1)
            scipy_csr = sparse.random(nrows, ncols, density=density, format="csr", dtype=np.float64, random_state=rng)
            scipy_csr.data = np.ones_like(scipy_csr.data)  # all entries = 1

            row_ptr = scipy_csr.indptr.tolist()
            col_idx = scipy_csr.indices.tolist()
            x = rng.standard_normal(ncols).tolist()

            mojo_result = MojoCSR(row_ptr, col_idx, nrows, ncols).matvec(x)
            scipy_result = scipy_csr.dot(np.array(x))

            np.testing.assert_allclose(mojo_result, scipy_result.tolist(), rtol=1e-10)

    def test_hadamard_identity(self) -> None:
        """Mojo hadamard of I*I = I."""
        from magma.mojo_bridge import MojoCSR

        n = 4
        row_ptr = list(range(n + 1))
        col_idx = list(range(n))
        csr = MojoCSR(row_ptr, col_idx, n, n)

        result = csr.hadamard(csr)
        assert result.row_ptr == row_ptr
        assert result.col_idx == col_idx
        assert result._nnz == n

    def test_hadamard_matches_scipy(self) -> None:
        """Mojo hadamard matches scipy element-wise multiply."""
        from magma.mojo_bridge import MojoCSR

        row_ptr = [0, 2, 4, 6]
        col_idx = [0, 1, 1, 2, 0, 2]
        a_scipy = _scipy_csr_from_lists(row_ptr, col_idx, 3, 3)

        b_ptr = [0, 1, 3, 5]
        b_idx = [0, 1, 2, 0, 2]
        b_scipy = _scipy_csr_from_lists(b_ptr, b_idx, 3, 3)

        expected = a_scipy.multiply(b_scipy).tocsr()

        mojo_a = MojoCSR(row_ptr, col_idx, 3, 3)
        mojo_b = MojoCSR(b_ptr, b_idx, 3, 3)
        result = mojo_a.hadamard(mojo_b)

        assert result.row_ptr == expected.indptr.tolist()
        assert result.col_idx == expected.indices.tolist()

    def test_boolean_mask(self) -> None:
        """boolean_mask is equivalent to hadamard."""
        from magma.mojo_bridge import MojoCSR

        a = MojoCSR([0, 2, 4], [0, 1, 0, 1], 2, 2)
        mask = MojoCSR([0, 1, 3], [0, 0, 1], 2, 2)

        hadamard_result = a.hadamard(mask)
        mask_result = a.boolean_mask(mask)

        assert mask_result.row_ptr == hadamard_result.row_ptr
        assert mask_result.col_idx == hadamard_result.col_idx

    def test_from_csr_parquet(self) -> None:
        """MojoCSR loads correctly from golden fixture Parquet."""
        from magma.mojo_bridge import MojoCSR

        pq_path = GOLDEN_DIR / "uaf_simple.c.parquet" / "csr.parquet"
        if not pq_path.exists():
            pytest.skip("Golden parquet fixture not available")

        csr = MojoCSR.from_csr_parquet(pq_path, "REACHING_DEF")
        assert csr.nrows > 0
        assert csr._nnz > 0

        # Verify matvec produces correct-size output
        x = [1.0] * csr.ncols
        y = csr.matvec(x)
        assert len(y) == csr.nrows

    def test_matvec_empty(self) -> None:
        """Mojo CSR matvec on empty matrix returns zeros."""
        from magma.mojo_bridge import MojoCSR

        csr = MojoCSR(row_ptr=[0], col_idx=[], nrows=3, ncols=3)
        result = csr.matvec([1.0, 2.0, 3.0])
        assert result == [0.0, 0.0, 0.0]

    def test_csr_mojo_compiles(self) -> None:
        """csr.mojo compiles and runs its self-test."""
        result = _run_mojo(MOJO_DIR / "csr.mojo")
        assert result.returncode == 0, f"csr.mojo failed: {result.stderr}"
        assert "CSR(" in result.stdout
        assert "matvec: 1.0 2.0 3.0" in result.stdout


# ── US-108: SIMD vectorization ──────────────────────────────────────────────

@_skip_no_mojo()
class TestMojoSIMD:
    """US-108: SIMD-accelerated matvec matches scalar results exactly."""

    def test_simd_matvec_identity(self) -> None:
        """SIMD matvec on identity matches scalar."""
        from magma.mojo_bridge import MojoCSR

        n = 5
        row_ptr = list(range(n + 1))
        col_idx = list(range(n))
        x = [float(i + 1) for i in range(n)]
        csr = MojoCSR(row_ptr, col_idx, n, n)

        scalar = csr.matvec(x)
        simd = csr.matvec_simd(x)
        assert scalar == simd

    def test_simd_matvec_sparse(self) -> None:
        """SIMD matvec on sparse matrix matches scalar."""
        from magma.mojo_bridge import MojoCSR

        row_ptr = [0, 2, 3, 5, 7]
        col_idx = [0, 2, 1, 1, 3, 0, 2]
        x = [1.0, 2.0, 3.0, 4.0]
        csr = MojoCSR(row_ptr, col_idx, 4, 4)

        scalar = csr.matvec(x)
        simd = csr.matvec_simd(x)
        assert scalar == simd

    def test_simd_matvec_large_rows(self) -> None:
        """SIMD matvec on rows with 4+ entries (exercises SIMD inner loop)."""
        from magma.mojo_bridge import MojoCSR

        # Two rows, each with 6 entries (SIMD processes 4 + scalar tail 2)
        row_ptr = [0, 6, 12]
        col_idx = [0, 1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5]
        x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
        csr = MojoCSR(row_ptr, col_idx, 2, 6)

        scalar = csr.matvec(x)
        simd = csr.matvec_simd(x)
        assert scalar == simd

    def test_simd_matvec_random(self) -> None:
        """SIMD matvec matches scalar on random sparse matrices."""
        from magma.mojo_bridge import MojoCSR

        rng = np.random.default_rng(42)
        for _ in range(5):
            nrows, ncols = int(rng.integers(5, 20)), int(rng.integers(5, 20))
            density = float(rng.uniform(0.1, 0.4))
            scipy_csr = sparse.random(nrows, ncols, density=density, format="csr", dtype=np.float64, random_state=rng)
            scipy_csr.data = np.ones_like(scipy_csr.data)

            row_ptr = scipy_csr.indptr.tolist()
            col_idx = scipy_csr.indices.tolist()
            x = rng.standard_normal(ncols).tolist()

            csr = MojoCSR(row_ptr, col_idx, nrows, ncols)
            scalar = csr.matvec(x)
            simd = csr.matvec_simd(x)
            np.testing.assert_allclose(scalar, simd, rtol=1e-10)

    def test_simd_matvec_real_cpg(self) -> None:
        """SIMD matvec matches scalar on real Joern CPG data."""
        from magma.mojo_bridge import MojoCSR

        pq_path = GOLDEN_DIR / "uaf_simple.c.parquet" / "csr.parquet"
        if not pq_path.exists():
            pytest.skip("Golden parquet fixture not available")

        csr = MojoCSR.from_csr_parquet(pq_path, "REACHING_DEF")
        x = [1.0] * csr.ncols

        scalar = csr.matvec(x)
        simd = csr.matvec_simd(x)
        assert scalar == simd

    def test_simd_matvec_matches_scipy(self) -> None:
        """SIMD matvec matches scipy on random matrices."""
        from magma.mojo_bridge import MojoCSR

        rng = np.random.default_rng(123)
        nrows, ncols = 10, 15
        scipy_csr = sparse.random(nrows, ncols, density=0.3, format="csr", dtype=np.float64, random_state=rng)
        scipy_csr.data = np.ones_like(scipy_csr.data)

        row_ptr = scipy_csr.indptr.tolist()
        col_idx = scipy_csr.indices.tolist()
        x = rng.standard_normal(ncols).tolist()

        csr = MojoCSR(row_ptr, col_idx, nrows, ncols)
        simd = csr.matvec_simd(x)
        expected = scipy_csr.dot(np.array(x)).tolist()
        np.testing.assert_allclose(simd, expected, rtol=1e-10)
