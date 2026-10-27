from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uid() -> str:
    return str(uuid4())


def thanks_page_id(form_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"sillage:form:{form_id}:thanks"))


def initial_tunnel_id(form_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"sillage:form:{form_id}:tunnel"))


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
    """Dossier de travail : un client, un evenement, une operation. Contient des formulaires."""

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(140))
    client: Mapped[str] = mapped_column(String(140), default="")
    objective: Mapped[str] = mapped_column(Text, default="")
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True, default=None)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    company: Mapped[Company] = relationship(back_populates="campaigns")
    creator: Mapped[User] = relationship(back_populates="campaigns")
    forms: Mapped[list["Form"]] = relationship(back_populates="campaign", cascade="all, delete-orphan", order_by="Form.created_at")
    tunnels: Mapped[list["Tunnel"]] = relationship(back_populates="campaign", cascade="all, delete-orphan", order_by="Tunnel.created_at")


class Tunnel(Base):
    """Parcours de pages au sein d'une campagne."""

    __tablename__ = "tunnels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    name: Mapped[str] = mapped_column(String(140))
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    entry_page_id: Mapped[str | None] = mapped_column(ForeignKey("pages.id", use_alter=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    campaign: Mapped[Campaign] = relationship(back_populates="tunnels")
    pages: Mapped[list["Page"]] = relationship(back_populates="tunnel", foreign_keys="Page.tunnel_id", cascade="all, delete-orphan", order_by="Page.position")
    entry_page: Mapped["Page | None"] = relationship(foreign_keys=[entry_page_id], post_update=True)


class Form(Base):
    """Le formulaire lui-meme : ce qu'on edite avec Luna et ce que voit un visiteur."""

    __tablename__ = "forms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
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
    # Identite appliquee a cette page, figee a la creation. NULL signale un
    # formulaire anterieur, qui retombe sur celle du compte ; {} signale un
    # choix explicite de ne pas appliquer d'identite.
    identity: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    campaign: Mapped[Campaign] = relationship(back_populates="forms")
    creator: Mapped[User] = relationship()
    responses: Mapped[list["FormResponse"]] = relationship(back_populates="form", cascade="all, delete-orphan")
    versions: Mapped[list["FormVersion"]] = relationship(back_populates="form", cascade="all, delete-orphan", order_by="FormVersion.created_at")
    pages: Mapped[list["Page"]] = relationship(back_populates="form", cascade="all, delete-orphan", order_by="Page.position")


class Page(Base):
    """Document HTML d'un tunnel ; form_id garde la collecte historique."""

    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("form_id", "role", name="uq_pages_form_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    form_id: Mapped[str | None] = mapped_column(ForeignKey("forms.id"), index=True, nullable=True)
    tunnel_id: Mapped[str | None] = mapped_column(ForeignKey("tunnels.id"), index=True, nullable=True)
    name: Mapped[str | None] = mapped_column(String(140), nullable=True)
    slug: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    position: Mapped[int] = mapped_column(Integer, default=0)
    next_page_id: Mapped[str | None] = mapped_column(ForeignKey("pages.id"), nullable=True)
    next_page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    html: Mapped[str] = mapped_column(Text)
    draft_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[list] = mapped_column(JSON, default=list)
    draft_manifest: Mapped[list | None] = mapped_column(JSON, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    visits: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    form: Mapped[Form | None] = relationship(back_populates="pages", foreign_keys=[form_id])
    tunnel: Mapped[Tunnel | None] = relationship(back_populates="pages", foreign_keys=[tunnel_id])


class FormVersion(Base):
    """Etat du formulaire apres une etape d'edition : sert d'historique et d'annulation."""

    __tablename__ = "form_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    form_id: Mapped[str] = mapped_column(ForeignKey("forms.id"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="luna")
    instruction: Mapped[str] = mapped_column(Text, default="")
    message: Mapped[str] = mapped_column(Text, default="")
    # La capture et les references restent attachees au message Luna apres rechargement.
    screenshot_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    images: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    form: Mapped[Form] = relationship(back_populates="versions")


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
    form_id: Mapped[str] = mapped_column(ForeignKey("forms.id"), index=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="Lien direct")
    promo_code: Mapped[str] = mapped_column(String(60), default="")
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_text: Mapped[str] = mapped_column(Text, default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    form: Mapped[Form] = relationship(back_populates="responses")
