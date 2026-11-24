"""Language switch: every example has an English reading translation, the rules file gets English
comments without changing the real file, and e-mail translations never need a key for the examples."""

import re

from fastapi.testclient import TestClient

from intake.i18n import example_translations, rules_yaml_en, translate
from intake.rules import DEFAULT_RULES_PATH
from intake.scenarios import load_scenarios
from intake.web.app import create_app


def test_every_example_has_a_translation_in_the_other_language():
    tr = example_translations()["scenarios"]
    for sc in load_scenarios():
        t = tr[sc.id]
        assert t["title"] and t["description"]
        assert t["email"]["language"] in ("en", "de") and t["email"]["subject"] and t["email"]["body"]


def test_rules_file_comments_all_english_and_values_untouched():
    raw = DEFAULT_RULES_PATH.read_text(encoding="utf-8")
    en = rules_yaml_en(raw)
    assert len(en.splitlines()) == len(raw.splitlines())
    for de_line, en_line in zip(raw.splitlines(), en.splitlines()):
        code = de_line.split("#", 1)[0]
        assert en_line.startswith(code.rstrip()) or en_line.startswith(code)   # values never change
        if "#" in en_line:
            assert not re.search(r"[äöüß]", en_line.split("#", 1)[1].split("# =")[0]), en_line


def test_fields_and_keywords_translate():
    assert translate("seit gestern") == "since yesterday"
    assert translate("links") == "left"
    assert translate("Rohrverstopfung Küche") == "Blocked pipe, kitchen"
    assert "spüle (sink)" in translate("Regelmodus; gefundene Schlüsselwörter: wasser, spüle.")


def test_translate_email_uses_stored_example_without_key(monkeypatch, tmp_path):
    client = TestClient(create_app(static_dir=tmp_path))
    monkeypatch.setenv("GROQ_API_KEY", "")   # after create_app (which reads .env): no key = no live call
    sc = load_scenarios()[0]
    r = client.post("/api/translate-email", json={"subject": sc.email.subject, "body": sc.email.body, "target": "en"})
    assert r.json()["translation"]["source"] == "example"
    r = client.post("/api/translate-email", json={"subject": "x", "body": "Ganz neue Nachricht", "target": "en"})
    assert r.json() == {"translation": None}
    assert client.post("/api/translate-email", json={"body": "x", "target": "fr"}).status_code == 422
