"""Build the reference catalog: reusable capabilities, shared foundations and domain packs, plus their scenario fixtures.

    python scripts/build_domain_catalog.py

Deterministic, reads nothing but this repository's code, writes packs to app/design_studio/knowledge/packs and fixtures to
app/design_studio/knowledge/fixtures. Every pack is validated with its dependencies before anything is written.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_dsl import PACKS  # noqa: E402


def packs():
    from catalog_a import all_a
    result = list(all_a())
    for module in ("catalog_b", "catalog_c", "catalog_sectors"):
        try:
            result += __import__(module).all_packs()
        except ModuleNotFoundError as exc:
            if exc.name != module:
                raise
    return result


def main() -> int:
    from app.design_studio.knowledge.models import ReferencePack
    built = packs()
    documents = {pack.id: pack.document() for pack in built}
    validated: dict[str, ReferencePack] = {}

    def check(pack_id: str):
        if pack_id in validated:
            return
        for dep in documents[pack_id]["depends_on"]:
            check(dep)
        validated[pack_id] = ReferencePack.model_validate(documents[pack_id], context={"dependencies": validated})

    for pack_id in documents:
        check(pack_id)
    for pack in built:
        pack.write()
    print(f"{len(built)} packs written to {PACKS}")
    for pack in built:
        b = documents[pack.id]["business"]
        print(f"  {pack.id:24s} {pack.layer:9s} entities={len(b['entities']):2d} rules={len(b['rules']):2d} roles={len(b['roles']):2d} workflows={len(pack.workflows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
