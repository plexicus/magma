# Getting Started

## Prerequisites

- Python 3.10+
- [Joern](https://joern.io/) (Java-based code analysis platform, requires JVM 11+)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify installation:

```bash
python -c "import magma; print(magma.__version__)"
magma --version
```

## Basic Usage

### Scan a C file for UAF

```bash
magma scan path/to/file.c
```

Output shows findings with file path, line number, and description:

```
Magma UAF Detection Results
==============================

[1] Use-After-Free
    File: test.c
    Line: 6
    Pointer freed at line 5 (free(ptr)) then dereferenced at line 6 (*ptr)

Found 1 vulnerability.
```

Exit codes: `0` = clean, `1` = vulnerabilities found, `2` = error.

### JSON output

```bash
magma scan --json-output path/to/file.c
```

```json
[
  {
    "vuln_type": "Use-After-Free",
    "file": "test.c",
    "line": 6,
    "description": "Pointer freed at line 5 (free(ptr)) then dereferenced at line 6 (*ptr)"
  }
]
```

### Export CPG only

```bash
magma parse path/to/file.c
# Produces path/to/file.cpg.dot
```

### Tune detection sensitivity

```bash
# Increase max hops for longer data dependency chains
magma scan --max-hops 10 path/to/file.c
```

## Example: Vulnerable Code

```c
#include <stdlib.h>

void example() {
    int *ptr = malloc(sizeof(int));
    free(ptr);      // line 5 — free
    *ptr = 42;      // line 6 — use after free
}
```

```bash
$ magma scan example.c
[1] Use-After-Free
    File: example.c
    Line: 6
    Pointer freed at line 5 (free(ptr)) then dereferenced at line 6 (*ptr)
```

## Example: Safe Code (null assignment)

```c
#include <stdlib.h>

void safe() {
    int *ptr = malloc(sizeof(int));
    free(ptr);
    ptr = NULL;     // null assignment — suppresses UAF finding
    // *ptr would segfault but is not detected as UAF
}
```

```bash
$ magma scan safe.c
No vulnerabilities found.
```

## Project Structure

```
magma/
├── src/magma/
│   ├── __init__.py      # Version
│   ├── types.py         # CPGNode, CPGEdge, Finding
│   ├── ingest.py        # Joern CLI + DOT parser
│   ├── graph.py         # Sparse matrix graph
│   ├── query.py         # UAF detection engine
│   └── cli.py           # Click CLI
├── tests/
│   ├── corpus/          # Test C files
│   ├── test_ingest.py
│   ├── test_graph.py
│   ├── test_query.py
│   ├── test_cli.py
│   └── test_e2e.py
├── doc/                 # Technical documentation
├── pyproject.toml
├── README.md
└── ROADMAP.md
```
