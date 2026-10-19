import base64
import binascii
import re
from datetime import date
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, field_validator, model_validator


MAX_SCREENSHOT_BYTES = 3_800_000
MAX_ATTACHMENT_BYTES = 2_000_000
MAX_TOTAL_IMAGE_BYTES = 8_000_000
IMAGE_MIME_TYPES = {"png", "jpeg", "webp"}


def image_data_url_size(value: str, max_bytes: int) -> int:
    """Valide le type annonce et les octets avant de conserver une image."""
    # Le plafond encodé évite de décoder une chaîne disproportionnée.
    if len(value) > (max_bytes + 2) // 3 * 4 + 23:
        raise ValueError("Image trop volumineuse")
    header, separator, payload = value.partition(",")
    if not separator or not header.startswith("data:image/") or not header.endswith(";base64"):
        raise ValueError("Image attendue en data URL PNG, JPEG ou WebP")
    image_type = header[len("data:image/"):-len(";base64")]
    if image_type not in IMAGE_MIME_TYPES or not payload:
        raise ValueError("Image attendue en data URL PNG, JPEG ou WebP")
    try:
        binary = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Encodage de l'image invalide") from exc
    if len(binary) > max_bytes:
        raise ValueError("Image trop volumineuse")
    if base64.b64encode(binary).decode("ascii") != payload:
        raise ValueError("Encodage de l'image invalide")
    if image_type == "png":
        valid = len(binary) >= 24 and binary.startswith(b"\x89PNG\r\n\x1a\n") and binary[12:16] == b"IHDR"
    elif image_type == "jpeg":
        valid = len(binary) >= 10 and binary.startswith(b"\xff\xd8\xff") and binary.endswith(b"\xff\xd9")
    else:
        valid = len(binary) >= 20 and binary.startswith(b"RIFF") and binary[8:12] == b"WEBP"
    if not valid:
        raise ValueError("Le contenu ne correspond pas au format de l'image")
    return len(binary)


class SelectionRect(BaseModel):
    """Rectangle visé, en pourcentage du document affiché."""

    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)

    @model_validator(mode="after")
    def within_page(self) -> "SelectionRect":
        if self.x + self.width > 100.001 or self.y + self.height > 100.001:
            raise ValueError("Le rectangle doit rester dans la page")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class CampaignCreate(BaseModel):
    """La campagne est un dossier : aucune IA a ce niveau."""

    name: str = Field(min_length=3, max_length=140)
    client: str = Field(default="", max_length=140)
    objective: str = Field(default="", max_length=600)
    starts_on: date | None = None
    ends_on: date | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=140)
    client: str | None = Field(default=None, max_length=140)
    objective: str | None = Field(default=None, max_length=600)
    starts_on: date | None = None
    ends_on: date | None = None
    archived: bool | None = None


class FormCreate(BaseModel):
    prompt: str = Field(min_length=10, max_length=1200)
    name: str = Field(default="", max_length=90)
    description: str = Field(default="", max_length=260)
    context: str = Field(default="", max_length=800)
    images: list[str] = Field(default_factory=list, max_length=2)
    use_brand: bool = True


class TemplateUse(BaseModel):
    """Un modele s'utilise toujours dans une campagne existante."""

    campaign_id: str = Field(min_length=1, max_length=36)


class ThankYou(BaseModel):
    """Page de remerciement : seules les actions réellement rendues sont acceptées."""

    title: str = Field(min_length=3, max_length=100)
    message: str = Field(min_length=3, max_length=400)
    action: Literal["none", "cta", "redirect"] = "none"
    button_label: str = Field(default="Retour au site", max_length=60)
    button_url: str = Field(default="", max_length=400)

    @field_validator("button_url")
    @classmethod
    def https_only(cls, value: str) -> str:
        if not value:
            return value
        AnyHttpUrl(value)
        if not value.startswith("https://"):
            raise ValueError("L'URL de destination doit commencer par https://")
        return value


class FormUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: Literal["draft", "active"] | None = None
    visibility: Literal["private", "team", "public"] | None = None
    fields: list[dict[str, Any]] | None = None
    design: dict[str, Any] | None = None
    thank_you: ThankYou | None = None
    archived: bool | None = None


class DraftUpdate(BaseModel):
    """Edition directe dans l'editeur : tout passe par le brouillon."""

    html: str | None = Field(default=None, min_length=1, max_length=250_000)
    name: str | None = Field(default=None, min_length=2, max_length=140)
    description: str | None = Field(default=None, max_length=400)
    fields: list[dict[str, Any]] | None = None
    design: dict[str, Any] | None = None
    content: dict[str, str] | None = None
    thank_you: ThankYou | None = None


class LunaRefineRequest(BaseModel):
    """Une demande porte sur la zone encadree, decrite par les elements qu'elle contient."""

    instruction: str = Field(min_length=3, max_length=800)
    element_ids: list[str] = Field(default_factory=list, max_length=30)
    selection_label: str = Field(default="Formulaire complet", max_length=400)
    view: Literal["form", "thanks"] = "form"
    page_id: str | None = Field(default=None, max_length=36)
    region: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    selection_rect: SelectionRect | None = None
    screenshot_data_url: str | None = Field(default=None, max_length=5_066_700)
    # Images jointes par l'utilisateur : capture, inspiration, photo de charte.
    images: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def bounded_images(self) -> "LunaRefineRequest":
        total = 0
        if self.screenshot_data_url:
            total += image_data_url_size(self.screenshot_data_url, MAX_SCREENSHOT_BYTES)
        for image in self.images:
            total += image_data_url_size(image, MAX_ATTACHMENT_BYTES)
        if total > MAX_TOTAL_IMAGE_BYTES:
            raise ValueError("Les images jointes sont trop volumineuses ensemble")
        return self


class SubmitResponse(BaseModel):
    page_id: str | None = Field(default=None, max_length=36)
    answers: dict[str, Any] = Field(max_length=40)
    source: str = Field(default="Lien direct", max_length=40)
    promo_code: str = Field(default="", max_length=60)
    consent: bool = False

    @field_validator("answers")
    @classmethod
    def bounded_answers(cls, value: dict[str, Any]) -> dict[str, Any]:
        for name, answer in value.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", name):
                raise ValueError("Nom de champ invalide")
            if isinstance(answer, bool) or not isinstance(answer, (str, int, float)) or len(str(answer)) > 2000:
                raise ValueError("Valeur de champ invalide")
        return value


class TunnelPageCreate(BaseModel):
    role: Literal["landing", "form"]
    name: str = Field(default="", max_length=100)


class TunnelPageUpdate(BaseModel):
    next_page_id: str | None = Field(default=None, max_length=36)
    position: int | None = Field(default=None, ge=0, le=100)


class PublicPageVisit(BaseModel):
    page_id: str | None = Field(default=None, max_length=36)


class PublicPageAdvance(BaseModel):
    from_page_id: str = Field(max_length=36)


class BrandProfileIn(BaseModel):
    palette: list[str] = Field(default_factory=list, max_length=6)
    font: Literal["sans", "grotesk", "serif", "mono"] | None = None
    tone: str | None = Field(default=None, max_length=60)
    rules_do: list[str] = Field(default_factory=list, max_length=5)
    rules_avoid: list[str] = Field(default_factory=list, max_length=5)
    summary: str | None = Field(default=None, max_length=240)

    @field_validator("palette")
    @classmethod
    def hex_only(cls, value: list[str]) -> list[str]:
        for color in value:
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Les couleurs de la palette doivent être au format #RRGGBB")
        return value


class BrandAnalyzeRequest(BaseModel):
    """Images de la charte, envoyees une fois pour en deduire un profil."""

    images: list[str] = Field(min_length=1, max_length=4)
    notes: str = Field(default="", max_length=400)


class CompanyUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    sector: str | None = None
    siret: str | None = None
    address: str | None = None
    primary_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    tone: str | None = None
    dpo_email: EmailStr | None = None
    # Data URL d'image, 200 Ko maximum : le navigateur redimensionne avant l'envoi.
    logo: str | None = Field(default=None, max_length=280_000)
    brand: BrandProfileIn | None = None

    @field_validator("logo")
    @classmethod
    def image_data_url(cls, value: str | None) -> str | None:
        if value and not re.match(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$", value):
            raise ValueError("Le logo doit être une image PNG, JPEG ou WebP")
        return value
