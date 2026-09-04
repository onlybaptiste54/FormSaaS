from app.template_catalog import campaign_fields, curated_template, template_payload


def test_curated_templates_are_returned_as_independent_copies():
    first = curated_template("contact-artisan")
    second = curated_template("contact-artisan")
    assert first is not None and second is not None
    first["fields"][0]["label"] = "Modifié"
    assert second["fields"][0]["label"] == "Nom et prénom"


def test_campaign_fields_add_controlled_consent_without_mutating_template():
    template = template_payload(curated_template("satisfaction-client"))
    fields = campaign_fields(template["fields"], "Atelier Test")
    assert len(fields) == len(template["fields"]) + 1
    assert fields[-1]["type"] == "consent"
    assert "Atelier Test" in fields[-1]["label"]
    assert all(field["type"] != "consent" for field in template["fields"])
