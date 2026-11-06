"""Checks for .claude/audit.py, each on a small tree with one violation."""

from pathlib import Path

import pytest

import audit

# Split so that this file does not itself trip the audit.
NOQA = "# no" + "qa"
TYPE_IGNORE = "# type" + ": ignore"
CSRF_EXEMPT = "csrf" + "_exempt"
SAFE = "|sa" + "fe"


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def counts(root: Path) -> dict[str, int]:
    return {name: len(findings) for name, findings in audit.run(root).items()}


def test_clean_tree_has_no_findings(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "static/css/app.css": ".page { margin: 0; }\n",
            "templates/kit/base.html": '<main class="page"></main>\n',
            "templates/lab/index.html": '{% extends "kit/base.html" %}\n',
            "web/hospital/lab/views.py": (
                "class ReceiveView(View):\n"
                "    def post(self, request) -> HttpResponse:\n"
                "        self.test_request.run_analyser(now)\n"
            ),
        },
    )
    assert not any(counts(root).values()), audit.run(root)


def test_undefined_css_class(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "static/css/app.css": ".page {}\n",
            "templates/kit/base.html": (
                '<p class="page {% if unread %}unread{% endif %}">\n'
            ),
        },
    )
    assert audit.run(root)["css_classes"] == [
        "templates/kit/base.html:1: class 'unread' is not defined in static/css"
    ]


def test_page_template_outside_the_kit(tmp_path: Path) -> None:
    root = tree(tmp_path, {"templates/lab/index.html": "<html></html>\n"})
    assert counts(root)["kit_only"] == 1


def test_safe_filter_needs_an_allowlist_entry(tmp_path: Path) -> None:
    files = {"templates/kit/base.html": "{{ body" + SAFE + " }}\n"}
    assert counts(tree(tmp_path, files))["safe"] == 1
    allowlist = '[safe]\n"templates/kit/base.html" = "Rendered Markdown we write"\n'
    tree(tmp_path, {".claude/audit_allowlist.toml": allowlist})
    assert counts(tmp_path)["safe"] == 0


@pytest.mark.parametrize(
    "code",
    [
        f"x = 1  {NOQA}\n",
        f"x = 1  {TYPE_IGNORE}\n",
        f"@{CSRF_EXEMPT}\ndef view(request):\n    pass\n",
    ],
)
def test_suppressions(tmp_path: Path, code: str) -> None:
    assert counts(tree(tmp_path, {"web/x.py": code}))["suppressions"] == 1


def test_listed_choice_members(tmp_path: Path) -> None:
    code = "OPEN = [Status.ORDERED, Status.RECEIVED]\n"
    assert (
        counts(tree(tmp_path, {"web/hospital/lab/models.py": code}))["listed_members"]
        == 1
    )


def test_mutation_outside_a_post_handler(tmp_path: Path) -> None:
    code = (
        "class IndexView(ListView):\n"
        "    def get_queryset(self) -> QuerySet:\n"
        "        sample.save()\n"
    )
    assert audit.run(tree(tmp_path, {"web/hospital/lab/views.py": code}))[
        "get_mutation"
    ] == [
        "web/hospital/lab/views.py:2: IndexView.get_queryset mutates outside a POST handler"
    ]


def test_form_valid_may_write(tmp_path: Path) -> None:
    code = (
        "class NewOrderView(FormView):\n"
        "    def form_valid(self, form) -> HttpResponse:\n"
        "        self.general_practitioner.place_order()\n"
    )
    assert counts(tree(tmp_path, {"web/practice/views.py": code}))["get_mutation"] == 0


MODELS_WITH_A_WRITE = (
    "class Patient(models.Model):\n"
    "    @transaction.atomic\n"
    "    def collect_sample(self, now):\n"
    "        return self.samples.create(collected_at=now)\n"
)


def test_calling_a_writing_model_method_outside_a_post_handler(
    tmp_path: Path,
) -> None:
    view = (
        "class PatientView(DetailView):\n"
        "    def get_context_data(self, **kwargs) -> dict:\n"
        "        self.object.collect_sample(now)\n"
    )
    root = tree(
        tmp_path,
        {"web/practice/models.py": MODELS_WITH_A_WRITE, "web/practice/views.py": view},
    )
    finding = (
        "web/practice/views.py:2: PatientView.get_context_data mutates outside a"
        " POST handler"
    )
    assert audit.run(root)["get_mutation"] == [finding]


def test_a_post_handler_may_call_a_writing_model_method(tmp_path: Path) -> None:
    view = (
        "class CollectSampleView(View):\n"
        "    def post(self, request) -> HttpResponse:\n"
        "        patient.collect_sample(now)\n"
    )
    root = tree(
        tmp_path,
        {"web/practice/models.py": MODELS_WITH_A_WRITE, "web/practice/views.py": view},
    )
    assert counts(root)["get_mutation"] == 0


def test_function_view(tmp_path: Path) -> None:
    code = "def index(request) -> HttpResponse:\n    return render(request, 'x.html')\n"
    assert audit.run(tree(tmp_path, {"web/hospital/lab/views.py": code}))[
        "get_mutation"
    ] == ["web/hospital/lab/views.py:1: function view index; use a class-based view"]


def test_helpers_are_not_views(tmp_path: Path) -> None:
    code = "def general_practitioner_of(request) -> GeneralPractitioner:\n    return GeneralPractitioner.objects.get()\n"
    assert counts(tree(tmp_path, {"web/practice/views.py": code}))["get_mutation"] == 0


def test_unsourced_glossary_term(tmp_path: Path) -> None:
    glossary = (
        '[order]\nsource = "Report, DF1"\nwhy = "Report\'s word"\nrejected = ["request"]\n'
        '[read]\nsource = "unsourced"\nwhy = "x"\nrejected = []\n'
        '[seen]\nwhy = "no source at all"\nrejected = []\n'
    )
    root = tree(tmp_path, {"glossary.toml": glossary})
    assert audit.run(root)["glossary_sources"] == [
        "glossary.toml: term 'read' has no source",
        "glossary.toml: term 'seen' has no source",
    ]


def test_any_finding_fails_the_audit(tmp_path: Path) -> None:
    root = tree(tmp_path, {"web/x.py": f"x = 1  {NOQA}\n"})
    assert audit.main(["--root", str(root)]) == 1


def test_no_finding_passes_the_audit(tmp_path: Path) -> None:
    root = tree(tmp_path, {"web/x.py": "x = 1\n"})
    assert audit.main(["--root", str(root)]) == 0


def test_web_imports_only_the_screening_side(tmp_path: Path) -> None:
    code = (
        "from ml.cohort import CBC_VARS\n"
        "from ml.inference import score\n"
        "from ml.client_app import app\n"
        "import ml.server_app\n"
    )
    root = tree(tmp_path, {"web/hospital/lab/models.py": code, "tools/x.py": code})
    assert audit.run(root)["training_imports"] == [
        "web/hospital/lab/models.py:3: imports ml.client_app, the Flower app's code",
        "web/hospital/lab/models.py:4: imports ml.server_app, the Flower app's code",
    ]


def test_each_party_imports_only_its_own_apps(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "web/practice/views.py": "from web.practice.models import Order\n"
            "from web.vocabulary import Test\n"
            "from web.hospital.lab.models import TestRequest\n",
            "web/hospital/lab/models.py": "import web.practice.models\n",
            "web/accounts/backends.py": "from web.hospital.deployment import models\n",
            "web/messaging/messages_pb2.py": "import grpc\n",
            "demo/demo.py": "from web.hospital.lab.models import TestRequest\n",
        },
    )
    assert audit.run(root)["party_imports"] == [
        "web/accounts/backends.py:1: shared code imports web.hospital",
        "web/hospital/lab/models.py:1: the hospital's code imports web.practice",
        "web/practice/views.py:3: the practice's code imports web.hospital",
    ]


def test_each_partys_tests_import_only_its_own_code(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "tests/practice/test_messaging.py": "from tests.practice.conftest import x\n"
            "from web.hospital.lab.models import TestRequest\n",
            "tests/hospital/test_lab.py": "from tests.practice.conftest import make_patient\n",
            "tests/views/test_urls.py": "import web.hospital.lab.urls\nimport web.practice.urls\n",
        },
    )
    assert audit.run(root)["party_imports"] == [
        "tests/hospital/test_lab.py:1: the hospital's code imports tests.practice",
        "tests/practice/test_messaging.py:2: the practice's code imports web.hospital",
    ]


def test_only_the_hospital_imports_the_screening(tmp_path: Path) -> None:
    code = (
        "from ml.cohort import CBC_VARS\n"
        "from ml.inference import score\n"
        "from ml.final_model import read\n"
    )
    root = tree(
        tmp_path,
        {
            "web/hospital/lab/models.py": code,
            "web/practice/views.py": code,
            "web/seeding/command.py": code,
            "web/startup/training/views.py": code,
        },
    )
    assert audit.run(root)["training_imports"] == [
        "web/practice/views.py:2: imports ml.inference, the hospital's code",
        "web/practice/views.py:3: imports ml.final_model, the hospital's or the startup's code",
        "web/seeding/command.py:2: imports ml.inference, the hospital's code",
        "web/seeding/command.py:3: imports ml.final_model, the hospital's or the startup's code",
        "web/startup/training/views.py:2: imports ml.inference, the hospital's code",
    ]
