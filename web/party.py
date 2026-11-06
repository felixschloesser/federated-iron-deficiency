"""The party a deployment belongs to (demo/README.md): the same code runs as each."""

import enum
from typing import assert_never


class Party(enum.Enum):
    HOSPITAL = "hospital"
    PRACTICE = "practice"
    STARTUP = "startup"

    def apps(self) -> list[str]:
        """This party's own Django apps; no other party installs them (features/quality/party_isolation.feature)."""
        match self:
            case Party.HOSPITAL:
                return ["web.nhanes", "web.lab", "web.deployment"]
            case Party.PRACTICE:
                return ["web.practice"]
            case Party.STARTUP:
                return ["web.training"]
            case _:
                assert_never(self)

    def demo_name(self) -> str:
        """The name its pages show when PARTY_NAME names none."""
        match self:
            case Party.HOSPITAL:
                return "Demo hospital"
            case Party.PRACTICE:
                return "Demo practice"
            case Party.STARTUP:
                return "Demo startup"
            case _:
                assert_never(self)
