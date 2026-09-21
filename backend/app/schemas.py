from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, field_validator


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class CampaignCreate(BaseModel):
    prompt: str = Field(min_length=10, max_length=1200)


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
    instruction: str = Field(min_length=3, max_length=800)
    selection_kind: Literal["form", "header", "field", "button"] = "form"
    selection_id: str | None = Field(default=None, max_length=40)
    selection_label: str = Field(default="Formulaire complet", max_length=140)
    screenshot_data_url: str | None = Field(default=None, max_length=4_000_000)


class SubmitResponse(BaseModel):
    answers: dict[str, Any]
    source: str = "Lien direct"
    promo_code: str = ""
    consent: bool = False


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
