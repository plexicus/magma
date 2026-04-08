"""Python bridge for Mojo CSR operations.

Provides a Python interface to the Mojo CSR implementation via subprocess.
Data is exchanged via JSON for interoperability.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

_MOJO_BIN = shutil.which("mojo") or str(Path.home() / ".pixi" / "bin" / "mojo")
_MOJO_CSR = Path(__file__).parent / "mojo" / "csr.mojo"

_PREAMBLE = """from std.python import Python

fn main() raises:
    var json_mod = Python.import_module("json")
    var builtins = Python.import_module("builtins")
    var range_fn = builtins.range
    var len_fn = builtins.len
"""


def mojo_available() -> bool:
    """Check if Mojo is installed and the CSR module exists."""
    return Path(_MOJO_BIN).exists() and _MOJO_CSR.exists()


class MojoCSR:
    """Python wrapper around Mojo CSR operations.

    Loads CSR data from Parquet and runs matvec, hadamard, and
    boolean_mask operations via the Mojo binary.
    """

    def __init__(self, row_ptr: list[int], col_idx: list[int], nrows: int, ncols: int):
        self.row_ptr = row_ptr
        self.col_idx = col_idx
        self.nrows = nrows
        self.ncols = ncols
        self._nnz = len(col_idx)

    @classmethod
    def from_csr_parquet(cls, csr_path: Path, edge_type: str) -> MojoCSR:
        """Load a CSR matrix from a Parquet CSR index table.

        Args:
            csr_path: Path to the csr.parquet file.
            edge_type: Edge type to load (e.g., "REACHING_DEF").

        Returns:
            MojoCSR instance.
        """
        import pyarrow.parquet as pq

        table = pq.read_table(str(csr_path))
        edge_types = table.column("edge_type").to_pylist()
        idx = edge_types.index(edge_type) if edge_type in edge_types else None
        if idx is None:
            return cls(row_ptr=[0], col_idx=[], nrows=0, ncols=0)

        row_ptr = json.loads(table.column("row_ptr")[idx].as_py())
        col_idx = json.loads(table.column("col_idx")[idx].as_py())
        nrows = len(row_ptr) - 1 if row_ptr else 0
        ncols = max(col_idx) + 1 if col_idx else 0

        return cls(row_ptr=row_ptr, col_idx=col_idx, nrows=nrows, ncols=ncols)

    def matvec(self, x: list[float]) -> list[float]:
        """Sparse matrix-vector multiply using Mojo.

        Args:
            x: Dense vector of length ncols.

        Returns:
            Dense result vector of length nrows.
        """
        if self._nnz == 0:
            return [0.0] * self.nrows

        rp = json.dumps(self.row_ptr)
        ci = json.dumps(self.col_idx)
        xv = json.dumps(x)
        n = self.nrows

        script = f"""{_PREAMBLE}
    var rp = json_mod.loads('{rp}')
    var ci = json_mod.loads('{ci}')
    var xv = json_mod.loads('{xv}')

    var result = Python.list()
    var zero = builtins.float(0)
    for i in range_fn({n}):
        var acc = zero + 0
        for k in range_fn(rp[i], rp[i + 1]):
            acc = acc + xv[ci[k]]
        result.append(acc)
    print(json_mod.dumps(result))
"""
        return json.loads(self._run_mojo_script(script))

    def hadamard(self, other: MojoCSR) -> MojoCSR:
        """Hadamard (element-wise) product with another CSR.

        Args:
            other: Another MojoCSR with the same shape.

        Returns:
            New MojoCSR with the Hadamard product.
        """
        if self._nnz == 0 or other._nnz == 0:
            return MojoCSR(
                row_ptr=[0] * (self.nrows + 1),
                col_idx=[],
                nrows=self.nrows,
                ncols=self.ncols,
            )

        a_rp = json.dumps(self.row_ptr)
        a_ci = json.dumps(self.col_idx)
        b_rp = json.dumps(other.row_ptr)
        b_ci = json.dumps(other.col_idx)
        n = self.nrows

        script = f"""{_PREAMBLE}
    var a_rp = json_mod.loads('{a_rp}')
    var a_ci = json_mod.loads('{a_ci}')
    var b_rp = json_mod.loads('{b_rp}')
    var b_ci = json_mod.loads('{b_ci}')

    var out_rp = Python.list()
    var out_ci = Python.list()
    out_rp.append(0)

    for i in range_fn({n}):
        var pa = a_rp[i]
        var a_e = a_rp[i + 1]
        var pb = b_rp[i]
        var b_e = b_rp[i + 1]
        while pa < a_e and pb < b_e:
            var ac = a_ci[pa]
            var bc = b_ci[pb]
            if ac == bc:
                out_ci.append(ac)
                pa = pa + 1
                pb = pb + 1
            elif ac < bc:
                pa = pa + 1
            else:
                pb = pb + 1
        out_rp.append(len_fn(out_ci))

    var result = Python.dict()
    result["row_ptr"] = out_rp
    result["col_idx"] = out_ci
    result["nrows"] = {n}
    result["ncols"] = {self.ncols}
    print(json_mod.dumps(result))
"""
        data = json.loads(self._run_mojo_script(script))
        return MojoCSR(
            row_ptr=data["row_ptr"],
            col_idx=data["col_idx"],
            nrows=data["nrows"],
            ncols=data["ncols"],
        )

    def matvec_simd(self, x: list[float]) -> list[float]:
        """SIMD-accelerated sparse matrix-vector multiply using Mojo.

        Uses native Mojo SIMD[DType.float64, 4] for the inner dot-product
        accumulation, processing 4 column indices at a time.

        Args:
            x: Dense vector of length ncols.

        Returns:
            Dense result vector of length nrows.
        """
        if self._nnz == 0:
            return [0.0] * self.nrows
        if self._nnz < 4:
            # SIMD overhead not worth it for tiny matrices
            return self.matvec(x)

        rp = json.dumps(self.row_ptr)
        ci = json.dumps(self.col_idx)
        xv = json.dumps(x)
        n = self.nrows

        # Build native Mojo List append calls from JSON data.
        # This avoids PythonObject→Mojo conversion by generating
        # direct Mojo code with the data baked in.
        rp_appends = "\n    ".join(
            f"rp.append({v})" for v in self.row_ptr
        )
        ci_appends = "\n    ".join(
            f"ci.append({v})" for v in self.col_idx
        )
        xv_appends = "\n    ".join(
            f"xv.append({v})" for v in x
        )

        script = f"""from std.python import Python

fn main() raises:
    var json_mod = Python.import_module("json")

    var rp = List[Int]()
    {rp_appends}

    var ci = List[Int]()
    {ci_appends}

    var xv = List[Float64]()
    {xv_appends}

    var nrows = {n}
    var simd_width: Int = 4
    var result = Python.list()

    for row in range(nrows):
        var start = rp[row]
        var end = rp[row + 1]
        var acc_vec = SIMD[DType.float64, 4](0.0, 0.0, 0.0, 0.0)

        var k = start
        while k + simd_width <= end:
            var v = SIMD[DType.float64, 4](xv[ci[k]], xv[ci[k + 1]], xv[ci[k + 2]], xv[ci[k + 3]])
            acc_vec = acc_vec + v
            k = k + simd_width

        var acc = acc_vec.reduce_add()
        while k < end:
            acc = acc + xv[ci[k]]
            k = k + 1
        result.append(acc)

    print(json_mod.dumps(result))
"""
        return json.loads(self._run_mojo_script(script))

    def boolean_mask(self, mask: MojoCSR) -> MojoCSR:
        """Apply boolean mask (same as hadamard for boolean matrices)."""
        return self.hadamard(mask)

    def _run_mojo_script(self, script: str) -> str:
        """Write script to temp file, run Mojo, return stdout."""
        with tempfile.NamedTemporaryFile(suffix=".mojo", mode="w", delete=False) as f:
            f.write(script)
            tmp_path = f.name

        try:
            result = subprocess.run(
                [_MOJO_BIN, "run", tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Mojo execution failed: {result.stderr}")
            return result.stdout.strip()
        finally:
            Path(tmp_path).unlink(missing_ok=True)
