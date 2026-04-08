# Joern DOT Format

## Overview

Joern exports Code Property Graphs in Graphviz DOT format. Each export produces a `.dot` file containing labeled nodes and typed edges.

## Node Format

```dot
"30064771076" [label="CALL" CODE="free(ptr)" LINE_NUMBER="5" FILENAME="test.c" METHOD_FULL_NAME="free"];
```

**Syntax:** `"<node_id>" [key="value" ...];`

**Attribute mapping:**

| DOT attribute | CPGNode field | Notes |
|---------------|---------------|-------|
| `label` | `type` | Node type: CALL, IDENTIFIER, BLOCK, etc. |
| `CODE` | `label` | Source code text |
| `NAME` | `label` | Fallback if CODE absent |
| `LINE_NUMBER` | `line_number` | Parsed to int |
| `FILENAME` | `file` | Source file path |
| Everything else | `properties` | METHOD_FULL_NAME, TYPE_FULL_NAME, etc. |

## Edge Format

```dot
"25769803776" -> "30064771076" [label="AST"];
```

**Syntax:** `"<src_id>" -> "<tgt_id>" [key="value" ...];`

**Edge types in Joern CPG:**

| Edge type | Meaning |
|-----------|---------|
| `AST` | Abstract syntax tree parent→child |
| `CFG` | Control flow graph |
| `REACHING_DEF` | Data dependency (reaching definition) |
| `CDG` | Control dependency |
| `DDG` | Data dependency graph |
| `EVAL_TYPE` | Type evaluation |
| `REF` | Reference to declaration |

## Parsing Strategy

The DOT parser (`ingest.py`) uses three regex patterns:

```
_NODE_RE:  "(?P<id>\d+)" \[(?P<attrs>[^\]]+)\];
_EDGE_RE:  "(?P<src>\d+)" -> "(?P<tgt>\d+)" \[(?P<attrs>[^\]]+)\];
_ATTR_RE:  (?P<key>\w+)="(?P<value>[^"]*)"
```

**Edge-first matching:** Edge lines are matched before node lines because edge target lines (e.g., `"68719476738"`) would otherwise match `_NODE_RE`. The `->` token in `_EDGE_RE` makes it more specific.

**Line-by-line parsing:** The parser iterates lines and classifies each as edge, node, or irrelevant. This is simpler and more robust than full DOT grammar parsing for the structured output Joern produces.

## Joern CLI Commands

```bash
# Parse C file into CPG (creates cpg.bin in current directory)
joern-parse file.c

# Export CPG as DOT (output dir must NOT exist)
joern-export --repr all --format dot -o output_dir/
```

**Key constraints:**
- `joern-export` fails if the output directory already exists
- JVM warnings go to stderr even on success — only check `returncode`
- Multiple DOT files may be produced; Magma uses the first one
