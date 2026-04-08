"""Compressed Sparse Row (CSR) matrix implementation in Mojo.

Provides sparse matrix operations for CPG reachability analysis.
Data is exchanged with Python via JSON strings.

CSR format:
    - row_ptr[i] to row_ptr[i+1] gives the range of col_idx entries for row i
    - col_idx[k] is the column index of the k-th nonzero entry
"""

struct CSR:
    """Compressed Sparse Row sparse matrix."""

    var _row_ptr: List[Int]
    var _col_idx: List[Int]
    var _nrows: Int
    var _ncols: Int

    fn __init__(out self, nrows: Int, ncols: Int):
        self._row_ptr = List[Int]()
        self._row_ptr.append(0)
        self._col_idx = List[Int]()
        self._nrows = nrows
        self._ncols = ncols

    fn nrows(self) -> Int:
        return self._nrows

    fn ncols(self) -> Int:
        return self._ncols

    fn nnz(self) -> Int:
        return len(self._col_idx)

    fn row_ptr_at(self, i: Int) -> Int:
        return self._row_ptr[i]

    fn col_idx_at(self, i: Int) -> Int:
        return self._col_idx[i]

    fn row_degree(self, row: Int) -> Int:
        return self._row_ptr[row + 1] - self._row_ptr[row]

    fn add_row(mut self, cols: List[Int]):
        """Add a row of column indices."""
        for i in range(len(cols)):
            self._col_idx.append(cols[i])
        self._row_ptr.append(len(self._col_idx))

    fn matvec(self, x: List[Float64], mut y: List[Float64]):
        """Sparse matrix-vector multiply: y = self @ x (writes into y)."""
        for i in range(self._nrows):
            var acc: Float64 = 0.0
            var start = self._row_ptr[i]
            var end = self._row_ptr[i + 1]
            for k in range(start, end):
                acc += x[self._col_idx[k]]
            y.append(acc)

    fn hadamard(mut result: CSR, a: CSR, b: CSR):
        """Element-wise (Hadamard) product: result = a * b (entry-wise)."""
        for i in range(a._nrows):
            var row_cols = List[Int]()
            var a_start = a._row_ptr[i]
            var a_end = a._row_ptr[i + 1]
            var b_start = b._row_ptr[i]
            var b_end = b._row_ptr[i + 1]

            # Two-pointer intersection of sorted column lists
            var pa = a_start
            var pb = b_start
            while pa < a_end and pb < b_end:
                if a._col_idx[pa] == b._col_idx[pb]:
                    row_cols.append(a._col_idx[pa])
                    pa += 1
                    pb += 1
                elif a._col_idx[pa] < b._col_idx[pb]:
                    pa += 1
                else:
                    pb += 1
            result.add_row(row_cols^)

    fn get_row_at(self, row: Int, mut col_out: List[Int]) -> Int:
        """Get column indices for row, return count."""
        var count: Int = 0
        var start = self._row_ptr[row]
        var end = self._row_ptr[row + 1]
        for k in range(start, end):
            col_out.append(self._col_idx[k])
            count += 1
        return count

    fn to_string(self) -> String:
        var s = String("CSR(") + String(self._nrows) + String("x") + String(self._ncols)
        s += String(", nnz=") + String(self.nnz()) + String(")")
        return s


fn main():
    """Quick self-test of CSR operations."""
    # Build 3x3 identity matrix
    var csr = CSR(3, 3)
    var r0 = List[Int]()
    r0.append(0)
    csr.add_row(r0^)
    var r1 = List[Int]()
    r1.append(1)
    csr.add_row(r1^)
    var r2 = List[Int]()
    r2.append(2)
    csr.add_row(r2^)
    print(csr.to_string())
    print("nnz:", csr.nnz())

    # Test matvec: I @ [1,2,3] = [1,2,3]
    var x = List[Float64]()
    x.append(1.0)
    x.append(2.0)
    x.append(3.0)
    var y = List[Float64]()
    csr.matvec(x, y)
    print("matvec:", y[0], y[1], y[2])

    # Test get_row
    var cols = List[Int]()
    var n = csr.get_row_at(1, cols)
    print("row 1:", n, "cols:", cols[0])

    # Test hadamard: I * I = I
    var result = CSR(3, 3)
    CSR.hadamard(result, csr, csr)
    print("hadamard nnz:", result.nnz())
