"""Checks for the shared template kit."""

import pytest
from django.template import engines
from django.test import RequestFactory


def test_base_layout_renders() -> None:
    template = engines["django"].from_string(
        '{% extends "kit/base.html" %}{% block title %}Probe{% endblock %}'
    )
    html = template.render({}, RequestFactory().get("/"))
    assert "<title>Probe · Iron-deficiency screening</title>" in html


def test_missing_variable_fails_the_render() -> None:
    template = engines["django"].from_string("{{ absent }}")
    with pytest.raises(AssertionError, match="absent"):
        template.render({})
