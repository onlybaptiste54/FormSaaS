from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class CampaignCreate(BaseModel):
    prompt: str = Field(min_length=10, max_length=1200)


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    visibility: str | None = None
    fields: list[dict[str, Any]] | None = None
    design: dict[str, Any] | None = None
    thank_you: dict[str, Any] | None = None
    archived: bool | None = None


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
    primary_color: str | None = None
    accent_color: str | None = None
    tone: str | None = None
    dpo_email: EmailStr | None = None
