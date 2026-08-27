from typing import Any

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
    thank_you: dict[str, Any] | None = None
    archived: bool | None = None


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

