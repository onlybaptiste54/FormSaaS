"""Cree le premier administrateur d'une mise en ligne.

En production il n'y a pas de donnees de demonstration, donc pas de compte :
cette commande ouvre la porte une seule fois.

    python -m app.admin --email vous@exemple.fr --company "Votre entreprise"

Le mot de passe est demande sans etre affiche. Pour un deploiement automatise,
le passer par la variable ADMIN_PASSWORD plutot que par --password, qui reste
dans l'historique du shell.
"""

import argparse
import getpass
import os
import sys

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import SessionLocal, initialize_schema
from .models import Company, User
from .schemas import FirstAdminIn
from .security import hash_password


def create_first_admin(db: Session, account: FirstAdminIn) -> User:
    """Cree l'entreprise et son administrateur, et seulement sur une base vide.

    Refuser des qu'un compte existe garde cette commande inoffensive : elle ne
    peut pas servir a s'ajouter a une entreprise deja en service.
    """
    if db.scalar(select(User).limit(1)):
        raise ValueError(
            "Un compte existe déjà : cette commande ne crée que le premier administrateur."
        )
    company = Company(name=account.company_name, legal_name=account.company_name)
    db.add(company)
    db.flush()
    user = User(company_id=company.id, email=str(account.email).lower(), full_name=account.full_name,
                password_hash=hash_password(account.password), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def read_password(given: str | None) -> str:
    """--password, sinon ADMIN_PASSWORD, sinon une saisie masquee confirmee."""
    if given:
        return given
    from_environment = os.environ.get("ADMIN_PASSWORD")
    if from_environment:
        return from_environment
    typed = getpass.getpass("Mot de passe : ")
    if typed != getpass.getpass("Confirmation : "):
        raise ValueError("Les deux saisies diffèrent.")
    return typed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.admin",
                                     description="Crée le premier administrateur de cette installation.")
    parser.add_argument("--email", required=True, help="Adresse de connexion")
    parser.add_argument("--company", required=True, help="Nom de l'entreprise")
    parser.add_argument("--name", default="", help="Nom complet affiché (défaut : la partie avant @)")
    parser.add_argument("--password", default=None,
                        help="À éviter : reste dans l'historique du shell. Sinon ADMIN_PASSWORD, "
                             "sinon saisie masquée.")
    args = parser.parse_args(argv)

    try:
        account = FirstAdminIn(email=args.email, password=read_password(args.password),
                               full_name=args.name or args.email.split("@")[0],
                               company_name=args.company)
    except (ValidationError, ValueError) as exc:
        print(f"Compte refusé : {exc}", file=sys.stderr)
        return 2

    initialize_schema()
    with SessionLocal() as db:
        try:
            user = create_first_admin(db, account)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    print(f"Administrateur créé : {user.email} pour {account.company_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
