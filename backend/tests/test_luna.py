import json

import httpx

from app.luna import generate_campaign, revise_campaign


DESIGN = {
    "layout": "card",
    "background": "warm",
    "density": "comfortable",
    "radius": "rounded",
    "field_style": "outline",
    "button_style": "solid",
    "heading_align": "left",
}


def test_survey_generation_stays_short_and_rgpd_ready():
    campaign = generate_campaign("Je veux un sondage de satisfaction avec une note", "Atelier Test")
    assert campaign["kind"] == "survey"
    assert len(campaign["fields"]) <= 6
    assert campaign["fields"][-1]["type"] == "consent"
    assert campaign["fields"][-1]["required"] is True
    assert campaign["design"] == DESIGN


def test_contact_generation_understands_urgency():
    campaign = generate_campaign("Formulaire plombier avec type intervention et urgence", "Plombier Martin")
    ids = [field["id"] for field in campaign["fields"]]
    assert "urgent" in ids
    assert campaign["kind"] == "contact"


def test_openai_generation_uses_structured_output_and_safe_identity():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        sent_input = json.loads(payload["input"])
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
            "design": DESIGN,
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


def test_visual_revision_sends_selected_capture_and_returns_safe_tokens():
    capture = "data:image/png;base64,aGVsbG8="

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        content = payload["input"][0]["content"]
        context = json.loads(content[0]["text"])
        assert payload["store"] is False
        assert context["selection"] == {"kind": "field", "id": "email", "label": "Email"}
        assert context["current_campaign"]["fields"][0]["id"] == "email"
        assert all(field["type"] != "consent" for field in context["current_campaign"]["fields"])
        assert content[1] == {"type": "input_image", "image_url": capture, "detail": "low"}
        result = {
            "name": "Contact rapide",
            "description": "Laissez-nous vos coordonnées pour être rappelé rapidement.",
            "kind": "contact",
            "fields": [
                {"id": "email", "label": "Votre meilleur email", "type": "email", "required": True, "options": [], "scale": None, "placeholder": "vous@entreprise.fr"},
            ],
            "design": {**DESIGN, "field_style": "filled", "radius": "pill"},
            "thank_you_title": "Merci !",
            "thank_you_message": "Votre demande a bien été envoyée à notre équipe.",
            "assistant_message": "J’ai adouci le champ email et clarifié son libellé.",
        }
        return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(result)}]}]})

    revision = revise_campaign(
        {
            "name": "Contact",
            "description": "Un formulaire de contact pour nos visiteurs.",
            "kind": "contact",
            "fields": [
                {"id": "email", "label": "Email", "type": "email", "required": True},
                {"id": "consent", "label": "J’accepte.", "type": "consent", "required": True},
            ],
            "design": DESIGN,
            "thank_you": {"title": "Merci", "message": "Message reçu."},
        },
        "Rends ce champ plus doux",
        {"name": "Atelier Test", "primary_color": "#123456"},
        selection={"kind": "field", "id": "email", "label": "Email"},
        screenshot_data_url=capture,
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert revision["design"]["field_style"] == "filled"
    assert revision["design"]["radius"] == "pill"
    assert revision["fields"][-1]["type"] == "consent"
    assert revision["assistant_message"].startswith("J’ai adouci")
