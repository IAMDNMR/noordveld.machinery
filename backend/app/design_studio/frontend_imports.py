"""Mechanical import wiring between generated files.

Files are written by separate model calls, so they often disagree on names: an icon used but not imported, a helper that
exists in the shared module but is not imported where it is used, or a component imported from the shared module that it
never defines. The first two have exactly one correct fix and are applied here; the third is returned so the model writes
the missing definitions once, into the module that should export them.
"""

from __future__ import annotations

from functools import lru_cache
import posixpath
import re

from app.design_studio.frontend_generation import FRONTEND

ERROR = re.compile(r"(src/[\w/.-]+\.tsx?)\(\d+,\d+\): error (TS\d+): (.*)")
NOT_FOUND = re.compile(r"Cannot find name '(\w+)'")
NO_MEMBER = re.compile(r"""Module '"([^"]+)"' has no exported member '(\w+)'""")
NAMED_IMPORT = re.compile(r"""import\s*(type\s*)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"];?""")
EXPORTED = re.compile(r"export\s+(?!default\b)(?:async\s+)?(?:function|const|let|class|type|interface|enum)\s+(\w+)")


@lru_cache(maxsize=1)
def lucide_icons() -> frozenset[str]:
    text = (FRONTEND / "node_modules/lucide-react/dist/lucide-react.d.ts").read_text(encoding="utf-8")
    return frozenset(re.findall(r"declare const (\w+)", text))


def exports(source: str) -> set[str]:
    return set(EXPORTED.findall(source)) | {
        name.split(" as ")[-1].strip() for block in re.findall(r"export\s*\{([^}]*)\}", source) for name in block.split(",") if name.strip()
    }


def module_path(importer: str, specifier: str, sources: dict[str, str]) -> str | None:
    base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), specifier))
    return next((name for name in (base, f"{base}.tsx", f"{base}.ts") if name in sources), None)


def specifier(importer: str, module: str) -> str:
    path = posixpath.relpath(posixpath.splitext(module)[0], posixpath.dirname(importer))
    return path if path.startswith(".") else "./" + path


def _set_import(source: str, module_spec: str, add: set[str] = frozenset(), remove: set[str] = frozenset()) -> str:
    """Add or remove names in the named import from one module, creating or deleting the statement as needed."""
    for match in NAMED_IMPORT.finditer(source):
        if match.group(3) != module_spec or match.group(1):
            continue
        names = [item.strip() for item in match.group(2).split(",") if item.strip()]
        kept = [item for item in names if item.split(" as ")[-1].strip() not in remove]
        kept += sorted(name for name in add if name not in {item.split(" as ")[-1].strip() for item in kept})
        statement = f"import {{ {', '.join(kept)} }} from '{module_spec}'" if kept else ""
        return source[: match.start()] + statement + source[match.end():]
    if not add:
        return source
    return f"import {{ {', '.join(sorted(add))} }} from '{module_spec}'\n" + source


def wire_imports(sources: dict[str, str], report: str) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Fix the import errors that have one answer. Returns the updated sources and {module: names it must still define}."""
    files = dict(sources)
    icons = lucide_icons()
    local = {name: exports(text) for name, text in files.items() if name.endswith((".ts", ".tsx"))}
    missing: dict[str, set[str]] = {}
    for line in report.splitlines():
        match = ERROR.search(line)
        if not match or match.group(1) not in files:
            continue
        importer, message = match.group(1), match.group(3)
        if found := NOT_FOUND.search(message):
            name = found.group(1)
            owner = next((module for module, names in local.items() if name in names and module != importer), None)
            if name in icons:
                files[importer] = _set_import(files[importer], "lucide-react", add={name})
            elif owner:
                files[importer] = _set_import(files[importer], specifier(importer, owner), add={name})
        elif member := NO_MEMBER.search(message):
            spec, name = member.group(1), member.group(2)
            target = module_path(importer, spec, files)
            owner = next((module for module, names in local.items() if name in names and module != importer), None)
            if name in icons:
                files[importer] = _set_import(files[importer], spec, remove={name})
                files[importer] = _set_import(files[importer], "lucide-react", add={name})
            elif owner and owner != target:
                files[importer] = _set_import(files[importer], spec, remove={name})
                files[importer] = _set_import(files[importer], specifier(importer, owner), add={name})
            elif target:
                missing.setdefault(target, set()).add(name)
    return files, missing
