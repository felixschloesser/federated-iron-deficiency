"""The startup's URLs follow one scheme: /<app>/<things>/ for an index,
/<app>/<things>/<id>/ for one thing, /<app>/<things>/<id>/<verb>/ for an action;
and its web app serves no other party's pages."""

import pytest
from django.urls import Resolver404, resolve, reverse


@pytest.mark.parametrize(
    ("name", "kwargs", "path"),
    [
        ("training:runs", {}, "/training/runs/"),
        ("training:stop", {"run_id": 7}, "/training/runs/7/stop/"),
        ("training:models", {}, "/training/models/"),
        ("training:release", {"run_id": "7"}, "/training/models/7/release/"),
    ],
)
def test_each_url_follows_the_scheme(
    name: str, kwargs: dict[str, object], path: str
) -> None:
    assert reverse(name, kwargs=kwargs) == path


@pytest.mark.parametrize("prefix", ["cohort/", "deployment/", "lab/", "practice/"])
def test_another_partys_pages_are_not_served_here(prefix: str) -> None:
    with pytest.raises(Resolver404):
        resolve(f"/{prefix}")
