"""Tiny helpers shared across modules.

Kept minimal on purpose; if a helper grows substantial enough to deserve
its own module, it should move.
"""
from __future__ import annotations

from re import finditer


def camel_case_split(identifier: str) -> list[str]:
    """Split a CamelCase or camelCase string into its component words.

    Used to humanise Mila enum values when rendering them in HA. For
    example, ``"LivingRoom"`` becomes ``["Living", "Room"]`` and
    ``"FiveOrMore"`` becomes ``["Five", "Or", "More"]``. The regex
    splits at every transition from lower-to-upper *or* from an
    upper-case run to upper+lower (so acronyms like ``HTTPRequest``
    yield ``["HTTP", "Request"]``).
    """
    # Pattern reads as: greedy "any characters" up to one of three
    # boundaries: a lower->upper transition, an upper->(upper-lower)
    # transition, or end-of-string.
    matches = finditer(
        ".+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)",
        identifier,
    )
    return [m.group(0) for m in matches]


def coalesce(*args):
    """SQL-style ``COALESCE``: return the first non-None argument.

    Returns ``None`` if every argument is ``None``. Used by
    ``MilaAppliance.name`` to fall back from the user-set device name
    to the room name to a humanised room kind.
    """
    return next((a for a in args if a is not None), None)
