"""Art direction for a generated interface: the model decides how THIS application looks and navigates; code only checks it.

The shared design rules below constrain quality (contrast, responsiveness, visible navigation). They never supply content,
screens or a layout, so they cannot turn into an application template.
"""

from __future__ import annotations

import json
import re

from app.llm.base import LLMInvalidResponse
from app.schemas.application_definition import ApplicationDefinition

DESIGN_RULES = """
Shared design rules (quality constraints, not a layout):
- Follow art_direction: put its palette on :root as CSS custom properties and use its typography, density, shape language,
  navigation pattern and page compositions. Do not fall back to a default palette or a generic dashboard shell.
- Define every colour, spacing step, radius and font size once as a CSS variable in styles.css and use only those variables.
- Build mobile-first and add @media rules so every page works at 375px, 768px and 1280px with no horizontal scrolling.
- Navigation must be visible without an extra click on desktop widths (a persistent sidebar or top bar); collapse it behind a
  menu button only on narrow screens.
- Text contrast at least 4.5:1, touch targets at least 40px high, and a visible focus ring.
- styles.css must contain a rule for every class name the components use. Never use a class you have not defined.
- styles.css must be self-contained: no @import, no url(...) (not even data: URIs) and no external fonts. Use system fonts.
- Use semantic HTML (header, nav, main, buttons for actions, links only for navigation, tables only for tabular data). Use ARIA
  roles only where the markup needs them, together with their required parent and child roles.
- Every list or workspace needs loading, empty and error states written for its own task.
"""

ART_SYSTEM = """You are the art director for a business application. Decide how THIS application should look and navigate,
from its users, their tasks and its domain (project, domain_reference). Choose from the work people actually do; do not default
to a generic dashboard. Return ONE JSON object only:
{"identity": {"mood": str, "typography": str, "density": "compact|comfortable|spacious", "shape": str,
  "palette": {"background": "#RRGGBB", "surface": "#RRGGBB", "text": "#RRGGBB", "muted": "#RRGGBB",
              "accent": "#RRGGBB", "accent_text": "#RRGGBB"}},
 "navigation": {"pattern": str, "reason": str},
 "pages": [{"title": str, "composition": str, "reason": str}],
 "avoid": [str]}
composition says how a page is organised for the task it serves (for example a queue beside a detail pane for decisions); the
reason ties it to a user's task. Pick colours that suit the domain. Text must stay readable: text on background and on surface
at least 4.5:1, and accent_text on accent at least 4.5:1."""

PALETTE_KEYS = ("background", "surface", "text", "muted", "accent", "accent_text")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    """WCAG contrast ratio between two #RRGGBB colours."""
    light, dark = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def validate_direction(data: dict) -> dict:
    """Structure and readability only; what the application looks like stays the model's decision."""
    identity = data.get("identity")
    palette = identity.get("palette") if isinstance(identity, dict) else None
    if not isinstance(palette, dict) or any(
        not HEX.match(str(palette.get(key, ""))) for key in PALETTE_KEYS
    ):
        raise ValueError(
            "identity.palette needs " + ", ".join(PALETTE_KEYS) + " as #RRGGBB colours"
        )
    for text, ground in (("text", "background"), ("text", "surface"), ("accent_text", "accent")):
        if contrast(palette[text], palette[ground]) < 4.5:
            raise ValueError(f"palette.{text} on palette.{ground} has contrast below 4.5:1")
    navigation = data.get("navigation")
    pages = data.get("pages")
    if not isinstance(navigation, dict) or not navigation.get("pattern"):
        raise ValueError("navigation.pattern is required")
    if (
        not isinstance(pages, list)
        or not pages
        or any(not isinstance(p, dict) or not p.get("composition") for p in pages)
    ):
        raise ValueError("pages must list a composition for each page")
    return data


def art_direction(llm, context: dict) -> dict:
    """One model call (with one correction attempt) that fixes the visual identity and page compositions for the project."""
    prompt = json.dumps(context, ensure_ascii=False)
    for attempt in range(2):
        try:
            return validate_direction(llm.studio_frontend(ART_SYSTEM, prompt))
        except (ValueError, LLMInvalidResponse) as exc:
            if attempt:
                raise
            prompt += "\nFix this art direction: " + str(exc)[:500]


def domain_reference(definition: ApplicationDefinition) -> list[dict]:
    """Use the knowledge already adopted into this revision of the project.

    The reviewed requirements, entities and process are in the generation contract. A fresh
    Neo4j read here could change the evidence mid-revision or stall generation when DNS fails.
    """
    from app.design_studio.templates import visual_references

    domain = definition.business.brief.domain_id
    if not domain and not definition.business.knowledge:
        return []
    return [
        {
            "domain_id": domain,
            "adopted_packs": [
                {"pack_id": link.pack_id, "version": link.pack_version}
                for link in definition.business.knowledge
            ],
            "visual_references": visual_references(definition),
            "usage": "Optional visual patterns only. Combine useful patterns across sources; derive all required pages and capabilities from the application blueprint and business contract.",
        }
    ]


BASE_START, BASE_END = "/* base layer */", "/* end base layer */"


def css_variables() -> list[str]:
    """The custom properties the base layer defines, so the model's own rules can use them without redefining them."""
    return [
        "--bg",
        "--surface",
        "--text",
        "--muted",
        "--accent",
        "--accent-text",
        "--space-1",
        "--space-2",
        "--space-3",
        "--space-4",
        "--space-5",
        "--radius",
        "--text-sm",
        "--text-md",
        "--text-lg",
        "--text-xl",
    ]


def with_base(css: str, direction: dict) -> str:
    """Put the art direction's palette and the shared resets in front of the model's rules. Writing them is the same every time,
    so the model only spends output on the layout and components of this application."""
    palette = direction["identity"]["palette"]
    base = f"""{BASE_START}
:root{{--bg:{palette["background"]};--surface:{palette["surface"]};--text:{palette["text"]};--muted:{palette["muted"]};--accent:{palette["accent"]};--accent-text:{palette["accent_text"]};
--space-1:.25rem;--space-2:.5rem;--space-3:.75rem;--space-4:1rem;--space-5:1.5rem;--radius:8px;--text-sm:.875rem;--text-md:1rem;--text-lg:1.25rem;--text-xl:1.75rem}}
*,*::before,*::after{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font:var(--text-md)/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
button,input,select,textarea{{font:inherit;color:inherit;min-height:40px}}
:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
[hidden]{{display:none!important}}
.sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}}
{BASE_END}
"""
    start = css.find(BASE_START)
    end = css.find(BASE_END)
    if start != -1 and end != -1:
        css = css[:start] + css[end + len(BASE_END) :]
    return base + css.lstrip("\n")
