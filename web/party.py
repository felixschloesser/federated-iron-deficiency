"""The party a deployment belongs to (spec §9): the same code runs as each."""

import enum
from typing import assert_never


class Party(enum.Enum):
    HOSPITAL = "hospital"
    GENERAL_PRACTITIONER = "general practitioner"
    STARTUP = "startup"

    def apps(self) -> list[str]:
        """This party's own Django apps; no other party installs them (R21)."""
        match self:
            case Party.HOSPITAL:
                return ["web.nhanes", "web.lab", "web.deployment"]
            case Party.GENERAL_PRACTITIONER:
                return ["web.practice"]
            case Party.STARTUP:
                return ["web.training"]
            case _:
                assert_never(self)
