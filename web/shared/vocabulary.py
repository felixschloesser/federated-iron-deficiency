"""Terms every party's web app uses: the general practitioner's app and the
hospital. No models, so either may import it."""

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
    """Why a general practitioner orders a CBC, in the guidelines' words; which of them the hospital screens is the hospital's rule."""

    SUSPECTED_ANAEMIA = "suspected_anaemia", "Suspected anaemia"
    SUSPECTED_IBS = "suspected_ibs", "Suspected irritable bowel syndrome"
    UNEXPLAINED_FATIGUE = "unexplained_fatigue", "Unexplained fatigue"
    START_OF_PREGNANCY = "start_of_pregnancy", "Start of pregnancy"
    CKD_FOLLOW_UP = "ckd_follow_up", "Chronic kidney disease follow-up"
    OTHER = "other", "Other"


class ResultName(models.TextChoices):
    """How a lab report names a measured value: NHANES 2021–2023's own label and
    unit (CBC_L and FERTIN_L codebooks); its value is the NHANES variable. In the
    order of ml.cohort.CBC_VARS, then ferritin, then the demo's made-up ferritin
    (web.hospital.analyser.models.MADE_UP_FERRITIN); a test checks the order."""

    WHITE_BLOOD_CELL_COUNT = "LBXWBCSI", "White blood cell count"
    RED_BLOOD_CELL_COUNT = "LBXRBCSI", "Red blood cell count"
    HEMOGLOBIN = "LBXHGB", "Hemoglobin"
    HEMATOCRIT = "LBXHCT", "Hematocrit"
    MEAN_CELL_VOLUME = "LBXMCVSI", "Mean cell volume"
    MEAN_CELL_HEMOGLOBIN_CONCENTRATION = "LBXMC", "Mean cell hemoglobin concentration"
    MEAN_CELL_HEMOGLOBIN = "LBXMCHSI", "Mean cell hemoglobin"
    RED_CELL_DISTRIBUTION_WIDTH = "LBXRDW", "Red cell distribution width"
    PLATELET_COUNT = "LBXPLTSI", "Platelet count"
    MEAN_PLATELET_VOLUME = "LBXMPSI", "Mean platelet volume"
    LYMPHOCYTE_NUMBER = "LBDLYMNO", "Lymphocyte number"
    SEGMENTED_NEUTROPHILS_NUMBER = "LBDNENO", "Segmented neutrophils number"
    MONOCYTE_NUMBER = "LBDMONO", "Monocyte number"
    FERRITIN = "LBXFER", "Ferritin"
    MADE_UP_FERRITIN = "MADE_UP_LBXFER", "Ferritin (made up for the demo)"

    def unit(self) -> str:
        """NHANES's unit for the value, with no conversion."""
        match self:
            case (
                ResultName.WHITE_BLOOD_CELL_COUNT
                | ResultName.PLATELET_COUNT
                | ResultName.LYMPHOCYTE_NUMBER
                | ResultName.SEGMENTED_NEUTROPHILS_NUMBER
                | ResultName.MONOCYTE_NUMBER
            ):
                return "1000 cells/µL"
            case ResultName.RED_BLOOD_CELL_COUNT:
                return "million cells/µL"
            case ResultName.HEMOGLOBIN | ResultName.MEAN_CELL_HEMOGLOBIN_CONCENTRATION:
                return "g/dL"
            case ResultName.HEMATOCRIT | ResultName.RED_CELL_DISTRIBUTION_WIDTH:
                return "%"
            case ResultName.MEAN_CELL_VOLUME | ResultName.MEAN_PLATELET_VOLUME:
                return "fL"
            case ResultName.MEAN_CELL_HEMOGLOBIN:
                return "pg"
            case ResultName.FERRITIN | ResultName.MADE_UP_FERRITIN:
                return "ng/mL"
            case _:
                assert_never(self)
