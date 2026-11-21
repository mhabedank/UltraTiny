"""Periodic-table position computed from the atomic number (own, deterministic).

Used by fetch_wikidata.py --chemie for element profiles at Mittelstufe level:
period, (Haupt-/Neben-)gruppe, element family, metal/non-metal/semimetal and state at 20 °C.
"""

from __future__ import annotations

PERIOD_ENDS = [2, 10, 18, 36, 54, 86, 118]
LANTHANOIDS = range(57, 72)
ACTINOIDS = range(89, 104)
NONMETALS = {1, 2, 6, 7, 8, 9, 10, 15, 16, 17, 18, 34, 35, 36, 53, 54, 86}
SEMIMETALS = {5, 14, 32, 33, 51, 52}
GASES = {1, 2, 7, 8, 9, 10, 17, 18, 36, 54, 86}
LIQUIDS = {35, 80}
FAMILIES = {1: "Alkalimetallen", 2: "Erdalkalimetallen", 16: "Chalkogenen", 17: "Halogenen",
            18: "Edelgasen"}  # fmt: skip
HAUPTGRUPPE = {1: 1, 2: 2, 13: 3, 14: 4, 15: 5, 16: 6, 17: 7, 18: 8}


def period(z: int) -> int:
    for p, end in enumerate(PERIOD_ENDS, 1):
        if z <= end:
            return p
    raise ValueError(z)


def iupac_group(z: int) -> int | None:
    """Group 1-18, None for lanthanoids/actinoids (f-block)."""
    if z == 1:
        return 1
    if z == 2:
        return 18
    if z in LANTHANOIDS or z in ACTINOIDS:
        return None
    p = period(z)
    start = PERIOD_ENDS[p - 2] + 1  # first element of the period
    i = z - start  # 0-based position in the period
    if p in (2, 3):
        return i + 1 if i < 2 else i + 11
    if p in (4, 5):
        return i + 1
    # periods 6/7: skip the 14 f-block elements after group 3
    return i + 1 if i < 3 else i + 1 - 14


def group_phrase(z: int) -> str:
    """Object text used in '{Element} steht in {phrase}.'"""
    if z in LANTHANOIDS:
        return "der Gruppe der Lanthanoide"
    if z in ACTINOIDS:
        return "der Gruppe der Actinoide"
    g = iupac_group(z)
    if g in HAUPTGRUPPE:
        return f"der {HAUPTGRUPPE[g]}. Hauptgruppe"
    return f"der {g}. Gruppe, einer Nebengruppe"


def family(z: int) -> str | None:
    if z == 1:
        return None  # hydrogen is in group 1 but not an alkali metal
    g = iupac_group(z)
    if z in LANTHANOIDS:
        return "Lanthanoiden"
    if z in ACTINOIDS:
        return "Actinoiden"
    return FAMILIES.get(g) if z <= 103 or g == 18 else None


def category(z: int) -> str | None:
    if z > 103:
        return None  # superheavy: properties unknown
    if z in NONMETALS:
        return "Nichtmetall"
    if z in SEMIMETALS:
        return "Halbmetall"
    return "Metall"


def state(z: int) -> str | None:
    if z > 103:
        return None
    if z in GASES:
        return "gasförmig"
    if z in LIQUIDS:
        return "flüssig"
    return "fest"


if __name__ == "__main__":
    for z in (1, 2, 3, 11, 26, 29, 35, 53, 57, 80, 82, 86, 92, 118):
        print(z, period(z), iupac_group(z), group_phrase(z), family(z), category(z), state(z))
