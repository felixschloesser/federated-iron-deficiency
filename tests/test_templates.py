"""Checks for the shared template kit."""

import pytest
from django.template import engines
from django.test import RequestFactory
from pytest_django.fixtures import Settings


def test_base_layout_renders() -> None:
    template = engines["django"].from_string(
        '{% extends "kit/base.html" %}{% block title %}Probe{% endblock %}'
    )
    html = template.render({}, RequestFactory().get("/"))
    assert "<title>Probe · Demo hospital</title>" in html
    assert "screening" not in html.lower()


def test_title_and_header_name_only_the_hospital(settings: Settings) -> None:
    settings.PARTY_NAME = "AZ Diest"
    template = engines["django"].from_string(
        '{% extends "kit/base.html" %}{% block title %}Probe{% endblock %}'
    )
    html = template.render({}, RequestFactory().get("/"))
    assert "<title>Probe · AZ Diest</title>" in html
    assert "<strong>AZ Diest</strong>" in html


def test_missing_variable_fails_the_render() -> None:
    template = engines["django"].from_string("{{ absent }}")
    with pytest.raises(AssertionError, match="absent"):
        template.render({})


def test_a_party_colour_picks_its_pico_theme(settings: Settings) -> None:
    settings.PARTY_COLOUR = "jade"
    template = engines["django"].from_string(
        '{% extends "kit/base.html" %}{% block title %}Probe{% endblock %}'
    )
    html = template.render({}, RequestFactory().get("/"))
    assert "css/vendor/pico-2.1.1/pico.jade.min.css" in html
    assert "pico-2.1.1/pico.min.css" not in html


def test_without_a_party_colour_pico_keeps_its_default(settings: Settings) -> None:
    settings.PARTY_COLOUR = None
    template = engines["django"].from_string(
        '{% extends "kit/base.html" %}{% block title %}Probe{% endblock %}'
    )
    assert "pico-2.1.1/pico.min.css" in template.render({}, RequestFactory().get("/"))
