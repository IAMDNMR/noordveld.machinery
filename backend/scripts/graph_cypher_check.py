"""Static check of the generated Cypher (no database needed, none contacted).

1. Structure: every statement ends with ';', brackets balance outside string literals, map keys are plain identifiers,
   no CREATE of data (only CREATE CONSTRAINT), no DELETE / DETACH / REMOVE / DROP.
2. Idempotency: parses every UNWIND literal back into rows and replays the MERGE semantics twice in memory
   (nodes keyed by label + canonical id, relationships by type + rel_id). The second pass must create nothing.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from graph_audit_lib import CYPHER

files = sorted(CYPHER.glob("[0-2]*.cypher"))
problems: list[str] = []
statements = 0


def strip_strings(text: str) -> str:
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)


def cypher_list_to_python(lit: str):
    # map keys are bare identifiers; quote them so the literal parses as Python
    py = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', lit)
    py = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", re.sub(r"\bnull\b", "None", py)))
    return ast.literal_eval(py)


nodes: dict[tuple[str, str], dict] = {}
rels: dict[tuple[str, str], tuple] = {}
created = {1: [0, 0], 2: [0, 0]}

for run in (1, 2):
    for f in files:
        text = f.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
        for stmt in [s.strip() for s in body.split(";\n") if s.strip()]:
            if run == 1:
                statements += 1
                bare = strip_strings(stmt)
                for o, c in ("()", "[]", "{}"):
                    if bare.count(o) != bare.count(c):
                        problems.append(f"{f.name}: unbalanced {o}{c}")
                if re.search(r"\b(DELETE|DETACH|REMOVE|DROP)\b", bare) or (re.search(r"\bCREATE\b", bare) and "CREATE CONSTRAINT" not in bare):
                    problems.append(f"{f.name}: destructive or non-idempotent clause")
            if stmt.startswith("CREATE CONSTRAINT"):
                continue
            m = re.match(r"UNWIND (\[.*\]) AS row\s*\n(.*)", stmt, re.S)
            if not m:
                problems.append(f"{f.name}: unexpected statement shape")
                continue
            rows = cypher_list_to_python(m.group(1))
            tail = m.group(2)
            nm = re.match(r"MERGE \(n:(\w+) \{(\w+): row\.(\w+)\}\)", tail)
            if nm:
                label, key = nm.group(1), nm.group(2)
                for r in rows:
                    k = (label, r[key])
                    if k not in nodes:
                        nodes[k] = r
                        created[run][0] += 1
                continue
            rm = re.match(r"MATCH \(a:(\w+) \{(\w+): row\.from\}\)\s*MATCH \(b:(\w+) \{(\w+): row\.to\}\)\s*MERGE \(a\)-\[r:(\w+) \{rel_id: row\.props\.rel_id\}\]->\(b\)", tail)
            if not rm:
                problems.append(f"{f.name}: unexpected MERGE shape")
                continue
            fl, _, tl, _, t = rm.groups()
            for r in rows:
                if (fl, r["from"]) not in nodes or (tl, r["to"]) not in nodes:
                    problems.append(f"{f.name}: {t} endpoint missing at import time ({r['from']} -> {r['to']})")
                    continue
                k = (t, r["props"]["rel_id"])
                if k not in rels:
                    rels[k] = (r["from"], r["to"])
                    created[run][1] += 1

print(f"files {len(files)}, statements {statements}")
print(f"first run created: {created[1][0]} nodes, {created[1][1]} relationships")
print(f"second run created: {created[2][0]} nodes, {created[2][1]} relationships")
print("problems:", problems[:10] or "none")
sys.exit(1 if problems or created[2] != [0, 0] else 0)
