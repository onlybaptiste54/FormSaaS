"""Opérations de Luna : ce qu'elle a le droit de changer, et comment on l'applique.

Luna ne réécrit plus le formulaire entier à chaque message. Elle renvoie une
courte liste d'opérations typées, que le serveur applique lui-même puis valide.
C'est plus rapide, ça évite les dérives, et chaque étape reste annulable.
"""

from copy import deepcopy
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


HEX_COLOR = r"^#[0-9a-fA-F]{6}$"
FIELD_ID = r"^[a-z][a-z0-9_]{1,39}$"
FIELD_TYPES = ("text", "email", "tel", "textarea", "number", "date", "radio", "select", "rating")

# Cible d'un texte -> (emplacement dans l'etat, identifiant du noeud rendu).
TEXT_TARGETS = {
    "name": (("name",), "title"),
    "description": (("description",), "description"),
    "eyebrow": (("content", "eyebrow"), "eyebrow"),
    "submit_label": (("content", "submit_label"), "submit"),
    "trust_note": (("content", "trust_note"), "trust"),
    "thanks_title": (("thank_you", "title"), "thanks.title"),
    "thanks_message": (("thank_you", "message"), "thanks.message"),
    "thanks_button": (("thank_you", "button_label"), "thanks.button"),
}

MAX_BUSINESS_FIELDS = 5


class OpsError(ValueError):
    """Une opération est refusée : le message explique quoi corriger."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewField(Strict):
    id: str = Field(pattern=FIELD_ID)
    label: str = Field(min_length=2, max_length=140)
    type: Literal[FIELD_TYPES]
    required: bool
    options: list[str] = Field(max_length=8)
    scale: int | None = Field(ge=3, le=10)
    placeholder: str | None = Field(max_length=100)


class SetText(Strict):
    op: Literal["set_text"]
    target: Literal[tuple(TEXT_TARGETS)]
    value: str = Field(min_length=1, max_length=400)


class UpdateField(Strict):
    op: Literal["update_field"]
    id: str = Field(pattern=FIELD_ID)
    label: str | None = Field(min_length=2, max_length=140)
    placeholder: str | None = Field(max_length=100)
    required: bool | None
    options: list[str] | None = Field(max_length=8)
    scale: int | None = Field(ge=3, le=10)


class AddField(Strict):
    op: Literal["add_field"]
    after: str | None = Field(pattern=FIELD_ID)
    field: NewField


class RemoveField(Strict):
    op: Literal["remove_field"]
    id: str = Field(pattern=FIELD_ID)


class MoveField(Strict):
    op: Literal["move_field"]
    id: str = Field(pattern=FIELD_ID)
    position: int = Field(ge=0, le=MAX_BUSINESS_FIELDS - 1)


class SetTheme(Strict):
    """Couleurs et formes : chaque valeur est un hex ou un nombre borné, jamais du CSS."""

    op: Literal["set_theme"]
    page_from: str | None = Field(pattern=HEX_COLOR)
    page_to: str | None = Field(pattern=HEX_COLOR)
    surface: str | None = Field(pattern=HEX_COLOR)
    surface_alpha: float | None = Field(ge=0.05, le=1)
    border: str | None = Field(pattern=HEX_COLOR)
    border_alpha: float | None = Field(ge=0, le=1)
    ink: str | None = Field(pattern=HEX_COLOR)
    ink_soft: str | None = Field(pattern=HEX_COLOR)
    accent: str | None = Field(pattern=HEX_COLOR)
    accent_ink: str | None = Field(pattern=HEX_COLOR)
    blur_px: int | None = Field(ge=0, le=40)
    radius_px: int | None = Field(ge=0, le=48)
    glow: float | None = Field(ge=0, le=1)
    font: Literal["sans", "grotesk", "serif", "mono"] | None


class SetStructure(Strict):
    op: Literal["set_structure"]
    layout: Literal["card", "split", "minimal"] | None
    density: Literal["compact", "comfortable", "airy"] | None
    field_style: Literal["outline", "filled", "underline"] | None
    button_style: Literal["solid", "outline", "soft"] | None
    heading_align: Literal["left", "center"] | None


class Ask(Strict):
    """Aucune modification : Luna pose une question ou explique une limite."""

    op: Literal["ask"]


Operation = Annotated[
    Union[SetText, UpdateField, AddField, RemoveField, MoveField, SetTheme, SetStructure, Ask],
    Field(discriminator="op"),
]


class LunaOps(Strict):
    message: str = Field(min_length=3, max_length=240)
    ops: list[Operation] = Field(max_length=12)


def ops_json_schema() -> dict:
    """Schéma accepté par la sortie structurée stricte d'OpenAI.

    L'union discriminée de Pydantic produit un `oneOf`, refusé par l'API, qui
    n'accepte que `anyOf`. Le discriminant reste utilisé côté Python, où il
    donne des erreurs de validation bien plus lisibles.
    """
    schema = LunaOps.model_json_schema()
    items = schema["properties"]["ops"]["items"]
    if "oneOf" in items:
        items["anyOf"] = items.pop("oneOf")
        items.pop("discriminator", None)
    return schema


def _business_fields(state: dict) -> list[dict]:
    return [field for field in state.get("fields", []) if field.get("type") != "consent"]


def _consent_field(state: dict) -> dict | None:
    return next((field for field in state.get("fields", []) if field.get("type") == "consent"), None)


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    channels = []
    for index in (0, 2, 4):
        channel = int(value[index:index + 2], 16) / 255
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: str, background: str) -> float:
    """Rapport de contraste WCAG entre deux couleurs, de 1 à 21."""
    first, second = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def apply_ops(state: dict, ops: list[Operation]) -> tuple[dict, list[str]]:
    """Applique les opérations sur une copie de l'état et dit ce qui a bougé."""
    result = deepcopy(state)
    result.setdefault("content", {})
    result.setdefault("thank_you", {})
    result.setdefault("design", {}).setdefault("style", {})
    touched: list[str] = []

    for operation in ops:
        if isinstance(operation, Ask):
            continue

        if isinstance(operation, SetText):
            path, node = TEXT_TARGETS[operation.target]
            target = result
            for key in path[:-1]:
                target = target.setdefault(key, {})
            target[path[-1]] = operation.value
            touched.append(node)

        elif isinstance(operation, UpdateField):
            field = next((item for item in _business_fields(result) if item["id"] == operation.id), None)
            if not field:
                raise OpsError(f"Le champ « {operation.id} » n'existe pas.")
            for key in ("label", "placeholder", "required", "options", "scale"):
                value = getattr(operation, key)
                if value is not None:
                    field[key] = value
            touched.append(f"field:{operation.id}")

        elif isinstance(operation, AddField):
            fields = _business_fields(result)
            if len(fields) >= MAX_BUSINESS_FIELDS:
                raise OpsError("Le formulaire contient déjà 5 champs : il faut en retirer un d'abord.")
            if any(item["id"] == operation.field.id for item in fields):
                raise OpsError(f"Un champ « {operation.field.id} » existe déjà.")
            new_field = {key: value for key, value in operation.field.model_dump().items() if value not in (None, [])}
            index = len(fields)
            if operation.after:
                index = next((position + 1 for position, item in enumerate(fields) if item["id"] == operation.after), len(fields))
            fields.insert(index, new_field)
            result["fields"] = fields
            touched.append(f"field:{operation.field.id}")

        elif isinstance(operation, RemoveField):
            fields = _business_fields(result)
            if not any(item["id"] == operation.id for item in fields):
                raise OpsError(f"Le champ « {operation.id} » n'existe pas.")
            if len(fields) <= 1:
                raise OpsError("Un formulaire garde au moins un champ.")
            result["fields"] = [item for item in fields if item["id"] != operation.id]
            touched.append("card")

        elif isinstance(operation, MoveField):
            fields = _business_fields(result)
            field = next((item for item in fields if item["id"] == operation.id), None)
            if not field:
                raise OpsError(f"Le champ « {operation.id} » n'existe pas.")
            fields.remove(field)
            fields.insert(min(operation.position, len(fields)), field)
            result["fields"] = fields
            touched.append(f"field:{operation.id}")

        elif isinstance(operation, SetTheme):
            style = result["design"].setdefault("style", {})
            for key, value in operation.model_dump(exclude={"op"}).items():
                if value is not None:
                    style[key] = value
            touched.append("card")

        elif isinstance(operation, SetStructure):
            for key, value in operation.model_dump(exclude={"op"}).items():
                if value is not None:
                    result["design"][key] = value
            touched.append("card")

    # Le consentement reste la version controlee par le serveur, toujours en dernier.
    consent = _consent_field(state)
    fields = _business_fields(result)[:MAX_BUSINESS_FIELDS]
    result["fields"] = fields + ([consent] if consent else [])
    return result, list(dict.fromkeys(touched))


def validate_state(state: dict, previous: dict) -> None:
    """Garde-fous non negociables, verifies avant d'ecrire quoi que ce soit."""
    fields = _business_fields(state)
    if not fields:
        raise OpsError("Le formulaire doit garder au moins un champ.")
    if len(fields) > MAX_BUSINESS_FIELDS:
        raise OpsError("Le formulaire ne peut pas dépasser 5 champs métier.")

    ids = [field["id"] for field in fields]
    if len(set(ids)) != len(ids):
        raise OpsError("Deux champs portent le même identifiant.")

    previous_by_id = {field["id"]: field for field in _business_fields(previous)}
    for field in fields:
        if field["type"] not in FIELD_TYPES:
            raise OpsError(f"Le type « {field['type']} » n'est pas disponible.")
        if field["type"] in ("radio", "select") and len(field.get("options") or []) < 2:
            raise OpsError(f"Le champ « {field['id']} » a besoin d'au moins deux options.")
        # Un identifiant conserve garde son sens : les reponses deja collectees en dependent.
        if field["id"] in previous_by_id and field["type"] != previous_by_id[field["id"]]["type"]:
            kept = previous_by_id[field["id"]]["type"]
            raise OpsError(f"Le champ « {field['id']} » doit rester de type {kept} : des réponses y sont rattachées.")

    style = (state.get("design") or {}).get("style") or {}
    checks = (
        ("ink", "surface", "le texte sur la carte"),
        ("accent_ink", "accent", "le texte du bouton"),
    )
    for foreground, background, label in checks:
        if style.get(foreground) and style.get(background):
            ratio = contrast_ratio(style[foreground], style[background])
            if ratio < 4.5:
                raise OpsError(f"Contraste insuffisant pour {label} ({ratio:.1f}:1, minimum 4,5:1). Choisis des couleurs plus tranchées.")
