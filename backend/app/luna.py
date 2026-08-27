import re
import unicodedata
from uuid import uuid4


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return f"{value[:55]}-{uuid4().hex[:5]}"


def field(key: str, label: str, kind: str, required: bool = False, **extra):
    return {"id": key, "label": label, "type": kind, "required": required, **extra}


def generate_campaign(prompt: str, company_name: str) -> dict:
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
        "thank_you": {"title": "Merci {prenom} !", "message": "Votre réponse a bien été transmise. Notre équipe revient vers vous rapidement.", "action": "none", "button_label": "Retour au site", "button_url": "https://example.com"},
    }

