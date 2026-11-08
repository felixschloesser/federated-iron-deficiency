"""Checks for .claude/audit.py, each on a small tree with one violation."""

from pathlib import Path

import pytest

import audit

# Split so that this file does not itself trip the audit.
NOQA = "# no" + "qa"
TYPE_IGNORE = "# type" + ": ignore"
CSRF_EXEMPT = "csrf" + "_exempt"
SAFE = "|sa" + "fe"


# Each party's settings module: where the audit learns which parties there are.
PARTY_SETTINGS = {
    f"web/{party}/settings.py": "" for party in ("hospital", "practice", "startup")
}


def tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in {**PARTY_SETTINGS, **files}.items():
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
            "templates/includes/base.html": '<main class="page"></main>\n',
            "templates/lab/index.html": '{% extends "includes/base.html" %}\n',
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
            "templates/includes/base.html": (
                '<p class="page {% if unread %}unread{% endif %}">\n'
            ),
        },
    )
    assert audit.run(root)["css_classes"] == [
        "templates/includes/base.html:1: class 'unread' is not defined in static/css"
    ]


def test_page_template_that_does_not_extend_the_base(tmp_path: Path) -> None:
    root = tree(tmp_path, {"templates/lab/index.html": "<html></html>\n"})
    assert counts(root)["includes_only"] == 1


def test_safe_filter_needs_an_allowlist_entry(tmp_path: Path) -> None:
    files = {"templates/includes/base.html": "{{ body" + SAFE + " }}\n"}
    assert counts(tree(tmp_path, files))["safe"] == 1
    allowlist = (
        '[safe]\n"templates/includes/base.html" = "Rendered Markdown we write"\n'
    )
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
    assert counts(tree(tmp_path, {"web/shared/x.py": code}))["suppressions"] == 1


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


def test_glossary_term_without_meaning_or_source(tmp_path: Path) -> None:
    practice = (
        '[order]\nmeaning = "What the GP asks for"\nsource = "Report, DF1"\n'
        '[read]\nmeaning = "x"\nsource = "unsourced"\n'
    )
    shared = '[seen]\nmeaning = "no source at all"\n[kept]\nsource = "Report, DF2"\n'
    root = tree(
        tmp_path,
        {
            "web/practice/settings.py": "",
            "web/practice/glossary.toml": practice,
            "web/shared/glossary.toml": shared,
        },
    )
    assert audit.run(root)["glossary_entries"] == [
        "web/practice/glossary.toml: term 'read' has no source",
        "web/shared/glossary.toml: term 'seen' has no source",
        "web/shared/glossary.toml: term 'kept' has no meaning",
    ]


def test_a_glossary_belongs_to_a_party_or_is_the_shared_one(tmp_path: Path) -> None:
    """Each party speaks its own language: its glossary sits in its folder, the
    words the parties share in web/shared/."""
    entry = '[sample]\nmeaning = "m"\nsource = "s"\n'
    root = tree(tmp_path, {"web/lab/glossary.toml": entry})
    assert audit.run(root)["glossary_entries"] == [
        "web/lab/glossary.toml: neither a party's glossary nor the shared one"
    ]


def test_glossary_record_names_only_glossary_terms(tmp_path: Path) -> None:
    glossary = '[order]\nmeaning = "What the GP asks for"\nsource = "Report, DF1"\n'
    record = '[order]\nrejected = ["request"]\n[gone]\nrejected = []\n'
    root = tree(
        tmp_path,
        {"web/shared/glossary.toml": glossary, ".claude/glossary_record.toml": record},
    )
    assert audit.run(root)["glossary_entries"] == [
        ".claude/glossary_record.toml: term 'gone' is in no glossary"
    ]


def test_feature_files_are_named_once_per_module_or_class_docstring(
    tmp_path: Path,
) -> None:
    code = (
        '"""Orders (features/a.feature, features/b.feature)."""\n\n\n'
        "class Order:\n"
        '    """One order (features/a.feature)."""\n\n'
        "    def place(self) -> None:\n"
        '        """Place it (features/a.feature)."""\n'
        "        # Once (features/a.feature).\n"
    )
    test = '"""Steps (features/a.feature)."""\n\n\ndef test_x() -> None:\n    """features/a.feature"""\n'
    root = tree(tmp_path, {"web/practice/models.py": code, "tests/test_x.py": test})
    assert audit.run(root)["feature_citations"] == [
        "web/practice/models.py:1: a second feature file in one docstring",
        "web/practice/models.py:8: feature file named outside a module or class docstring",
        "web/practice/models.py:9: feature file named outside a module or class docstring",
    ]


def test_any_finding_fails_the_audit(tmp_path: Path) -> None:
    root = tree(tmp_path, {"web/shared/x.py": f"x = 1  {NOQA}\n"})
    assert audit.main(["--root", str(root)]) == 1


def test_no_finding_passes_the_audit(tmp_path: Path) -> None:
    root = tree(tmp_path, {"web/shared/x.py": "x = 1\n"})
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
            "from web.shared.vocabulary import Test\n"
            "from web.hospital.lab.models import TestRequest\n",
            "web/hospital/lab/models.py": "import web.practice.models\n",
            "web/shared/accounts/backends.py": "from web.hospital.deployment import models\n",
            "web/shared/messaging/messages_pb2.py": "import grpc\n",
            "demo/demo.py": "from web.hospital.lab.models import TestRequest\n",
        },
    )
    assert audit.run(root)["party_imports"] == [
        "web/hospital/lab/models.py:1: the hospital's code imports web.practice",
        "web/practice/views.py:3: the practice's code imports web.hospital",
        "web/shared/accounts/backends.py:1: shared code imports web.hospital",
    ]


def test_each_partys_tests_import_only_its_own_code(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "tests/practice/test_messaging.py": "from tests.practice.conftest import x\n"
            "from web.hospital.lab.models import TestRequest\n",
            "tests/hospital/test_lab.py": "from tests.practice.conftest import make_patient\n",
            "tests/views/test_urls.py": "import web.hospital.lab.urls\nimport web.practice.pages\n",
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
            "web/shared/vocabulary.py": code,
            "web/startup/training/views.py": code,
        },
    )
    assert audit.run(root)["training_imports"] == [
        "web/practice/views.py:2: imports ml.inference, the hospital's code",
        "web/practice/views.py:3: imports ml.final_model, the hospital's or the startup's code",
        "web/shared/vocabulary.py:2: imports ml.inference, the hospital's code",
        "web/shared/vocabulary.py:3: imports ml.final_model, the hospital's or the startup's code",
        "web/startup/training/views.py:2: imports ml.inference, the hospital's code",
    ]


ROLES = (
    "class Role(TextChoices):\n"
    '    GENERAL_PRACTITIONER = "gp", "gp"\n'
    '    LABORATORY_STAFF = "staff", "staff"\n'
)


def test_each_party_installs_its_own_apps_and_no_other_partys(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "web/shared/accounts/roles.py": ROLES,
            "web/practice/apps.py": "",
            "web/hospital/lab/apps.py": "",
            "web/hospital/deployment/apps.py": "",
            "web/hospital/settings.py": 'INSTALLED_APPS: list[str] = [*SHARED_APPS, "web.hospital.lab"]\n'
            "ROLES = [Role.LABORATORY_STAFF]\n",
            "web/practice/settings.py": 'INSTALLED_APPS = ["web.practice", "web.hospital.lab"]\n'
            "ROLES = [Role.GENERAL_PRACTITIONER]\n",
        },
    )
    assert audit.run(root)["party_settings"] == [
        "web/hospital/settings.py: does not install web.hospital.deployment",
        "web/practice/settings.py: installs web.hospital.lab, the hospital's",
    ]


def test_every_role_logs_in_to_exactly_one_party(tmp_path: Path) -> None:
    root = tree(
        tmp_path,
        {
            "web/shared/accounts/roles.py": ROLES,
            "web/hospital/settings.py": "ROLES = [Role.GENERAL_PRACTITIONER]\n",
            "web/practice/settings.py": "ROLES = [Role.GENERAL_PRACTITIONER]\n",
        },
    )
    assert audit.run(root)["party_settings"] == [
        "web/shared/accounts/roles.py: Role.GENERAL_PRACTITIONER logs in to hospital and practice",
        "web/shared/accounts/roles.py: Role.LABORATORY_STAFF logs in to no party",
    ]


def test_a_partys_roles_are_no_listed_members(tmp_path: Path) -> None:
    """A party's settings write out its roles; party_settings checks them."""
    code = "ROLES = [Role.LABORATORY_STAFF, Role.LABORATORY_DIRECTOR]\n"
    root = tree(tmp_path, {"web/hospital/settings.py": code, "web/shared/x.py": code})
    assert audit.run(root)["listed_members"] == [
        "web/shared/x.py:1: members of Role listed; derive with match"
    ]


def test_the_hospital_reaches_the_analyser_only_through_its_port(
    tmp_path: Path,
) -> None:
    root = tree(
        tmp_path,
        {
            "web/hospital/lab/models.py": "from web.hospital.analyser import port\n"
            "from web.hospital.analyser.models import Participant\n",
            "web/hospital/analyser/port.py": "from web.hospital.analyser.models import Participant\n",
        },
    )
    assert audit.run(root)["analyser_port"] == [
        (
            "web/hospital/lab/models.py:2: imports web.hospital.analyser.models;"
            " use web.hospital.analyser.port"
        )
    ]
