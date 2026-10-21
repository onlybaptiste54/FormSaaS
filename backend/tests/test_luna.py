import json

import httpx
import pytest

from app.luna import LunaAPIError, generate_campaign, generate_page, merge_page_region, revise_campaign, revise_page, stream_page_revision


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
    "heading_font": "serif",
    "title_scale": 1.2,
    "title_case": "normal",
}

AI_DESIGN = {**DESIGN, "style": STYLE}


def test_survey_generation_stays_short_and_rgpd_ready():
    campaign = generate_campaign("Je veux un sondage de satisfaction avec une note", "Atelier Test")
    assert campaign["kind"] == "survey"
    assert len(campaign["fields"]) <= 6
    assert campaign["fields"][-1]["type"] == "consent"
    assert campaign["fields"][-1]["required"] is True
    assert campaign["design"] == {
        **DESIGN, "layout": "minimal", "density": "airy", "field_style": "underline",
        "button_style": "soft", "heading_align": "center",
    }
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
         "radius_px": None, "glow": None, "font": None, "heading_font": None, "title_scale": None, "title_case": None}


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
    field = {"id": "urgence", "label": "Urgence", "type": "radio", "required": True, "options": ["Oui"], "scale": None, "placeholder": None}

    def handler(request: httpx.Request) -> httpx.Response:
        context = json.loads(json.loads(request.content)["input"][0]["content"][0]["text"])
        attempts.append(context.get("correction_demandee", ""))
        if len(attempts) == 1:
            return _ops_response("Champ urgence ajouté.", [{"op": "add_field", "after": None, "field": field}])
        return _ops_response("Champ urgence corrigé.", [{"op": "add_field", "after": None, "field": {**field, "options": ["Oui", "Non"]}}])

    revision = revise_campaign(
        CURRENT,
        "Ajoute une question sur l'urgence",
        {"name": "Atelier Test"},
        selection={"element_ids": ["card"], "label": "Formulaire complet", "view": "form"},
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    )

    assert len(attempts) == 2
    assert "deux options" in attempts[1]
    assert next(field for field in revision["fields"] if field["id"] == "urgence")["options"] == ["Oui", "Non"]


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


PAGE = '<!doctype html><html lang="fr"><head><style>button{color:blue}</style></head><body><form data-sillage="form"><section data-sillage-region="hero"><h1>Contact</h1></section><input name="email" type="email"><div data-sillage="consent"></div><button>Envoyer</button></form></body></html>'


def _page_response(message: str, html: str, region: str | None = None) -> httpx.Response:
    return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"message": message, "html": html, "region": region})}]}]})


def test_page_revision_receives_full_context_and_returns_named_region():
    capture = "data:image/png;base64,aGVsbG8="
    reference = "data:image/png;base64,d29ybGQ="
    fragment = '<section data-sillage-region="hero"><h1>Nouveau titre</h1></section>'

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["text"]["format"]["name"] == "sillage_page"
        assert payload["store"] is False
        stable = json.loads(payload["input"][0]["content"][0]["text"])
        assert stable["brief_initial"] == {"prompt": "Une prise de contact", "context": "Atelier"}
        assert stable["existing_field_names"] == ["email"]
        assert stable["identity"]["name"] == "Atelier Test"
        assert "siret" not in json.dumps(stable)
        history = payload["input"][1]["content"]
        assert json.loads(history[0]["text"])["recent_exchanges"][-1]["text"] == "Rends le titre plus clair"
        assert history[1] == {"type": "input_image", "image_url": reference, "detail": "high"}
        current = payload["input"][2]["content"]
        context = json.loads(current[0]["text"])
        assert context["current_html"] == PAGE
        assert context["selection"]["region"] == "hero"
        assert context["selection"]["rect"] == {"x": 10, "y": 20, "width": 50, "height": 12}
        assert context["page_stats"]["visits"] == 30
        assert current[1] == {"type": "input_image", "image_url": capture, "detail": "high"}
        return _page_response("Titre clarifié.", fragment, "hero")

    result = revise_page(
        PAGE, "Rends le titre plus clair", {"name": "Atelier Test", "siret": "SECRET"},
        selection={"region": "hero", "rect": {"x": 10, "y": 20, "width": 50, "height": 12}},
        brief={"prompt": "Une prise de contact", "context": "Atelier"},
        stats={"visits": 30, "conversions": 9}, existing_names=["email", "consent"],
        history=[{"role": "user", "text": "Rends le titre plus clair", "images": [reference]}],
        screenshot_data_url=capture, api_key="test-key", transport=httpx.MockTransport(handler),
    )
    assert result == {"message": "Titre clarifié.", "html": fragment, "region": "hero"}


def test_page_revision_retries_invalid_region_as_full_page_without_resending_images():
    capture = "data:image/png;base64,aGVsbG8="
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            return _page_response("Titre changé.", '<section data-sillage-region="hero"><h1>Incomplet', "hero")
        context = json.loads(payload["input"][-1]["content"][0]["text"])
        assert context["region_interdite"] is True
        assert "fragment" in context["correction_demandee"]
        assert all(block["type"] != "input_image" for message in payload["input"] for block in message["content"])
        return _page_response("Page réécrite.", PAGE)

    result = revise_page(
        PAGE, "Change le titre", {"name": "Atelier Test"}, selection={"region": "hero"},
        history=[{"role": "user", "text": "Avant", "images": [capture]}],
        screenshot_data_url=capture, images=[capture], api_key="test-key", transport=httpx.MockTransport(handler),
    )
    assert len(requests) == 2
    assert result["region"] is None
    assert result["html"] == PAGE


def test_page_revision_accepts_style_region_and_rejects_mismatched_region():
    style = "<style>button{color:red}</style>"
    result = revise_page(
        PAGE, "Bouton rouge", "Atelier Test", selection={"region": "hero"},
        api_key="test-key", transport=httpx.MockTransport(lambda _: _page_response("Bouton rouge.", style, "style")),
    )
    assert result["html"] == style
    with pytest.raises(LunaAPIError, match="fragment"):
        revise_page(
            PAGE, "Change le titre", "Atelier Test", selection={"region": "hero"}, api_key="test-key",
            transport=httpx.MockTransport(lambda _: _page_response("Titre changé.", '<section data-sillage-region="other">Titre</section>', "hero")),
        )


def test_generate_page_requests_a_complete_document():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        stable = json.loads(payload["input"][0]["content"][0]["text"])
        assert stable["brief_initial"] == {
            "prompt": "Un contact",
            "context": "Artisan",
            "name": "Demande de rendez-vous",
            "description": "Un premier échange avec notre équipe.",
            "website_url": "https://atelier.example/",
        }
        assert payload["tools"] == [{"type": "web_search", "search_context_size": "low"}]
        assert payload["tool_choice"] == "required"
        current = json.loads(payload["input"][-1]["content"][0]["text"])
        assert current["current_html"] == ""
        return _page_response("Page créée.", PAGE)

    result = generate_page(
        "Un contact", "Atelier Test", form_name="Demande de rendez-vous",
        description="Un premier échange avec notre équipe.", context="Artisan",
        website_url="https://atelier.example/", api_key="test-key",
        transport=httpx.MockTransport(handler),
    )
    assert result["html"] == PAGE
    assert result["region"] is None


def test_merge_page_region_preserves_the_rest_of_the_document():
    fragment = '<section data-sillage-region="hero"><h1>Un autre titre</h1></section>'
    merged = merge_page_region(PAGE, fragment, "hero")
    assert fragment in merged
    assert '<input name="email" type="email">' in merged
    assert "button{color:blue}" in merged
    assert merge_page_region(merged, "<style>button{color:red}</style>", "style").count("<style>") == 1
    assert merge_page_region(PAGE, PAGE, None) == PAGE
    with pytest.raises(ValueError, match="style"):
        merge_page_region(PAGE, "<style>button{color:red}</style><style>body{color:black}</style>", "style")
    with pytest.raises(ValueError, match="absente"):
        merge_page_region(PAGE, fragment.replace('"hero"', '"missing"'), "missing")


def test_stream_page_revision_yields_preview_then_validated_final():
    output = json.dumps({"message": "Page enrichie.", "region": None, "html": PAGE})
    chunks = [output[index:index + 61] for index in range(0, len(output), 61)]
    events = "".join(f'data: {json.dumps({"type": "response.output_text.delta", "delta": chunk})}\n\n' for chunk in chunks)
    events += 'data: {"type":"response.completed","response":{}}\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=events)

    updates = list(stream_page_revision(
        PAGE, "Ajoute une section", "Atelier Test", selection={"view": "form"},
        api_key="test-key", transport=httpx.MockTransport(handler),
    ))
    assert any(update["type"] == "preview" and "<html" in update["html"] for update in updates)
    assert updates[-1] == {"type": "final", "message": "Page enrichie.", "region": None, "html": PAGE}


def test_stream_page_revision_resets_invalid_fragment_and_omits_images_on_retry():
    image = "data:image/png;base64,aGVsbG8="
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        output = ({"message": "Incomplet.", "region": "hero", "html": '<section data-sillage-region="hero">'}
                  if len(calls) == 1 else {"message": "Page corrigée.", "region": None, "html": PAGE})
        event = json.dumps({"type": "response.output_text.delta", "delta": json.dumps(output)})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=f"data: {event}\n\n")

    updates = list(stream_page_revision(
        PAGE, "Change le titre", "Atelier Test", selection={"region": "hero"},
        screenshot_data_url=image, images=[image], api_key="test-key", transport=httpx.MockTransport(handler),
    ))
    assert len(calls) == 2
    assert {"type": "reset"} in updates
    assert updates[-1]["type"] == "final"
    assert all(block["type"] != "input_image" for message in calls[1]["input"] for block in message["content"])


def test_page_revision_retries_once_when_the_page_describes_itself():
    """La première page se raconte : on la refuse en citant la phrase fautive."""
    bavarde = PAGE.replace("<h1>Contact</h1>", "<h1>Contact</h1><p>Un formulaire opt-in pour capter des prospects.</p>")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return _page_response("Page créée.", bavarde)
        return _page_response("Page créée.", PAGE)

    result = revise_page(
        "", "Crée une page de contact", {"name": "Atelier Test"},
        selection={"view": "form", "element_ids": [], "label": "Nouvelle page"},
        api_key="test-key", transport=httpx.MockTransport(handler),
    )
    assert len(requests) == 2
    reprise = json.dumps(requests[1], ensure_ascii=False)
    assert "opt-in" in reprise and "s'adresser aux visiteurs" in reprise
    assert result["html"] == PAGE


def test_page_revision_keeps_a_second_attempt_that_still_describes_itself():
    """Mieux vaut une page imparfaite qu'un refus sec : la reprise n'est pas rejouée."""
    bavarde = PAGE.replace("<h1>Contact</h1>", "<h1>Contact</h1><p>Un formulaire opt-in pour capter des prospects.</p>")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return _page_response("Page créée.", bavarde)

    result = revise_page(
        "", "Crée une page de contact", {"name": "Atelier Test"},
        selection={"view": "form", "element_ids": [], "label": "Nouvelle page"},
        api_key="test-key", transport=httpx.MockTransport(handler),
    )
    assert len(requests) == 2
    assert result["html"] == bavarde
