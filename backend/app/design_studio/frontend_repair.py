"""Targeted repair of a generated file.

The builder reports exact lines. Asking the model for small find/replace edits there is faster and safer than rewriting a
500-line file, which is slow and, for long files, runs into the model's output limit and corrupts the file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.llm.base import LLMInvalidResponse

CONTEXT_LINES = 6
FILE = r"/?(src/[\w/-]+\.(?:tsx|ts|css))"
# Builder policy errors, Babel syntax errors and tsc errors each put the position somewhere different.
PATTERNS = (
    re.compile(rf"^{FILE}: (?P<m>.*) \[line (?P<l>\d+):"),
    re.compile(rf"^{FILE}: (?P<m>.*) \((?P<l>\d+):\d+\)$"),
    re.compile(rf"^{FILE}\((?P<l>\d+),\d+\): (?P<m>.*)"),
    re.compile(rf"^{FILE}: (?P<m>.*)"),
)

PATCH_SYSTEM = """You fix specific problems in one source file. You receive the file name, the problems (with line numbers) and
the numbered lines around each one. Return ONE JSON object only: {"edits": [{"find": str, "replace": str}]}.
"find" must be copied exactly from the excerpt (one or more whole lines) and identify exactly one occurrence; include more context if it repeats.
"replace" is the corrected text. Fix every listed problem, change nothing else, and keep the file's behaviour. If a fix needs
several lines changed, put them all in one edit.
Use the supplied SDK and module contracts; do not guess component props or SDK exports. Never silence an error with
any, @ts-ignore or @ts-expect-error. SDK mutations are returned by useStudio inside components; pass them to ordinary
helper functions as typed arguments. React checkbox indeterminate is a DOM property set through a ref, not a JSX attribute.
This app runs in an isolated frame. Never use window, localStorage, sessionStorage, navigator, location, fetch, or document
(except document.activeElement/addEventListener/removeEventListener). Instead: keep UI state in React state and apply it with
a className on an element React renders (for example a drawer-open class on the app wrapper, never on document or body); to
offer a download render <a href={"data:text/csv;charset=utf-8," + encodeURIComponent(csv)} download="name.csv">."""


# Compiler messages say what is wrong, not how to fix it; a model given only the message tends to write the same line again.
HINTS = (
    (
        re.compile(r"styles must be self-contained"),
        "Remove the entire CSS background-image/url declaration, including data SVGs. Keep native select arrows or render a lucide icon in React; never encode the URL another way.",
    ),
    (
        re.compile(r"Use @studio/sdk instead of window"),
        "Do not add another guard around window. Remove window reads and resize listeners entirely. Use CSS @media for responsive layout and React state for drawer visibility; close the drawer unconditionally on navigation.",
    ),
    (
        re.compile(r"rules-of-hooks|React Hook|React hook placement", re.I),
        "Call hooks once at the top of a React component or custom hook. Reuse that result in callbacks; pass SDK functions as typed arguments to ordinary helpers instead of calling useStudio inside them.",
    ),
    (
        re.compile(r'Expected ">" but found "\["'),
        "A JSX tag name cannot be an indexed expression such as <ICONS[key] />. Assign it first: const Icon = ICONS[key]; then render <Icon />.",
    ),
    (
        re.compile(r"Unexpected end of file"),
        "The file is cut off. Close every open tag, bracket and function and keep the file complete.",
    ),
    (
        re.compile(r"has no exported member '(\w+)'"),
        "Import only names the other file really exports, or define what you need in this file.",
    ),
    (
        re.compile(r"Cannot find module '(\.[^']+)'"),
        "That local file does not exist. Import only files from the plan, or define the component in this file.",
    ),
    (re.compile(r"Cannot find name '(\w+)'"), "Declare or import this name before using it."),
    (
        re.compile(r"does not exist on type 'JSX\.IntrinsicElements'"),
        "A lowercase JSX tag is treated as an HTML element. If the value is an element, render it as {value}; if it is a component, assign it to a capitalised name first (const LeftIcon = leftIcon) and render <LeftIcon />.",
    ),
    (
        re.compile(r"'\"lucide-react\"' has no exported member"),
        "Use an icon that lucide-react really exports, for example X for close, Plus for add, Pencil for edit.",
    ),
    (
        re.compile(r"'getState' does not exist"),
        "useStudio is a React hook with no getState: call useStudio() inside a component (or receive its functions as arguments) and use what it returns.",
    ),
    (
        re.compile(r"Property '(\w+)' does not exist on type 'string \| number \| boolean"),
        "The value can be a string, number or boolean: convert it first, for example String(value).slice(0, 10).",
    ),
)


def with_hint(message: str) -> str:
    return next(
        (f"{message} FIX: {hint}" for pattern, hint in HINTS if pattern.search(message)), message
    )


def build_errors(report: str) -> dict[str, list[dict]]:
    """Group the builder's report by file: {file: [{"line": int | None, "message": str}]}."""
    grouped: dict[str, list[dict]] = {}
    for text in report.splitlines():
        # tsc reports files under the temporary check folder (../../Temp/studio-source-check-x/src/a.tsx): keep the src/ path.
        text = re.sub(r"^\S*?studio-source-check-[^/\\]+[/\\]", "", text.strip())
        for pattern in PATTERNS:
            match = pattern.match(text.strip())
            if match:
                line = match.groupdict().get("l")
                grouped.setdefault(match.group(1), []).append(
                    {
                        "line": int(line) if line else None,
                        "message": with_hint(match.group("m")[:400]),
                    }
                )
                break
    return grouped


def _excerpt(lines: list[str], line: int) -> str:
    start, end = max(1, line - CONTEXT_LINES), min(len(lines), line + CONTEXT_LINES)
    return "\n".join(f"{n}| {lines[n - 1]}" for n in range(start, end + 1))


def patch_file(llm, sources: dict[str, str], name: str, problems: list[dict]) -> bool:
    """Apply the model's edits for the reported lines. False means nothing was fixed (caller falls back to a rewrite)."""
    if not problems or any(item["line"] is None for item in problems):
        return False
    lines = sources[name].split("\n")
    from app.design_studio.frontend_generation import module_contracts, symbol_usages
    from app.design_studio.frontend_imports import exports
    request = json.dumps(
        {
            "file": name,
            "problems": problems,
            "excerpts": [_excerpt(lines, item["line"]) for item in problems],
            "imports_and_local_types": "\n".join(lines[:80]),
            "related_module_headers": module_contracts({other: text for other, text in sources.items() if other != name}),
            "actual_caller_props_and_arguments": symbol_usages(sources, exports(sources[name]) | {Path(name).stem}, name),
            "sdk_contract": (
                Path(__file__).resolve().parents[3]
                / "frontend/scripts/studio-sdk.tsx"
            ).read_text(encoding="utf-8").split("const Context =", 1)[0],
        },
        ensure_ascii=False,
    )
    try:
        response = llm.studio_frontend(PATCH_SYSTEM, request)
        edits = response.get("edits") if isinstance(response, dict) else None
    except LLMInvalidResponse:
        return False
    text, applied = sources[name], 0
    for edit in edits if isinstance(edits, list) else []:
        if not isinstance(edit, dict):
            continue
        find, replace = edit.get("find"), edit.get("replace")
        if isinstance(find, str) and isinstance(replace, str) and find and find != replace and text.count(find) == 1:
            text, applied = text.replace(find, replace), applied + 1
    sources[name] = text
    return applied > 0


# <ICONS[key] ... /> is a mistake models repeat even when told how to fix it: it is not valid JSX, and the compiler only
# reports the first one per file, so repairs chase it line by line. It has one correct mechanical rewrite, applied here.
INDEXED_OPEN = re.compile(r"<([A-Za-z_$][\w$.]*\[[^\]\n]+\])(?=[\s/>])")
INDEXED_CLOSE = re.compile(r"</[A-Za-z_$][\w$.]*\[[^\]\n]+\]>")
DYNAMIC = "\nfunction DynamicIcon({ icon: Component, ...props }: any) {\n  return Component ? <Component {...props} /> : null\n}\n"


STYLE_IMPORT = re.compile(
    r"""^\s*import\s+['"][^'"]+\.css['"];?\s*$""", re.M
)  # Studio loads styles.css itself


def fix_indexed_tags(source: str) -> str:
    source = STYLE_IMPORT.sub("", source)
    if "window.location.reload()" in source:
        source = source.replace("window.location.reload()", "refresh()")
        source = re.sub(
            r"const\s*\{([^}]+)\}\s*=\s*useStudio\(\)",
            lambda match: match.group(0).replace(
                match.group(1),
                match.group(1) if re.search(r"\brefresh\b", match.group(1)) else match.group(1).rstrip() + ", refresh ",
            ),
            source,
            count=1,
        )
    # A generated modal does not need to lock the document behind its isolated frame.
    source = re.sub(
        r"^\s*document\.body\.style\.overflow\s*=\s*[^;\n]+;?\s*$", "", source, flags=re.M
    )
    source = re.sub(
        r"^\s*document\.(?:body|documentElement)\.classList\.(?:add|remove)\([^\n]*\);?\s*$",
        "",
        source,
        flags=re.M,
    )
    source = re.sub(
        r"^\s*const root = document\.getElementById\(['\"]app-root['\"]\);?\s*$",
        "",
        source,
        flags=re.M,
    )
    source = re.sub(
        r"^\s*root\?\.classList\.(?:add|remove)\(['\"]modal-open['\"]\);?\s*$",
        "",
        source,
        flags=re.M,
    )
    fixed = INDEXED_CLOSE.sub("</DynamicIcon>", INDEXED_OPEN.sub(r"<DynamicIcon icon={\1}", source))
    if fixed != source and "function DynamicIcon" not in fixed:
        fixed += DYNAMIC
    return fixed


def close_stylesheet(css: str) -> str:
    """A stylesheet cut off at the output limit ends inside a rule. Drop the unfinished declaration and close what is open,
    so the rules that were written still apply."""
    depth = css.count("{") - css.count("}")
    if depth <= 0:
        return css
    end = max(css.rfind(";"), css.rfind("}"), css.rfind("{"))
    return css[: end + 1] + "}" * depth + "\n"
