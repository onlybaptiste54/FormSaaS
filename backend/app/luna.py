import hashlib
import json
import logging
import re
import time
import unicodedata
from typing import Literal
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .luna_ops import LunaOps, OpsError, apply_ops, ops_json_schema, validate_state


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
    heading_font: Literal["sans", "grotesk", "serif", "mono"]
    title_scale: float = Field(ge=0.7, le=1.8)
    title_case: Literal["normal", "uppercase"]


class LunaDesign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layout: Literal["card", "split", "minimal"]
    density: Literal["compact", "comfortable", "airy"]
    field_style: Literal["outline", "filled", "underline"]
    button_style: Literal["solid", "outline", "soft"]
    heading_align: Literal["left", "center"]
    style: LunaStyle


class LunaContent(BaseModel):
    """Textes de l'ossature du formulaire, autrefois codés en dur dans le rendu."""

    model_config = ConfigDict(extra="forbid")

    eyebrow: str = Field(min_length=2, max_length=40)
    submit_label: str = Field(min_length=2, max_length=40)
    trust_note: str = Field(min_length=10, max_length=180)


class LunaCampaign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=90)
    description: str = Field(min_length=10, max_length=260)
    kind: Literal["contact", "survey", "information"]
    fields: list[LunaField] = Field(min_length=1, max_length=5)
    design: LunaDesign
    content: LunaContent
    thank_you_title: str = Field(min_length=3, max_length=100)
    thank_you_message: str = Field(min_length=10, max_length=260)


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
- Choisis la structure (layout, density, field_style, button_style, heading_align) ET toutes les valeurs de style : les couleurs et les arrondis viennent uniquement de style.
- Le style est libre : sobre, chaleureux, sombre, futuriste ou verre dépoli selon le brief et l'identité. Ose une direction affirmée quand la demande le suggère, ne retombe pas systématiquement sur du neutre.
- Pour un rendu verre / glassmorphism : dégradé de page sombre, surface_alpha entre 0.08 et 0.25, blur_px entre 16 et 32, border_alpha autour de 0.3, glow élevé.
- Pour un rendu clair et sobre : surface_alpha proche de 1, blur_px à 0, glow bas.
- heading_font, title_scale (0,7 à 1,8) et title_case donnent le caractère des titres : c'est là que se joue une direction artistique affirmée.
- Contrainte non négociable : le contraste doit rester lisible. ink doit trancher franchement sur surface, et accent_ink sur accent.
- N'utilise jamais de CSS, HTML, URL d'image ou valeur libre pour le design.
- Le titre de remerciement peut contenir {prenom} si un champ de nom est présent.
- Les images jointes sont des références visuelles fournies par l'entreprise : inspire-t'en, n'en extrais aucune donnée personnelle.
- content.eyebrow est un sur-titre court en majuscules, submit_label le texte du bouton d'envoi, trust_note une phrase rassurante sur l'usage des données.
"""

LUNA_REVISION_INSTRUCTIONS = """Tu es Luna, directrice artistique et experte UX de formulaires français.
Tu reçois l'état du formulaire, la zone que l'utilisateur a encadrée, sa demande, les derniers échanges et parfois une capture de cette zone.

Tu ne réécris jamais le formulaire : tu renvoies un message court en français et la liste des opérations à appliquer.

Contraintes impératives :
- N'agis que sur ce qui est demandé. Aucune opération superflue.
- selection.element_ids dit ce que l'utilisateur a encadré : traite ces éléments en priorité.
- set_text change un texte : titre (name), description, sur-titre (eyebrow), bouton (submit_label), note de confiance (trust_note), remerciement (thanks_title, thanks_message, thanks_button).
- set_theme change les couleurs, les formes et la typographie : heading_font, title_scale et title_case agissent sur les titres. set_structure la mise en page ainsi que l'affichage du bloc de marque (brand_display, brand_size). Le fichier du logo lui-même se remplace dans les paramètres ou par un double-clic sur le logo : dis-le si on te demande de le changer. Ose une direction affirmée quand la demande le suggère.
- Le contraste est vérifié par le serveur : ink doit trancher franchement sur surface, et accent_ink sur accent (au moins 4,5:1). Une opération refusée te revient pour correction.
- 5 champs métier maximum. Ne touche jamais au consentement : le serveur gère sa version légale.
- Ne change jamais le type d'un champ existant : des réponses y sont déjà rattachées. Retire-le et ajoute-en un autre si c'est vraiment voulu.
- L'action, l'URL et le code promo de la page de remerciement se règlent dans le tunnel : tu ne peux pas les modifier. Dis-le si on te le demande.
- La première image est la capture de la zone encadrée, avec son environnement : le trait coloré entoure exactement la zone visée. Les images suivantes sont jointes par l'utilisateur comme références. N'en extrais aucune donnée personnelle.
- Aucun CSS, HTML, script, URL d'image ni valeur hors du schéma.
- Si la demande sort de ce que tu peux faire (image de fond, police hors liste, mise en page inédite), renvoie l'opération ask : dis dans message que ce n'est pas possible aujourd'hui, puis propose la modification la plus proche que tu sais faire. Le seul autre écran qui existe est l'onglet Tunnel, pour l'action, l'URL et le code promo du remerciement : ne renvoie jamais l'utilisateur ailleurs.
- message décrit en une phrase ce qui a été appliqué, sans jargon technique.
"""


class BrandProfile(BaseModel):
    """Identité de marque déduite d'une charte : uniquement des valeurs validées."""

    model_config = ConfigDict(extra="forbid")

    palette: list[str] = Field(min_length=2, max_length=6)
    font: Literal["sans", "grotesk", "serif", "mono"]
    tone: str = Field(min_length=3, max_length=60)
    rules_do: list[str] = Field(max_length=5)
    rules_avoid: list[str] = Field(max_length=5)
    summary: str = Field(min_length=10, max_length=240)


LUNA_BRAND_INSTRUCTIONS = """Tu es Luna, directrice artistique. On te montre la charte graphique d'une entreprise : logo, pages de charte ou capture du site.

Déduis-en un profil de marque exploitable pour des formulaires :
- palette : 2 à 6 couleurs hexadécimales réellement présentes, de la plus structurante à la plus secondaire.
- font : la police de la liste qui s'approche le plus de celle de la marque.
- tone : deux ou trois mots en français (par exemple « chaleureux et direct »).
- rules_do et rules_avoid : consignes courtes et concrètes, en français, tirées de ce que tu vois.
- summary : une phrase qui résume l'identité.
N'invente rien qui ne soit pas visible. Ne décris aucune personne présente sur les images.
"""


EYEBROWS = {"contact": "PRENONS CONTACT", "survey": "VOTRE AVIS COMPTE", "information": "INSCRIPTION"}


def default_content(kind: str = "contact") -> dict:
    return {
        "eyebrow": EYEBROWS.get(kind, EYEBROWS["contact"]),
        "submit_label": "Envoyer ma réponse",
        "trust_note": "Vos données sont protégées et utilisées uniquement pour traiter votre demande.",
    }


def default_design() -> dict:
    return {
        "layout": "card",
        "density": "comfortable",
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
        "content": default_content(kind),
        "thank_you": {"title": "Merci {prenom} !", "message": "Votre réponse a bien été transmise. Notre équipe revient vers vous rapidement.", "action": "none", "button_label": "Retour au site", "button_url": ""},
    }


def analyze_brand(
    images: list[str],
    identity: str | dict,
    *,
    notes: str = "",
    api_key: str,
    model: str = "gpt-5.4-mini",
    timeout_seconds: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Propose un profil de marque à partir d'images de charte, à valider ensuite."""
    if not api_key:
        raise LunaAPIError("Luna n'est pas connectée : renseignez la clé du service d'IA.")
    if not images:
        raise LunaAPIError("Ajoutez au moins une image de votre charte.")

    safe_identity = _safe_identity(identity)
    content: list[dict] = [{"type": "input_text", "text": json.dumps({"identity": safe_identity, "notes": notes}, ensure_ascii=False)}]
    for image in images[:4]:
        content.append({"type": "input_image", "image_url": _validate_screenshot(image), "detail": "high"})

    request_payload = {
        "model": model,
        "instructions": LUNA_BRAND_INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
        "text": {"format": {"type": "json_schema", "name": "sillage_brand_profile", "strict": True, "schema": BrandProfile.model_json_schema()}},
        "max_output_tokens": 600,
        "store": False,
        "safety_identifier": hashlib.sha256(str(safe_identity.get("name") or "sillage-user").encode()).hexdigest()[:32],
    }

    try:
        profile = BrandProfile.model_validate_json(_output_text(_request_openai(
            request_payload, api_key=api_key, timeout_seconds=timeout_seconds, transport=transport,
        )))
    except ValidationError as exc:
        logger.warning("Luna brand analysis failed: %s", type(exc).__name__)
        raise LunaAPIError("Luna n'a pas réussi à lire cette charte. Essayez avec une image plus lisible.") from exc
    return profile.model_dump()


def _company_name(identity: str | dict) -> str:
    if isinstance(identity, str):
        return identity
    return str(identity.get("name") or "votre entreprise")


def _safe_identity(identity: str | dict) -> dict:
    if isinstance(identity, str):
        return {"name": identity}
    allowed = ("name", "sector", "tone", "primary_color", "accent_color", "brand")
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
        "content": result.content.model_dump(),
        "thank_you": {
            "title": result.thank_you_title,
            "message": result.thank_you_message,
            "action": "none",
            "button_label": "Retour au site",
            "button_url": "",
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
    context: str = "",
    images: list[str] | None = None,
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
    brief = {"brief": prompt, "identity": identity_payload}
    if context:
        brief["context"] = context
    content: list[dict] = [{"type": "input_text", "text": json.dumps(brief, ensure_ascii=False)}]
    for image in (images or [])[:2]:
        content.append({"type": "input_image", "image_url": _validate_screenshot(image), "detail": "high"})
    request_payload = {
        "model": model,
        "instructions": LUNA_INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
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


def _revision_request(state: dict, instruction: str, identity: dict, *, selection: dict, history: list[dict], screenshot: str | None, images: list[str], model: str, correction: str = "") -> dict:
    user_context = {
        "instruction": instruction,
        "selection": selection,
        "recent_exchanges": history[-6:],
        "current_form": state,
        "identity": identity,
    }
    if state.get("brief"):
        user_context["brief_initial"] = state.pop("brief")
    if correction:
        user_context["correction_demandee"] = correction
    content = [{"type": "input_text", "text": json.dumps(user_context, ensure_ascii=False)}]
    if screenshot:
        content.append({"type": "input_image", "image_url": screenshot, "detail": "high"})
    # Images jointes au message : capture externe, inspiration, photo.
    for image in images[:3]:
        content.append({"type": "input_image", "image_url": image, "detail": "high"})
    safety_source = str(identity.get("name") or "sillage-user")
    return {
        "model": model,
        "instructions": LUNA_REVISION_INSTRUCTIONS,
        "input": [{"role": "user", "content": content}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sillage_form_ops",
                "strict": True,
                "schema": ops_json_schema(),
            }
        },
        "max_output_tokens": 1600,
        "store": False,
        "safety_identifier": hashlib.sha256(safety_source.encode()).hexdigest()[:32],
    }


def revise_campaign(
    current_campaign: dict,
    instruction: str,
    identity: str | dict,
    *,
    selection: dict,
    history: list[dict] | None = None,
    screenshot_data_url: str | None = None,
    images: list[str] | None = None,
    api_key: str,
    model: str = "gpt-5.4-mini",
    timeout_seconds: float = 30.0,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    """Applique une demande de modification sous forme d'operations validees.

    Luna renvoie un message et quelques operations ; le serveur les applique,
    les verifie (contraste, identifiants, nombre de champs) et, si un garde-fou
    saute, redonne une chance au modele avec l'erreur en clair.
    """
    if not api_key:
        raise LunaAPIError("Luna n'est pas connectée : renseignez la clé du service d'IA.")

    state = {
        "name": current_campaign.get("name"),
        "description": current_campaign.get("description"),
        "kind": current_campaign.get("kind"),
        "fields": current_campaign.get("fields", []),
        "design": current_campaign.get("design") or default_design(),
        "content": current_campaign.get("content") or default_content(current_campaign.get("kind", "contact")),
        "thank_you": current_campaign.get("thank_you") or {},
    }
    sent_state = {**state, "fields": [item for item in state["fields"] if item.get("type") != "consent"]}
    safe_identity = _safe_identity(identity)
    screenshot = _validate_screenshot(screenshot_data_url)
    attachments = [_validate_screenshot(image) or "" for image in (images or [])]

    correction = ""
    started = time.monotonic()
    for attempt in (1, 2):
        payload = _request_openai(
            _revision_request(sent_state, instruction, safe_identity, selection=selection, history=history or [], screenshot=screenshot, images=[image for image in attachments if image], model=model, correction=correction),
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )
        try:
            result = LunaOps.model_validate_json(_output_text(payload))
            revised, touched = apply_ops(state, result.ops)
            validate_state(revised, state)
        except (ValidationError, OpsError) as exc:
            correction = str(exc)
            logger.warning("Luna revision refused (attempt %s): %s", attempt, correction[:200])
            if attempt == 2:
                raise LunaAPIError(f"Luna n'a pas pu appliquer cette modification : {correction}") from exc
            continue

        usage = payload.get("usage") or {}
        logger.info(
            "Luna revision applied in %.1fs, attempt %s, %s ops, %s tokens",
            time.monotonic() - started, attempt, len(result.ops), usage.get("total_tokens", "?"),
        )
        return {
            **revised,
            "assistant_message": result.message,
            "touched": touched,
            "ops": [operation.model_dump(exclude_none=True) for operation in result.ops],
        }

    raise LunaAPIError("Luna n'a pas pu appliquer cette modification. Reformulez votre demande.")
