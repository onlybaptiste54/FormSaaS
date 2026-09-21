from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    legal_name: Mapped[str] = mapped_column(String(160), default="")
    sector: Mapped[str] = mapped_column(String(80), default="Services")
    siret: Mapped[str] = mapped_column(String(20), default="")
    address: Mapped[str] = mapped_column(String(240), default="")
    primary_color: Mapped[str] = mapped_column(String(7), default="#2F6B4F")
    accent_color: Mapped[str] = mapped_column(String(7), default="#EE755C")
    tone: Mapped[str] = mapped_column(String(40), default="Professionnel")
    dpo_email: Mapped[str] = mapped_column(String(160), default="")
    # Logo en data URL (200 Ko maximum, redimensionne par le navigateur).
    logo: Mapped[str] = mapped_column(Text, default="")
    # Profil de marque : palette, police, ton et regles, valides par l'utilisateur.
    brand: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    users: Mapped[list["User"]] = relationship(back_populates="company")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="company")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(30), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    company: Mapped[Company] = relationship(back_populates="users")
    campaigns: Mapped[list["Campaign"]] = relationship(back_populates="creator")


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(140))
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(30), default="contact")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    visibility: Mapped[str] = mapped_column(String(30), default="private")
    fields: Mapped[list] = mapped_column(JSON, default=list)
    design: Mapped[dict] = mapped_column(JSON, default=dict)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    thank_you: Mapped[dict] = mapped_column(JSON, default=dict)
    # Modifications non publiees : le formulaire en ligne lit les colonnes ci-dessus.
    draft: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    # Brief d'origine : Luna s'en souvient lors des retouches.
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    company: Mapped[Company] = relationship(back_populates="campaigns")
    creator: Mapped[User] = relationship(back_populates="campaigns")
    responses: Mapped[list["FormResponse"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")
    versions: Mapped[list["CampaignVersion"]] = relationship(back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignVersion.created_at")


class CampaignVersion(Base):
    """Etat du formulaire apres une etape d'edition : sert d'historique et d'annulation."""

    __tablename__ = "campaign_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="luna")
    instruction: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    campaign: Mapped[Campaign] = relationship(back_populates="versions")


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("company_id", "source_key", name="uq_template_company_source"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    source_key: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="Contact")
    fields: Mapped[list] = mapped_column(JSON, default=list)
    design: Mapped[dict] = mapped_column(JSON, default=dict)
    thank_you: Mapped[dict] = mapped_column(JSON, default=dict)
    uses: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class FormResponse(Base):
    __tablename__ = "responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="Lien direct")
    promo_code: Mapped[str] = mapped_column(String(60), default="")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_text: Mapped[str] = mapped_column(Text, default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    campaign: Mapped[Campaign] = relationship(back_populates="responses")
