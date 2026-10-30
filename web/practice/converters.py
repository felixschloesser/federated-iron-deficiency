"""URL converter: `<test:test>` matches only the tests one can order."""

from web.vocabulary import Test


class TestConverter:
    regex = "|".join(Test.values)

    def to_python(self, value: str) -> Test:
        return Test(value)

    def to_url(self, value: str) -> str:
        return Test(value).value  # A Test member or its value
