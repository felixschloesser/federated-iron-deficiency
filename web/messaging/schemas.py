"""The messages between the general practitioner's app and the hospital, as
JSON (features/messaging.feature). The app is always the client and names its
practice in every message; the hospital checks every message against these
schemas, the app every lab report. No other field is accepted."""

from ninja import Schema
from pydantic import AwareDatetime, ConfigDict, Field

from web.vocabulary import RegisteredSex, Test


class Message(Schema):
    model_config = ConfigDict(extra="forbid")


class LabOrder(Message):
    """DF23. No patient name, no blood values, no clinical indication: the
    tube's values are measured at the hospital, and of the indication the
    laboratory needs only whether it is screened (features/screening.feature)."""

    practice: str = Field(min_length=1, max_length=100)
    sample_id: str = Field(min_length=1, max_length=20)
    test: Test
    # False when absent: never screened by mistake.
    screened_indication: bool = False
    registered_sex: RegisteredSex
    age: int = Field(ge=0)
    ordered_at: AwareDatetime


class LabReport(Message):
    """DF25. Results and one bit of screening (features/reports.feature): no
    score, and nothing that tells ferritin not suggested from not screened."""

    report_id: int
    sample_id: str
    test: Test
    results: dict[str, float]
    # False when absent: never a false suggestion.
    ferritin_suggested: bool = False
    released_at: AwareDatetime


class Acknowledgement(Message):
    """The lab reports the app has stored: the hospital hands them out no more."""

    practice: str = Field(min_length=1, max_length=100)
    report_ids: list[int]
