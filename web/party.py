"""The party a deployment belongs to (spec §9): the same code runs as each."""

import enum


class Party(enum.Enum):
    HOSPITAL = "hospital"
    GENERAL_PRACTITIONER = "general practitioner"
