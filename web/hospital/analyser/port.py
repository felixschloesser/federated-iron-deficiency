"""The analyser as the laboratory sees it, and the only module of this app the
laboratory imports. In the demo, NHANES participants stand in for the analyser;
a real analyser's interface would replace this module, and nothing in the
laboratory would change."""

from web.hospital.analyser.models import Participant
from web.shared.vocabulary import Test


def measure(sample_id: str, test: Test) -> dict[str, float] | None:
    """The analyser's values for `test` on sample `sample_id`, or None when it has
    no tube for that sample. In the demo, a sample holds the blood of the NHANES
    participant whose number is its sample ID."""
    participant = (
        Participant.objects.filter(seqn=int(sample_id)).first()
        if sample_id.isdigit()
        else None
    )
    return None if participant is None else participant.measure(test)
