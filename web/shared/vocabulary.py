"""Choices that both the practice and the hospital use. The module defines no
models, so either party may import it."""

from typing import assert_never

from django.db import models


class RegisteredSex(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"

    @classmethod
    def of_nhanes(cls, label: str) -> "RegisteredSex":
        """Return the registered sex for NHANES's label ("Female" or "Male")."""
        return cls(label.lower())


class Test(models.TextChoices):
    CBC = "cbc", "CBC"
    FERRITIN = "ferritin", "ferritin"

    def is_screened(self) -> bool:
        """Whether the hospital screens this test for iron deficiency."""
        return self is Test.CBC

    def on_suspicion(self) -> bool:
        """Whether this test is ordered only after a lab report suggests it, on
        that lab report's sample."""
        return self is Test.FERRITIN

    def takes_indication(self) -> bool:
        """Whether an order for this test states a clinical indication."""
        return self is Test.CBC


class ClinicalIndication(models.TextChoices):
    """Why a general practitioner orders a CBC, in the guidelines' words. Which of
    them the hospital screens is decided in the hospital's code."""

    SUSPECTED_ANAEMIA = "suspected_anaemia", "Suspected anaemia"
    SUSPECTED_IBS = "suspected_ibs", "Suspected irritable bowel syndrome"
    UNEXPLAINED_FATIGUE = "unexplained_fatigue", "Unexplained fatigue"
    START_OF_PREGNANCY = "start_of_pregnancy", "Start of pregnancy"
    CKD_FOLLOW_UP = "ckd_follow_up", "Chronic kidney disease follow-up"
    OTHER = "other", "Other"


class ResultName(models.TextChoices):
    """The name of a measured value in a lab report: NHANES 2021–2023's label, with
    the NHANES variable as its value (CBC_L and FERTIN_L codebooks). The members
    follow the order of ml.cohort.CBC_VARS, then ferritin; a test checks it."""

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

    def unit(self) -> str:
        """NHANES's unit for this value; values are never converted."""
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
            case ResultName.FERRITIN:
                return "ng/mL"
            case _:
                assert_never(self)
