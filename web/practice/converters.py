"""URL converter: `<test:test>` matches only a Test value."""

from web.shared.vocabulary import Test


class TestConverter:
    regex = "|".join(Test.values)

    def to_python(self, value: str) -> Test:
        return Test(value)

    def to_url(self, value: str) -> str:
        return Test(value).value  # Accepts a Test member or its string value.
