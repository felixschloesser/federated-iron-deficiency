"""Views of the startup's training runs: who may, what the Final models page shows."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django import DjangoAssertNumQueries
from pytest_django.asserts import assertContains, assertRedirects
from pytest_django.fixtures import Settings

from iron_deficiency.final_models import keep_final_model
from iron_deficiency.task import Net
from tests.conftest import make_data_scientist, make_laboratory_director

pytestmark = pytest.mark.django_db


@pytest.fixture
def final_models_dir(tmp_path: Path, settings: Settings) -> Path:
    directory = tmp_path / "final-models"
    settings.FINAL_MODELS_DIR = directory
    keep_final_model(
        directory,
        run_id=7,
        state_dict=Net().state_dict(),
        threshold=0.4,
        federated={"eval_auroc": 0.861},
        stored_at=datetime(2026, 10, 30, 9, 0, tzinfo=UTC),
    )
    return directory


def test_final_models_page(
    client: Client,
    final_models_dir: Path,
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    client.force_login(make_data_scientist("Data One").user)
    # Session, user with role.
    with django_assert_num_queries(2):
        response = client.get(reverse("training:final_models"))
    assertContains(
        response,
        "<tr><td>30 Oct 2026, 10:00</td><td>7</td><td>0.4</td><td>0.86</td></tr>",
        html=True,
    )


def test_a_laboratory_director_is_sent_to_their_own_page(client: Client) -> None:
    client.force_login(make_laboratory_director("Director One").user)
    response = client.get(reverse("training:final_models"))
    assertRedirects(response, reverse("deployment:models"))
