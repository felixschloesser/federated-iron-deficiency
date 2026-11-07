"""The analyser as the laboratory sees it (report, P9: laboratory staff run the
analyser): the one module of this app the laboratory imports. Behind it the
demo's stand-in answers from NHANES participants; a real analyser's interface
would replace this module and nothing in the laboratory."""

from web.hospital.analyser.models import Participant
from web.shared.vocabulary import Test


def measure(sample_id: str, test: Test) -> dict[str, float] | None:
    """The analyser's values for `test` on the sample `sample_id` (DF36); None when
    it has no tube for that sample. In the demo, every sample of one patient
    holds the blood of the NHANES participant whose number starts its sample
    ID."""
    number = sample_id.split("-")[0]
    participant = (
        Participant.objects.filter(seqn=int(number)).first()
        if number.isdigit()
        else None
    )
    return None if participant is None else participant.measure(test)
