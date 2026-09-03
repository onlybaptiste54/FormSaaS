import hashlib
import json
import logging
import re
import unicodedata
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


logger = logging.getLogger(__name__)


class LunaAPIError(RuntimeError):
    """Raised when OpenAI is configured but cannot produce a valid campaign."""


class LunaField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    label: str = Field(min_length=2, max_length=140)
    type: Literal["text", "email", "tel", "textarea", "number", "date", "radio", "select", "rating"]
    required: bool
    options: list[str] = Field(max_length=8)
    scale: int | None = Field(ge=3, le=10)
    placeholder: str | None = Field(max_length=100)


HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class LunaStyle(BaseModel):
    """Identité visuelle libre, exprimée uniquement en valeurs validées.

    Rien n'est interprété comme de la syntaxe CSS : chaque champ est une couleur
    hexadécimale, un nombre borné ou une police de la liste. Le rendu applique
    ces valeurs en variables CSS.
    """

    model_config = ConfigDict(extra="forbid")

    page_from: str = Field(pattern=HEX_COLOR)
    page_to: str = Field(pattern=HEX_COLOR)
    surface: str = Field(pattern=HEX_COLOR)
    surface_alpha: float = Field(ge=0.05, le=1)
    border: str = Field(pattern=HEX_COLOR)
    border_alpha: float = Field(ge=0, le=1)
    ink: str = Field(pattern=HEX_COLOR)
    ink_soft: str = Field(pattern=HEX_COLOR)
    accent: str = Field(pattern=HEX_COLOR)
    accent_ink: str = Field(pattern=HEX_COLOR)
    blur_px: int = Field(ge=0, le=40)
    radius_px: int = Field(ge=0, le=48)
    glow: float = Field(ge=0, le=1)
    font: Literal["sans", "grotesk", "serif", "mono"]


class LunaDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: Literal["card", "split", "minimal"]
    background: Literal["warm", "mist", "white", "ink"]
    density: Literal["compact", "comfortable", "airy"]
    radius: Literal["subtle", "rounded", "pill"]
    field_style: Literal["outline", "filled", "underline"]
    button_style: Literal["solid", "outline", "soft"]
    heading_align: Literal["left", "center"]
    style: LunaStyle


class LunaCampaign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=90)
    description: str = Field(min_length=10, max_length=260)
    kind: Literal["contact", "survey", "information"]
    fields: list[LunaField] = Field(min_length=1, max_length=5)
    design: LunaDesign
    thank_you_title: str = Field(min_length=3, max_length=100)
    thank_you_message: str = Field(min_length=10, max_length=260)


class LunaRevision(LunaCampaign):
    assistant_message: str = Field(min_length=3, max_length=240)


LUNA_INSTRUCTIONS = """Tu es Luna, experte française en formulaires MOFU courts et conformes au RGPD.
À partir du brief et de l'identité visuelle fournis, conçois une campagne utile, claire, naturelle et visuellement cohérente en français.

Contraintes impératives :
- Produis uniquement les données demandées par le schéma JSON.
- La campagne est de type contact, sondage ou information. Ne crée jamais de formulaire de devis.
- Crée entre 1 et 5 champs métier maximum, dans l'ordre le plus fluide.
- N'ajoute aucune case de consentement : le serveur l'injecte avec un texte légal contrôlé.
- Utilise uniquement les types autorisés. Pour radio/select, fournis 2 à 8 options ; sinon options doit être [].
- scale vaut un entier de 3 à 10 uniquement pour rating, sinon null.
- placeholder est une aide courte ou null. Aucun dark pattern, aucune donnée sensible inutile.
- Le ton et les textes doivent correspondre à l'identité de l'entreprise.
- Choisis tous les tokens de design ET toutes les valeurs de style demandés.
- Le style est libre : sobre, chaleureux, sombre, futuriste ou verre dépoli selon le brief et l'identité. Ose une direction affirmée quand la demande le suggère, ne retombe pas systématiquement sur du neutre.
- Pour un rendu verre / glassmorphism : dégradé de page sombre, surface_alpha entre 0.08 et 0.25, blur_px entre 16 et 32, border_alpha autour de 0.3, glow élevé.
- Pour un rendu clair et sobre : surface_alpha proche de 1, blur_px à 0, glow bas.
- Contrainte non négociable : le contraste doit rester lisible. ink doit trancher franchement sur surface, et accent_ink sur accent.
- N'utilise jamais de CSS, HTML, URL d'image ou valeur libre pour le design.
- Le titre de remerciement peut contenir {prenom} si un champ de nom est présent.
"""

LUNA_REVISION_INSTRUCTIONS = """Tu es Luna, directrice artistique et experte UX de formulaires français.
Tu reçois le formulaire actuel, une zone sélectionnée, une demande de modification et parfois une capture PNG de cette zone.

Contraintes impératives :
- Retourne toujours le formulaire COMPLET, tous les tokens de design et toutes les valeurs de style, même si une seule zone change.
- Le style est libre dans les bornes du schéma : couleurs, flou, rayons, glow et police. Applique franchement la direction demandée (futuriste, verre dépoli, sombre, minimal) plutôt qu'un ajustement timide.
- Garde toujours un contraste lisible entre ink et surface, et entre accent_ink et accent.
- Modifie en priorité la zone sélectionnée et préserve tout ce que l'utilisateur n'a pas demandé de changer.
- Interprète la capture uniquement comme référence visuelle du formulaire vide. N'en extrais aucune donnée personnelle.
- La campagne reste de type contact, sondage ou information. Ne crée jamais de formulaire de devis.
- Garde entre 1 et 5 champs métier. N'ajoute pas de consentement : le serveur réinjecte sa version contrôlée.
- Aucun CSS, HTML, script, URL d'image ou token hors des valeurs autorisées.
- Réponds en français avec assistant_message : une phrase courte expliquant ce qui a été appliqué.
- N'annonce jamais une modification que le schéma ne permet pas. Si la demande sort de ce que tu peux produire (image de fond, police hors liste, mise en page inédite), dis-le explicitement dans assistant_message et indique ce que tu as fait de plus proche.
"""


def default_design() -> dict:
    return {
        "layout": "card",
        "background": "warm",
        "density": "comfortable",
        "radius": "rounded",
        "field_style": "outline",
        "button_style": "solid",
        "heading_align": "left",
    }

def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return f"{value[:55]}-{uuid4().hex[:5]}"


def field(key: str, label: str, kind: str, required: bool = False, **extra):
    return {"id": key, "label": label, "type": kind, "required": required, **extra}


def _generate_campaign_local(prompt: str, company_name: str) -> dict:
    text = prompt.lower()
    is_survey = any(w in text for w in ("sondage", "satisfaction", "avis", "nps", "note"))
    is_event = any(w in text for w in ("événement", "evenement", "inscription", "atelier"))
    is_btp = any(w in text for w in ("chantier", "visite", "photo", "btp"))

    if is_survey:
        name = "Satisfaction client"
        description = "Aidez-nous à améliorer votre expérience en partageant votre avis."
        fields = [
            field("rating", "Comment évaluez-vous votre expérience ?", "rating", True, scale=5),
            field("recommend", "Nous recommanderiez-vous à un proche ?", "radio", True, options=["Oui", "Peut-être", "Non"]),
            field("comment", "Un commentaire à nous partager ?", "textarea"),
            field("email", "Votre email (facultatif)", "email"),
        ]
        kind = "survey"
    elif is_event:
        name = "Inscription événement"
        description = "Réservez votre place en quelques instants."
        fields = [field("name", "Nom et prénom", "text", True), field("email", "Email", "email", True), field("phone", "Téléphone", "tel"), field("guests", "Nombre de participants", "number"), field("message", "Une précision ?", "textarea")]
        kind = "information"
    elif is_btp:
        name = "Visite de chantier"
        description = "Centralisez les informations essentielles de chaque visite."
        fields = [field("name", "Nom du client", "text", True), field("site", "Adresse du chantier", "text", True), field("date", "Date de visite", "date", True), field("comment", "Observations", "textarea", True), field("photo", "Photos du chantier", "file")]
        kind = "information"
    else:
        subject = "votre demande"
        if "plomb" in text or "urgence" in text:
            subject = "votre intervention"
        elif "laser" in text or "épilation" in text:
            subject = "votre projet d'épilation"
        name = "Demande de contact"
        description = f"Parlez-nous de {subject}. L'équipe {company_name} vous répond rapidement."
        fields = [field("name", "Nom et prénom", "text", True), field("email", "Email", "email", True), field("phone", "Téléphone", "tel", True)]
        if "urgence" in text or "intervention" in text:
            fields.append(field("need", "Type d'intervention", "select", True, options=["Dépannage", "Installation", "Entretien", "Autre"]))
            fields.append(field("urgent", "Est-ce urgent ?", "radio", True, options=["Oui", "Non"]))
        else:
            fields.append(field("message", "Comment pouvons-nous vous aider ?", "textarea", True))
        kind = "contact"

    fields = fields[:5]
    fields.append(field("consent", f"J'accepte que {company_name} utilise mes informations pour répondre à ma demande.", "consent", True))
    return {
        "name": name,
        "slug": slugify(name),
        "description": description,
        "kind": kind,
        "fields": fields,
        "design": default_design(),
        "thank_you": {"title": "Merci {prenom} !", "message": "Votre réponse a bien été transmise. Notre équipe revient vers vous rapidement.", "action": "none", "button_label": "Retour au site", "button_url": "https://example.com"},
    }


def _company_name(identity: str | dict) -> str:
    if isinstance(identity, str):
        return identity
    return str(identity.get("name") or "votre entreprise")


def _safe_identity(identity: str | dict) -> dict:
    if isinstance(identity, str):
        return {"name": identity}
    allowed = ("name", "sector", "tone", "primary_color", "accent_color")
    return {key: identity[key] for key in allowed if identity.get(key)}


def _output_text(payload: dict) -> str:
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"]
    raise LunaAPIError("OpenAI n'a retourné aucun formulaire exploitable.")


def _normalize_ai_campaign(result: LunaCampaign, company_name: str) -> dict:
    fields = []
    seen_ids: set[str] = set()
    for generated_field in result.fields:
        data = generated_field.model_dump()
        field_id = data["id"]
        if field_id in seen_ids:
            field_id = f"{field_id}_{len(fields) + 1}"
        seen_ids.add(field_id)
        data["id"] = field_id
        if not data["options"]:
            data.pop("options")
        if data["scale"] is None:
            data.pop("scale")
        if data["placeholder"] is None:
            data.pop("placeholder")
        fields.append(data)

    fields.append(field(
        "consent",
        f"J'accepte que {company_name} utilise mes informations pour répondre à ma demande.",
        "consent",
        True,
    ))
    return {
        "name": result.name,
        "slug": slugify(result.name),
        "description": result.description,
        "kind": result.kind,
        "fields": fields,
        "design": result.design.model_dump(),
        "thank_you": {
            "title": result.thank_you_title,
            "message": result.thank_you_message,
            "action": "none",
            "button_label": "Retour au site",
            "button_url": "https://example.com",
        },
    }


def _request_openai(
    request_payload: dict,
    *,
    api_key: str,
    timeout_seconds: float,
    transport: httpx.BaseTransport | None,
) -> dict:
    try:
        with httpx.Client(timeout=timeout_seconds, transport=transport) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=request_payload,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("OpenAI rejected Luna generation with status %s", exc.response.status_code)
        if exc.response.status_code == 401:
            raise LunaAPIError("La clé OpenAI de Luna est invalide.") from exc
        if exc.response.status_code == 429:
            raise LunaAPIError("Luna a atteint sa limite OpenAI. Réessayez dans un instant.") from exc
        raise LunaAPIError("Luna est temporairement indisponible côté OpenAI.") from exc
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Luna request failed: %s", type(exc).__name__)
        raise LunaAPIError("Luna est temporairement indisponible côté OpenAI.") from exc


def _validate_screenshot(data_url: str | None) -> str | None:
    if not data_url:
        return None
    if not re.match(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$", data_url):
        raise LunaAPIError("La capture envoyée à Luna n'est pas une image valide.")
    return data_url


def generate_campaign(
    prompt: str,
    identity: str | dict,
    *,
    api_key: str = "",
    model: str = "gpt-5.4-mini",
    timeout_seconds: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Generate with OpenAI when configured, otherwise keep the local demo usable."""
    company_name = _company_name(identity)
    if not api_key:
        return _generate_campaign_local(prompt, company_name)

    identity_payload = _safe_identity(identity)
    safety_source = str(identity_payload.get("name") or "sillage-user")
    request_payload = {
        "model": model,
        "instructions": LUNA_INSTRUCTIONS,
        "input": json.dumps({"brief": prompt, "identity": identity_payload}, ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sillage_campaign",
                "strict": True,
                "schema": LunaCampaign.model_json_schema(),
            }
        },
        "max_output_tokens": 1600,
        "store": False,
        "safety_identifier": hashlib.sha256(safety_source.encode()).hexdigest()[:32],
    }

    try:
        result = LunaCampaign.model_validate_json(_output_text(_request_openai(
            request_payload,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )))
    except (ValidationError, LunaAPIError) as exc:
        logger.warning("Luna generation failed: %s", type(exc).__name__)
        if isinstance(exc, LunaAPIError):
            raise
        raise LunaAPIError("Luna n'a pas pu générer un formulaire valide. Réessayez.") from exc

    return _normalize_ai_campaign(result, company_name)


def revise_campaign(
    current_campaign: dict,
    instruction: str,
    identity: str | dict,
    *,
    selection: dict,
    screenshot_data_url: str | None,
    api_key: str,
    model: str = "gpt-5.4-mini",
    timeout_seconds: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Revise content and safe design tokens using optional visual context."""
    if not api_key:
        raise LunaAPIError("Ajoutez OPENAI_API_KEY dans votre fichier .env pour modifier le design avec Luna.")

    company_name = _company_name(identity)
    business_fields = [item for item in current_campaign.get("fields", []) if item.get("type") != "consent"][:5]
    current_payload = {
        "name": current_campaign.get("name"),
        "description": current_campaign.get("description"),
        "kind": current_campaign.get("kind"),
        "fields": business_fields,
        "design": current_campaign.get("design") or default_design(),
        "thank_you": current_campaign.get("thank_you"),
    }
    user_context = {
        "instruction": instruction,
        "selection": selection,
        "current_campaign": current_payload,
        "identity": _safe_identity(identity),
    }
    content = [{"type": "input_text", "text": json.dumps(user_context, ensure_ascii=False)}]
    screenshot = _validate_screenshot(screenshot_data_url)
    if screenshot:
        content.append({"type": "input_image", "image_url": screenshot, "detail": "low"})

    safety_source = str(_safe_identity(identity).get("name") or "sillage-user")
    request_payload = {
        "model": model,
        "instructions": LUNA_REVISION_INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sillage_campaign_revision",
                "strict": True,
                "schema": LunaRevision.model_json_schema(),
            }
        },
        "max_output_tokens": 1800,
        "store": False,
        "safety_identifier": hashlib.sha256(safety_source.encode()).hexdigest()[:32],
    }

    try:
        result = LunaRevision.model_validate_json(_output_text(_request_openai(
            request_payload,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )))
    except (ValidationError, LunaAPIError) as exc:
        logger.warning("Luna revision failed: %s", type(exc).__name__)
        if isinstance(exc, LunaAPIError):
            raise
        raise LunaAPIError("Luna n'a pas pu appliquer cette modification. Reformulez votre demande.") from exc

    normalized = _normalize_ai_campaign(result, company_name)
    normalized["assistant_message"] = result.assistant_message
    return normalized
