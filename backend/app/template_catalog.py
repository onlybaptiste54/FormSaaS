from copy import deepcopy

from .luna import default_content


CURATED_TEMPLATES = [
    {
        "key": "contact-artisan",
        "name": "Contact artisan",
        "category": "Contact",
        "description": "Qualification courte pour une intervention, son urgence et le rappel.",
        "minutes": 2,
        "accent": "#2F6B4F",
        "fields": [
            {"id": "name", "label": "Nom et prénom", "type": "text", "required": True, "placeholder": "Votre nom"},
            {"id": "phone", "label": "Téléphone", "type": "tel", "required": True, "placeholder": "06 00 00 00 00"},
            {"id": "need", "label": "Type d’intervention", "type": "select", "required": True, "options": ["Dépannage", "Installation", "Entretien", "Autre"]},
            {"id": "urgent", "label": "Est-ce urgent ?", "type": "radio", "required": True, "options": ["Oui", "Non"]},
        ],
        "design": {"layout": "card", "background": "warm", "density": "comfortable", "radius": "rounded", "field_style": "outline", "button_style": "solid", "heading_align": "left"},
    },
    {
        "key": "satisfaction-client",
        "name": "Satisfaction client",
        "category": "Sondage",
        "description": "Mesurez la qualité perçue sans fatiguer vos clients.",
        "minutes": 1,
        "accent": "#665C9A",
        "fields": [
            {"id": "rating", "label": "Comment évaluez-vous votre expérience ?", "type": "rating", "required": True, "scale": 5},
            {"id": "recommend", "label": "Nous recommanderiez-vous ?", "type": "radio", "required": True, "options": ["Oui", "Peut-être", "Non"]},
            {"id": "comment", "label": "Une suggestion pour progresser ?", "type": "textarea", "required": False},
        ],
        "design": {"layout": "minimal", "background": "mist", "density": "airy", "radius": "rounded", "field_style": "filled", "button_style": "soft", "heading_align": "center"},
    },
    {
        "key": "inscription-evenement",
        "name": "Inscription événement",
        "category": "Information",
        "description": "Une inscription fluide pour ateliers, portes ouvertes et rencontres.",
        "minutes": 2,
        "accent": "#D96C55",
        "fields": [
            {"id": "name", "label": "Nom et prénom", "type": "text", "required": True},
            {"id": "email", "label": "Email", "type": "email", "required": True},
            {"id": "guests", "label": "Nombre de participants", "type": "number", "required": True},
            {"id": "message", "label": "Une précision ?", "type": "textarea", "required": False},
        ],
        "design": {"layout": "split", "background": "white", "density": "comfortable", "radius": "subtle", "field_style": "underline", "button_style": "solid", "heading_align": "left"},
    },
    {
        "key": "brief-decouverte",
        "name": "Brief découverte",
        "category": "Contact",
        "description": "Cadrez un premier échange commercial avec les bonnes informations.",
        "minutes": 3,
        "accent": "#347A78",
        "fields": [
            {"id": "name", "label": "Votre nom", "type": "text", "required": True},
            {"id": "email", "label": "Email professionnel", "type": "email", "required": True},
            {"id": "objective", "label": "Quel est votre objectif principal ?", "type": "textarea", "required": True},
            {"id": "timeline", "label": "Quand souhaitez-vous avancer ?", "type": "select", "required": True, "options": ["Dès maintenant", "Sous 1 mois", "Sous 3 mois", "Je me renseigne"]},
        ],
        "design": {"layout": "card", "background": "ink", "density": "airy", "radius": "rounded", "field_style": "filled", "button_style": "soft", "heading_align": "left"},
    },
    {
        "key": "retour-experience",
        "name": "Retour d’expérience",
        "category": "Sondage",
        "description": "Recueillez un retour précis après une prestation ou une livraison.",
        "minutes": 2,
        "accent": "#B18735",
        "fields": [
            {"id": "rating", "label": "Votre note globale", "type": "rating", "required": True, "scale": 5},
            {"id": "highlight", "label": "Qu’avez-vous le plus apprécié ?", "type": "textarea", "required": False},
            {"id": "improvement", "label": "Que pourrions-nous améliorer ?", "type": "textarea", "required": False},
        ],
        "design": {"layout": "card", "background": "warm", "density": "compact", "radius": "pill", "field_style": "outline", "button_style": "outline", "heading_align": "center"},
    },
    {
        "key": "rappel-conseiller",
        "name": "Être rappelé",
        "category": "Contact",
        "description": "Un formulaire très court pour transformer une visite en conversation.",
        "minutes": 1,
        "accent": "#456988",
        "fields": [
            {"id": "name", "label": "Nom", "type": "text", "required": True},
            {"id": "phone", "label": "Téléphone", "type": "tel", "required": True},
            {"id": "slot", "label": "Meilleur moment pour vous joindre", "type": "select", "required": False, "options": ["Matin", "Midi", "Après-midi", "Fin de journée"]},
        ],
        "design": {"layout": "minimal", "background": "white", "density": "compact", "radius": "subtle", "field_style": "underline", "button_style": "solid", "heading_align": "left"},
    },
]


DEFAULT_THANK_YOU = {
    "title": "Merci {prenom} !",
    "message": "Votre réponse a bien été transmise. Notre équipe revient vers vous rapidement.",
    "action": "none",
    "button_label": "Retour au site",
    "button_url": "",
}


KIND_BY_CATEGORY = {"Contact": "contact", "Sondage": "survey", "Information": "information"}


def template_kind(category: str) -> str:
    return KIND_BY_CATEGORY.get(category, "contact")


def curated_template(key: str) -> dict | None:
    item = next((template for template in CURATED_TEMPLATES if template["key"] == key), None)
    return deepcopy(item) if item else None


def template_payload(template: dict) -> dict:
    result = deepcopy(template)
    result["thank_you"] = deepcopy(DEFAULT_THANK_YOU)
    result["content"] = default_content(template_kind(result.get("category", "Contact")))
    result["field_count"] = len(result["fields"])
    return result


def campaign_fields(fields: list[dict], company_name: str) -> list[dict]:
    result = deepcopy(fields[:5])
    result.append({
        "id": "consent",
        "label": f"J'accepte que {company_name} utilise mes informations pour répondre à ma demande.",
        "type": "consent",
        "required": True,
    })
    return result
