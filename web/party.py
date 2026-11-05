"""The party a deployment belongs to (demo/README.md): the same code runs as each."""

import enum
from typing import assert_never


class Party(enum.Enum):
    HOSPITAL = "hospital"
    GENERAL_PRACTITIONER = "general practitioner"

    def apps(self) -> list[str]:
        """This party's own Django apps; the other party never installs them (features/quality/party_isolation.feature)."""
        match self:
            case Party.HOSPITAL:
                return ["web.nhanes", "web.lab", "web.deployment"]
            case Party.GENERAL_PRACTITIONER:
                return ["web.practice"]
            case _:
                assert_never(self)
