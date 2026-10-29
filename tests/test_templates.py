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
    settings.HOSPITAL_NAME = "AZ Diest"
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
