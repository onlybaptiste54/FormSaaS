"""Envoi d'e-mails en texte brut, avec la bibliotheque standard."""

import logging
import smtplib
from email.message import EmailMessage

from .config import settings


logger = logging.getLogger(__name__)


def send_mail(to: str, subject: str, body: str) -> None:
    """Envoie un e-mail ; sans SMTP_HOST, l'ecrit dans les logs de l'API.

    Les erreurs d'envoi remontent a l'appelant : c'est lui qui sait s'il doit
    les montrer ou seulement les journaliser.
    """
    if not settings.smtp_host:
        # Le corps contient le lien : qui lit les logs peut s'en servir.
        logger.warning("SMTP non configuré, e-mail non envoyé. À : %s | Objet : %s\n%s", to, subject, body)
        return

    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    if settings.smtp_port == 465:
        server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
    with server:
        # Le 587 impose le chiffrement ; sur les autres ports (25, 1025 pour
        # un Mailpit local), la connexion reste en clair.
        if settings.smtp_port == 587:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)
