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


DISCLAIMER = (
    "Research prototype for a privacy impact assessment. Patients are fictional;"
    " their blood values come from the NHANES 2021–2023 survey. Not for clinical use."
)


def test_every_page_says_it_is_a_prototype_with_fictional_patients() -> None:
    from django.template.loader import render_to_string

    template = engines["django"].from_string(
        '{% extends "kit/base.html" %}{% block title %}Probe{% endblock %}'
    )
    assert DISCLAIMER in template.render({}, RequestFactory().get("/"))
    # Django renders 500.html with no context at all.
    assert DISCLAIMER in render_to_string("500.html")


def test_a_link_that_looks_like_a_button_stays_a_link() -> None:
    # role="button" on a link promises Space as well as Enter, which a link
    # does not answer; a link styled as a button is the button-link class.
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    templates = [
        *root.glob("templates/**/*.html"),
        *root.glob("web/*/templates/**/*.html"),
    ]
    assert templates, root
    offenders = [
        f"{path.relative_to(root)}: {link}"
        for path in templates
        for link in re.findall(r"<a\b[^>]*>", path.read_text())
        if 'role="button"' in link
    ]
    assert offenders == []


def test_a_button_link_keeps_the_house_focus_outline() -> None:
    # The focus outline is a :where() rule, so any outline on the class would
    # beat it and leave keyboard focus only Pico's faint ring.
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[2] / "static/css/app.css").read_text()
    rules = re.findall(r"([^{}]*button-link[^{}]*)\{([^{}]*)\}", css)
    assert rules
    assert [selector.strip() for selector, body in rules if "outline:" in body] == []


def test_the_header_wraps_and_a_status_mark_keeps_its_padding_on_every_line() -> None:
    # Pico's nav is one flex row that never wraps, so on a phone the party's
    # name, the links and Log out overflow the page. A <mark> may wrap, as a
    # table cell on a phone must, but its padding must be drawn on each line;
    # nowrap instead widened the patient list past a 320px screen.
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[2] / "static/css/app.css").read_text()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    rules = {
        selector.strip(): body
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    }
    assert "flex-wrap: wrap" in rules.get("header nav,\nheader nav ul", ""), (
        rules.keys()
    )
    assert "box-decoration-break: clone" in rules.get("mark", "")
    assert "nowrap" not in rules.get("mark", "")
