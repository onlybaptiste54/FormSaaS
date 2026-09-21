import re
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, field_validator


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class CampaignCreate(BaseModel):
    prompt: str = Field(min_length=10, max_length=1200)
    context: str = Field(default="", max_length=800)
    images: list[str] = Field(default_factory=list, max_length=2)
    use_brand: bool = True


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


class CampaignUpdate(BaseModel):
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
    selection_label: str = Field(default="Formulaire complet", max_length=140)
    view: Literal["form", "thanks"] = "form"
    screenshot_data_url: str | None = Field(default=None, max_length=4_000_000)


class SubmitResponse(BaseModel):
    answers: dict[str, Any]
    source: str = "Lien direct"
    promo_code: str = ""
    consent: bool = False


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
