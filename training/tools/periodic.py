"""Compatibility shim: the periodic-table rules live in ultratiny.periodic (used by factgen)."""

from ultratiny.periodic import *  # noqa: F401,F403
from ultratiny.periodic import (  # noqa: F401
    ACTINOIDS,
    FAMILIES,
    GASES,
    HAUPTGRUPPE,
    LANTHANOIDS,
    LIQUIDS,
    NONMETALS,
    PERIOD_ENDS,
    SEMIMETALS,
)
