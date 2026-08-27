from datetime import datetime, timedelta, timezone
from random import Random

from sqlalchemy import select
from sqlalchemy.orm import Session

from .luna import generate_campaign
from .models import Campaign, Company, FormResponse, User
from .security import hash_password


def seed(db: Session):
    if db.scalar(select(User).limit(1)):
        return
    company = Company(name="Atelier Rivage", legal_name="Atelier Rivage SAS", sector="Services", siret="901 234 567 00018", address="18 rue des Tisserands, 44000 Nantes", dpo_email="bonjour@atelier-rivage.fr")
    db.add(company)
    db.flush()
    user = User(company_id=company.id, email="demo@sillage.fr", full_name="Camille Martin", password_hash=hash_password("demo1234"), role="admin")
    db.add(user)
    db.flush()

    specs = [
        ("Satisfaction après rendez-vous", "survey", "active", 286),
        ("Contact site principal", "contact", "active", 174),
        ("Inscription portes ouvertes", "information", "draft", 32),
    ]
    rng = Random(7)
    for idx, (name, kind, status, visits) in enumerate(specs):
        prompt = "sondage satisfaction note avis" if kind == "survey" else ("inscription événement" if kind == "information" else "formulaire de contact")
        generated = generate_campaign(prompt, company.name)
        campaign = Campaign(company_id=company.id, creator_id=user.id, name=name, slug=generated["slug"], description=generated["description"], kind=kind, status=status, visibility="team" if idx == 0 else "private", fields=generated["fields"], thank_you=generated["thank_you"], visits=visits, created_at=datetime.now(timezone.utc) - timedelta(days=38 - idx * 9))
        db.add(campaign)
        db.flush()
        count = (68, 39, 4)[idx]
        for n in range(count):
            answers = {"name": ["Léa Bernard", "Thomas Petit", "Inès Robert", "Hugo Leroy"][n % 4], "email": f"contact{n + 1}@exemple.fr"}
            if kind == "survey":
                answers.update({"rating": rng.choice([3, 4, 4, 5, 5]), "recommend": rng.choice(["Oui", "Oui", "Peut-être"]), "comment": rng.choice(["Très bon accueil", "Équipe disponible", "Service rapide", "Merci !"])})
            else:
                answers.update({"phone": f"06 12 34 {n:02d} {n:02d}", "message": "Je souhaite être rappelé rapidement."})
            response = FormResponse(campaign_id=campaign.id, answers=answers, source=rng.choice(["Lien direct", "QR Code", "Website", "Email"]), consent=True, consent_text=generated["fields"][-1]["label"], ip_address="192.0.2.1", user_agent="Sillage demo", created_at=datetime.now(timezone.utc) - timedelta(days=rng.randrange(0, 30), hours=rng.randrange(0, 24)))
            db.add(response)
    db.commit()

