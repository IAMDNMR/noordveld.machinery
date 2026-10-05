"""Short, casual part requests ("show me that belt", "do you have a hose", "hydraulics you have available"): drop the filler words and
singularise what is left, so the catalogue is searched for the thing the user named. Words are only removed, never added or guessed."""
from __future__ import annotations

import re

FILLER = frozenset(
    "a an the that this those these it its i im ive me my mine we our you your yours please pls can could would will should do does did have has got "
    "need needs want wants looking look find finding get give show list display see tell is are was be there any some all what which where when how "
    "for to of in on at with from by and or about into than then so just also available availability stock stocked store shop catalogue catalog "
    "machine machines part parts item items thing things something anything one ones kind type "
    "fit fits fitted fitting compatible compatibility work works suit suits suitable use used uses using model models spare spares".split()
)


def singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def content_words(question: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9\-]*", question.lower())
    return [singular(w) for w in words if w not in FILLER]


def content_text(question: str) -> str:
    return " ".join(content_words(question))
