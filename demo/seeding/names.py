"""Fictional names for the demo patients the practice seeds
(demo/seeding/parties.py)."""

from typing import assert_never

from web.shared.vocabulary import RegisteredSex

# Fictional names that sound Flemish: the ten most common family names in the
# Flemish Region on 1 January 2026 (Statbel, "Family names"), and common Flemish
# first names, led by Maria and Marc, the most common there (Statbel, "Maria,
# Marie, Monique, Martine…", 2018). A real person with the same name is chance.
SURNAMES = (
    "Peeters",
    "Janssens",
    "Maes",
    "Jacobs",
    "Willems",
    "Mertens",
    "Claes",
    "Wouters",
    "Goossens",
    "De Smet",
)


def first_names(sex: RegisteredSex) -> tuple[str, ...]:
    match sex:
        case RegisteredSex.FEMALE:
            return (
                "Maria",
                "Sarah",
                "Laura",
                "Julie",
                "Lotte",
                "Emma",
                "Lien",
                "Sofie",
            )
        case RegisteredSex.MALE:
            return ("Marc", "Jan", "Luc", "Peter", "Tom", "Pieter", "Bart", "Wim")
        case _:
            assert_never(sex)


def patient_name(nhanes_number: int, sex: RegisteredSex) -> str:
    """A fictional name for a demo patient, the same every time it is seeded."""
    first = first_names(sex)
    return (
        f"{first[nhanes_number % len(first)]}"
        f" {SURNAMES[nhanes_number // len(first) % len(SURNAMES)]}"
    )
