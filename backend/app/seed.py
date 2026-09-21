from datetime import date, datetime, timedelta, timezone
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from .luna import generate_campaign
from .models import Campaign, Company, Form, FormResponse, User
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
    if db.scalar(select(User).limit(1)):
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
