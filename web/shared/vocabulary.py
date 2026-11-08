"""Terms every party's web app uses: the general practitioner's app and the
hospital (terms: web/shared/glossary.toml). No models, so either may import it."""

from dataclasses import dataclass
from typing import assert_never

from django.db import models


class RegisteredSex(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"

    @classmethod
    def of_nhanes(cls, label: str) -> "RegisteredSex":
        """The registered sex NHANES records as `label` ("Female", "Male")."""
        return cls(label.lower())


class Test(models.TextChoices):
    CBC = "cbc", "CBC"
    FERRITIN = "ferritin", "ferritin"

    def is_screened(self) -> bool:
        """Whether the hospital screens this test for iron deficiency."""
        match self:
            case Test.CBC:
                return True
            case Test.FERRITIN:
                return False
            case _:
                assert_never(self)

    def on_suspicion(self) -> bool:
        """Whether this test is ordered only beside a lab report suggesting it,
        on that lab report's sample: ferritin is ordered on suspicion."""
        match self:
            case Test.CBC:
                return False
            case Test.FERRITIN:
                return True
            case _:
                assert_never(self)

    def takes_indication(self) -> bool:
        """Whether an order for this test states a clinical indication."""
        match self:
            case Test.CBC:
                return True
            case Test.FERRITIN:
                return False
            case _:
                assert_never(self)


class ClinicalIndication(models.TextChoices):
    """Why a general practitioner orders a CBC, in the guidelines' words
    (web/shared/glossary.toml); which of them the hospital screens is the hospital's rule."""

    SUSPECTED_ANAEMIA = "suspected_anaemia", "Suspected anaemia"
    SUSPECTED_IBS = "suspected_ibs", "Suspected irritable bowel syndrome"
    UNEXPLAINED_FATIGUE = "unexplained_fatigue", "Unexplained fatigue"
    START_OF_PREGNANCY = "start_of_pregnancy", "Start of pregnancy"
    CKD_FOLLOW_UP = "ckd_follow_up", "Chronic kidney disease follow-up"
    OTHER = "other", "Other"


@dataclass(frozen=True)
class ResultName:
    """How a lab report names a measured value: NHANES 2021–2023's own label and
    unit (CBC_L and FERTIN_L codebooks), keyed by the NHANES variable."""

    name: str
    unit: str


# In the order of ml.cohort.CBC_VARS, then ferritin, then the demo's
# made-up ferritin (web.hospital.analyser.models.MADE_UP_FERRITIN); a test checks the order.
RESULT_NAMES = {
    "LBXWBCSI": ResultName("White blood cell count", "1000 cells/µL"),
    "LBXRBCSI": ResultName("Red blood cell count", "million cells/µL"),
    "LBXHGB": ResultName("Hemoglobin", "g/dL"),
    "LBXHCT": ResultName("Hematocrit", "%"),
    "LBXMCVSI": ResultName("Mean cell volume", "fL"),
    "LBXMC": ResultName("Mean cell hemoglobin concentration", "g/dL"),
    "LBXMCHSI": ResultName("Mean cell hemoglobin", "pg"),
    "LBXRDW": ResultName("Red cell distribution width", "%"),
    "LBXPLTSI": ResultName("Platelet count", "1000 cells/µL"),
    "LBXMPSI": ResultName("Mean platelet volume", "fL"),
    "LBDLYMNO": ResultName("Lymphocyte number", "1000 cells/µL"),
    "LBDNENO": ResultName("Segmented neutrophils number", "1000 cells/µL"),
    "LBDMONO": ResultName("Monocyte number", "1000 cells/µL"),
    "LBXFER": ResultName("Ferritin", "ng/mL"),
    "MADE_UP_LBXFER": ResultName("Ferritin (made up for the demo)", "ng/mL"),
}
