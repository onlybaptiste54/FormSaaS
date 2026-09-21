import json

import httpx
import pytest

from app.luna import LunaAPIError, generate_campaign, revise_campaign


DESIGN = {
    "layout": "card",
    "density": "comfortable",
    "field_style": "outline",
    "button_style": "solid",
    "heading_align": "left",
}

CONTENT = {
    "eyebrow": "PRENONS CONTACT",
    "submit_label": "Envoyer ma réponse",
    "trust_note": "Vos données sont protégées et utilisées uniquement pour traiter votre demande.",
}

STYLE = {
    "page_from": "#0B0F1A",
    "page_to": "#1B2440",
    "surface": "#101728",
    "surface_alpha": 0.18,
    "border": "#6EE7F9",
    "border_alpha": 0.3,
    "ink": "#F2F6FF",
    "ink_soft": "#9FB0CE",
    "accent": "#6EE7F9",
    "accent_ink": "#04121C",
    "blur_px": 24,
    "radius_px": 28,
    "glow": 0.7,
    "font": "grotesk",
}

AI_DESIGN = {**DESIGN, "style": STYLE}


def test_survey_generation_stays_short_and_rgpd_ready():
    campaign = generate_campaign("Je veux un sondage de satisfaction avec une note", "Atelier Test")
    assert campaign["kind"] == "survey"
    assert len(campaign["fields"]) <= 6
    assert campaign["fields"][-1]["type"] == "consent"
    assert campaign["fields"][-1]["required"] is True
    assert campaign["design"] == DESIGN
    assert campaign["content"]["eyebrow"] == "VOTRE AVIS COMPTE"


def test_contact_generation_understands_urgency():
    campaign = generate_campaign("Formulaire plombier avec type intervention et urgence", "Plombier Martin")
    ids = [field["id"] for field in campaign["fields"]]
    assert "urgent" in ids
    assert campaign["kind"] == "contact"


def test_openai_generation_uses_structured_output_and_safe_identity():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        sent_input = json.loads(payload["input"][0]["content"][0]["text"])
        assert request.headers["authorization"] == "Bearer test-key"
        assert payload["store"] is False
        assert payload["text"]["format"]["type"] == "json_schema"
        assert sent_input["identity"] == {
            "name": "Atelier Test",
            "sector": "Artisanat",
            "tone": "Professionnel",
            "primary_color": "#123456",
            "accent_color": "#abcdef",
        }
        result = {
            "name": "Demande dépannage",
            "description": "Décrivez rapidement votre besoin de dépannage.",
            "kind": "contact",
            "fields": [
                {"id": "nom", "label": "Nom", "type": "text", "required": True, "options": [], "scale": None, "placeholder": "Votre nom"},
                {"id": "urgence", "label": "Est-ce urgent ?", "type": "radio", "required": True, "options": ["Oui", "Non"], "scale": None, "placeholder": None},
            ],
            "design": AI_DESIGN,
            "content": CONTENT,
            "thank_you_title": "Merci {prenom} !",
            "thank_you_message": "Votre demande a bien été transmise à notre équipe.",
        }
        return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}]})

    campaign = generate_campaign(
        "Un formulaire de dépannage",
        {
            "name": "Atelier Test",
            "sector": "Artisanat",
            "tone": "Professionnel",
            "primary_color": "#123456",
            "accent_color": "#abcdef",
            "siret": "NE-DOIT-PAS-PARTIR",
            "dpo_email": "prive@example.test",
        },
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert campaign["name"] == "Demande dépannage"
    assert len(campaign["fields"]) == 3
    assert campaign["fields"][-1]["type"] == "consent"
    assert campaign["design"]["layout"] == "card"
    assert campaign["design"]["style"]["blur_px"] == 24
    assert campaign["design"]["style"]["page_from"] == "#0B0F1A"


def _ops_response(message, ops):
    return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"message": message, "ops": ops})}]}]})


CURRENT = {
    "name": "Contact",
    "description": "Un formulaire de contact pour nos visiteurs.",
    "kind": "contact",
    "fields": [
        {"id": "email", "label": "Email", "type": "email", "required": True},
        {"id": "message", "label": "Votre message", "type": "textarea", "required": False},
        {"id": "consent", "label": "J’accepte.", "type": "consent", "required": True},
    ],
    "design": {**DESIGN, "style": STYLE},
    "content": CONTENT,
    "thank_you": {"title": "Merci", "message": "Message reçu.", "action": "cta", "button_url": "https://exemple.fr", "button_label": "Voir"},
}

THEME = {"op": "set_theme", "page_from": None, "page_to": None, "surface": None, "surface_alpha": None, "border": None,
         "border_alpha": None, "ink": None, "ink_soft": None, "accent": None, "accent_ink": None, "blur_px": None,
         "radius_px": None, "glow": None, "font": None}


def test_revision_applies_only_the_requested_operations():
    capture = "data:image/png;base64,aGVsbG8="

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["input"][0]["content"]
        context = json.loads(content[0]["text"])
        assert payload["store"] is False
        assert context["selection"]["element_ids"] == ["submit"]
        assert context["recent_exchanges"][-1]["text"] == "Rends le bouton plus visible"
        assert all(field["type"] != "consent" for field in context["current_form"]["fields"])
        assert "siret" not in json.dumps(context)
        assert content[1] == {"type": "input_image", "image_url": capture, "detail": "high"}
        return _ops_response("Bouton en orange foncé, texte plus direct.", [
            {"op": "set_text", "target": "submit_label", "value": "Être rappelé"},
            {**THEME, "accent": "#A8380F", "accent_ink": "#FFFFFF"},
        ])

    revision = revise_campaign(
        CURRENT,
        "Rends le bouton plus visible",
        {"name": "Atelier Test", "primary_color": "#123456", "siret": "NE-DOIT-PAS-PARTIR"},
        selection={"element_ids": ["submit"], "label": "Bouton d’envoi", "view": "form"},
        history=[{"role": "user", "text": "Rends le bouton plus visible"}],
        screenshot_data_url=capture,
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert revision["content"]["submit_label"] == "Être rappelé"
    assert revision["design"]["style"]["accent"] == "#A8380F"
    assert revision["touched"] == ["submit", "card"]
    # Le reste du formulaire n'a pas bouge, consentement et tunnel compris.
    assert revision["name"] == "Contact"
    assert revision["fields"][-1]["type"] == "consent"
    assert revision["thank_you"]["button_url"] == "https://exemple.fr"


def test_revision_retries_once_when_a_guard_rail_fails():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        context = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        attempts.append(context.get("correction_demandee", ""))
        if len(attempts) == 1:
            return _ops_response("Fond sombre.", [{**THEME, "surface": "#111111", "ink": "#222222"}])
        return _ops_response("Fond sombre et texte clair.", [{**THEME, "surface": "#111111", "ink": "#F5F5F5"}])

    revision = revise_campaign(
        CURRENT,
        "Passe en sombre",
        {"name": "Atelier Test"},
        selection={"element_ids": ["card"], "label": "Formulaire complet", "view": "form"},
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert len(attempts) == 2
    assert "Contraste insuffisant" in attempts[1]
    assert revision["design"]["style"]["ink"] == "#F5F5F5"


def test_revision_refuses_to_change_the_type_of_an_existing_field():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ops_response("Champ email transformé.", [
            {"op": "remove_field", "id": "email"},
            {"op": "add_field", "after": None, "field": {"id": "email", "label": "Votre nom", "type": "text", "required": True, "options": [], "scale": None, "placeholder": None}},
        ])

    with pytest.raises(LunaAPIError) as error:
        revise_campaign(
            CURRENT,
            "Transforme le champ email en texte libre",
            {"name": "Atelier Test"},
            selection={"element_ids": ["field:email"], "label": "Champ email", "view": "form"},
            api_key="test-key",
            transport=httpx.MockTransport(handler),
        )
    assert "rester de type email" in str(error.value)
