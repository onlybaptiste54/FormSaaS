import logging
from datetime import date, datetime, timedelta, timezone
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import is_production
from .luna import generate_campaign
from .models import Campaign, Company, Form, FormResponse, Page, Tunnel, User, initial_tunnel_id, thanks_page_id
from .page_document import legacy_to_html, prepare_page
from .security import hash_password


# Deux campagnes de demonstration, dont une a deux formulaires : le niveau campagne se voit tout de suite.
DEMO = [
    {
        "name": "Relation client boutique",
        "client": "Atelier Rivage",
        "objective": "Suivre la satisfaction et récupérer les demandes entrantes du site.",
        "forms": [
            ("Satisfaction après rendez-vous", "survey", "active", 286, 68),
            ("Contact site principal", "contact", "active", 174, 39),
        ],
    },
    {
        "name": "Portes ouvertes d’octobre",
        "client": "Atelier Rivage",
        "objective": "Remplir les créneaux de visite de l’atelier.",
        "forms": [
            ("Inscription portes ouvertes", "information", "draft", 32, 4),
        ],
    },
]

PROMPTS = {"survey": "sondage satisfaction note avis", "information": "inscription événement", "contact": "formulaire de contact"}


def seed(db: Session):
    existing = db.scalar(select(User).limit(1))
    if is_production():
        # Un compte de démonstration connu annulerait le contrôle des rôles.
        if not existing:
            logging.getLogger(__name__).warning(
                "Base vide et ENVIRONMENT=production : aucune donnée de démonstration n'est créée. "
                "Créez le premier compte avec "
                'python -m app.admin --email vous@exemple.fr --company "Votre entreprise"'
            )
        return
    if existing:
        return
    company = Company(name="Atelier Rivage", legal_name="Atelier Rivage SAS", sector="Services", siret="901 234 567 00018", address="18 rue des Tisserands, 44000 Nantes", dpo_email="bonjour@atelier-rivage.fr")
    db.add(company)
    db.flush()
    user = User(company_id=company.id, email="demo@sillage.fr", full_name="Camille Martin", password_hash=hash_password("demo1234"), role="admin")
    db.add(user)
    db.flush()

    rng = Random(7)
    position = 0
    for spec in DEMO:
        campaign = Campaign(company_id=company.id, creator_id=user.id, name=spec["name"], client=spec["client"], objective=spec["objective"], starts_on=date.today() - timedelta(days=40), ends_on=date.today() + timedelta(days=20))
        db.add(campaign)
        db.flush()
        for name, kind, status, visits, count in spec["forms"]:
            generated = generate_campaign(PROMPTS[kind], company.name)
            form = Form(campaign_id=campaign.id, creator_id=user.id, name=name, slug=generated["slug"], description=generated["description"], kind=kind, status=status, visibility="team" if position == 0 else "private", fields=generated["fields"], design=generated["design"], thank_you=generated["thank_you"], visits=visits, created_at=datetime.now(timezone.utc) - timedelta(days=38 - position * 9))
            db.add(form)
            db.flush()
            tunnel_id = initial_tunnel_id(form.id)
            tunnel = Tunnel(id=tunnel_id, campaign_id=campaign.id, name=form.name,
                            slug=form.slug, status=form.status)
            db.add(tunnel)
            db.flush()
            form_state = {
                "name": form.name, "description": form.description, "kind": form.kind,
                "fields": form.fields, "design": form.design, "content": form.content or {},
                "thank_you": form.thank_you,
            }
            company_state = {column.name: getattr(company, column.name) for column in Company.__table__.columns}
            form_html, manifest = prepare_page(legacy_to_html(form_state, company_state), require_form=True)
            thanks_html, thanks_manifest = prepare_page(
                legacy_to_html(form_state, company_state, role="thanks"), require_form=False
            )
            thanks_id = thanks_page_id(form.id)
            db.add(Page(id=thanks_id, form=form, tunnel_id=tunnel_id, slug=None, role="thanks", position=1,
                        html=thanks_html, manifest=thanks_manifest, settings=form.thank_you, visits=count))
            db.flush()
            db.add(Page(id=form.id, form=form, tunnel_id=tunnel_id, slug=form.slug, role="form", position=0,
                        next_page_id=thanks_id, html=form_html, manifest=manifest,
                        visits=visits, conversions=count))
            tunnel.entry_page_id = form.id
            form.thank_you = {}
            for n in range(count):
                answers = {"name": ["Léa Bernard", "Thomas Petit", "Inès Robert", "Hugo Leroy"][n % 4], "email": f"contact{n + 1}@exemple.fr"}
                if kind == "survey":
                    answers.update({"rating": rng.choice([3, 4, 4, 5, 5]), "recommend": rng.choice(["Oui", "Oui", "Peut-être"]), "comment": rng.choice(["Très bon accueil", "Équipe disponible", "Service rapide", "Merci !"])})
                else:
                    answers.update({"phone": f"06 12 34 {n:02d} {n:02d}", "message": "Je souhaite être rappelé rapidement."})
                response = FormResponse(form_id=form.id, answers=answers, source=rng.choice(["Lien direct", "QR Code", "Website", "Email"]), consent=True, consent_text=generated["fields"][-1]["label"], ip_address="192.0.2.1", user_agent="Sillage demo", created_at=datetime.now(timezone.utc) - timedelta(days=rng.randrange(0, 30), hours=rng.randrange(0, 24)))
                db.add(response)
            position += 1
    db.commit()
