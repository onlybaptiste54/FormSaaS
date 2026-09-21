import pytest

from app.luna_ops import LunaOps, OpsError, apply_ops, contrast_ratio, validate_state


THEME_KEYS = ("page_from", "page_to", "surface", "surface_alpha", "border", "border_alpha", "ink", "ink_soft",
              "accent", "accent_ink", "blur_px", "radius_px", "glow", "font", "heading_font", "title_scale", "title_case")
FIELD_KEYS = ("label", "placeholder", "required", "options", "scale")


def theme(**changes):
    return {"op": "set_theme", **{key: None for key in THEME_KEYS}, **changes}


def update_field(field_id, **changes):
    return {"op": "update_field", "id": field_id, **{key: None for key in FIELD_KEYS}, **changes}


def state():
    return {
        "name": "Demande de contact",
        "description": "Parlez-nous de votre projet.",
        "kind": "contact",
        "fields": [
            {"id": "name", "label": "Nom", "type": "text", "required": True},
            {"id": "email", "label": "Email", "type": "email", "required": True},
            {"id": "consent", "label": "J’accepte.", "type": "consent", "required": True},
        ],
        "design": {"layout": "card", "density": "comfortable", "style": {"ink": "#17211B", "surface": "#FFFFFF", "accent": "#2F6B4F", "accent_ink": "#FFFFFF"}},
        "content": {"eyebrow": "PRENONS CONTACT", "submit_label": "Envoyer", "trust_note": "Vos données sont protégées."},
        "thank_you": {"title": "Merci {prenom} !", "message": "Bien reçu.", "action": "cta", "button_url": "https://exemple.fr", "button_label": "Voir"},
    }


def run(ops):
    before = state()
    parsed = LunaOps.model_validate({"message": "Modification appliquée.", "ops": ops})
    after, touched = apply_ops(before, parsed.ops)
    validate_state(after, before)
    return after, touched


def test_a_text_change_leaves_everything_else_alone():
    after, touched = run([{"op": "set_text", "target": "submit_label", "value": "Être rappelé"}])
    assert after["content"]["submit_label"] == "Être rappelé"
    assert touched == ["submit"]
    assert after["name"] == state()["name"]
    assert after["design"] == state()["design"]


def test_fields_can_be_added_moved_and_removed():
    after, _ = run([
        {"op": "add_field", "after": "name", "field": {"id": "phone", "label": "Téléphone", "type": "tel", "required": False, "options": [], "scale": None, "placeholder": None}},
        {"op": "move_field", "id": "phone", "position": 0},
        {"op": "remove_field", "id": "email"},
    ])
    assert [field["id"] for field in after["fields"]] == ["phone", "name", "consent"]


def test_the_consent_field_survives_every_operation():
    after, _ = run([update_field("name", label="Votre nom complet")])
    assert after["fields"][-1]["type"] == "consent"
    assert after["fields"][-1]["label"] == "J’accepte."


def test_the_form_cannot_grow_past_five_business_fields():
    extra = [{"op": "add_field", "after": None, "field": {"id": f"extra{index}", "label": f"Champ {index}", "type": "text", "required": False, "options": [], "scale": None, "placeholder": None}} for index in range(4)]
    with pytest.raises(OpsError, match="5 champs"):
        run(extra)


def test_a_choice_field_needs_real_options():
    with pytest.raises(OpsError, match="deux options"):
        run([{"op": "add_field", "after": None, "field": {"id": "urgence", "label": "Urgent ?", "type": "radio", "required": True, "options": ["Oui"], "scale": None, "placeholder": None}}])


def test_an_unreadable_theme_is_refused():
    with pytest.raises(OpsError, match="Contraste"):
        run([theme(surface="#111111", ink="#1A1A1A")])


def test_a_dark_theme_with_light_text_passes():
    after, _ = run([theme(page_from="#0B0F1A", page_to="#1B2440", surface="#101728", ink="#F2F6FF", blur_px=24)])
    assert after["design"]["style"]["blur_px"] == 24
    assert after["design"]["style"]["accent"] == "#2F6B4F"


def test_the_thank_you_action_and_url_stay_out_of_reach():
    after, _ = run([{"op": "set_text", "target": "thanks_title", "value": "À très vite {prenom} !"}])
    assert after["thank_you"]["title"] == "À très vite {prenom} !"
    assert after["thank_you"]["action"] == "cta"
    assert after["thank_you"]["button_url"] == "https://exemple.fr"


def test_titles_can_be_restyled():
    after, touched = run([theme(heading_font="serif", title_scale=1.4, title_case="uppercase")])
    assert after["design"]["style"]["title_scale"] == 1.4
    assert after["design"]["style"]["heading_font"] == "serif"
    assert "title" in touched


def test_a_question_changes_nothing():
    after, touched = run([{"op": "ask"}])
    assert touched == []
    assert after["fields"] == state()["fields"]


def test_contrast_ratio_matches_the_wcag_reference():
    assert round(contrast_ratio("#000000", "#FFFFFF"), 1) == 21.0
    assert round(contrast_ratio("#FFFFFF", "#FFFFFF"), 1) == 1.0


def test_the_schema_sent_to_openai_uses_anyof():
    # L'API refuse `oneOf` : l'union discriminee de Pydantic doit etre convertie.
    from app.luna_ops import ops_json_schema

    items = ops_json_schema()["properties"]["ops"]["items"]
    assert "oneOf" not in items
    assert len(items["anyOf"]) == 8
    assert "discriminator" not in items
