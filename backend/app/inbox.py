"""Boite de reception des reponses et exports CSV."""

import csv
import io
import json
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Text, cast, desc, func, or_, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Campaign, Form, FormResponse, User
from .security import admin_user, current_user


router = APIRouter()


def response_json(r: FormResponse, *, with_form: bool = False):
    payload = {"id": r.id, "answers": r.answers, "source": r.source, "promo_code": r.promo_code, "consent": r.consent, "consent_text": r.consent_text, "ip_address": r.ip_address, "user_agent": r.user_agent, "created_at": r.created_at.isoformat()}
    if with_form:
        payload |= {"form_id": r.form_id, "form": r.form.name, "campaign_id": r.form.campaign_id, "campaign": r.form.campaign.name}
    return payload


def inbox_query(user: User, campaign_id: str, form_id: str, source: str, date_from: date | None, date_to: date | None, q: str):
    """Filtres de la boite de reception, partages par la liste et l'export."""
    conditions = [Campaign.company_id == user.company_id]
    if campaign_id:
        conditions.append(Form.campaign_id == campaign_id)
    if form_id:
        conditions.append(FormResponse.form_id == form_id)
    if source:
        conditions.append(FormResponse.source == source)
    if date_from:
        conditions.append(FormResponse.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        conditions.append(FormResponse.created_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    if q.strip():
        conditions.append(answers_contain(q.strip()))
    return conditions


def like_pattern(value: str) -> str:
    return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def answers_contain(needle: str):
    """Recherche plein texte dans les reponses, quelle que soit la base."""
    answers = cast(FormResponse.answers, Text)
    # Les reponses enregistrees avant que le JSON passe en UTF-8 gardent les accents echappes.
    escaped = json.dumps(needle, ensure_ascii=True)[1:-1]
    terms = [answers.ilike(like_pattern(needle), escape="!")]
    if escaped != needle:
        terms.append(answers.ilike(like_pattern(escaped), escape="!"))
    return or_(*terms)


@router.get("/api/responses")
def list_responses(
    campaign_id: str = "",
    form_id: str = "",
    source: str = "",
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    q: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    conditions = inbox_query(user, campaign_id, form_id, source, date_from, date_to, q)
    base = select(FormResponse).join(FormResponse.form).join(Form.campaign).where(*conditions)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(desc(FormResponse.created_at)).limit(limit).offset(offset)).all()
    sources = db.execute(
        select(FormResponse.source).join(FormResponse.form).join(Form.campaign)
        .where(Campaign.company_id == user.company_id).group_by(FormResponse.source).order_by(FormResponse.source)
    ).scalars().all()
    return {"items": [response_json(r, with_form=True) for r in rows], "total": total, "limit": limit, "offset": offset, "sources": list(sources)}


@router.get("/api/responses/export.csv")
def export_responses_csv(
    campaign_id: str = "",
    form_id: str = "",
    source: str = "",
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    conditions = inbox_query(user, campaign_id, form_id, source, date_from, date_to, q)
    rows = db.scalars(select(FormResponse).join(FormResponse.form).join(Form.campaign).where(*conditions).order_by(desc(FormResponse.created_at))).all()
    return csv_response(rows, "reponses.csv", with_form=True)


def csv_safe(value):
    """Un texte qui commence comme une formule serait exécuté par Excel : on le neutralise."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def csv_response(rows: list[FormResponse], filename: str, *, with_form: bool = False):
    keys = list(dict.fromkeys(k for r in rows for k in r.answers.keys()))
    head = ["date", "campagne", "formulaire", "source", "consent"] if with_form else ["date", "source", "consent"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[*head, *[csv_safe(k) for k in keys]])
    writer.writeheader()
    for r in rows:
        row = {"date": r.created_at.isoformat(), "source": r.source, "consent": r.consent, **r.answers}
        if with_form:
            row |= {"campagne": r.form.campaign.name, "formulaire": r.form.name}
        writer.writerow({csv_safe(k): csv_safe(v) for k, v in row.items()})
    return StreamingResponse(iter([buffer.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/api/responses/{response_id}", status_code=204)
def delete_response(response_id: str, db: Session = Depends(get_db), user: User = Depends(admin_user)):
    response = db.get(FormResponse, response_id)
    if not response or response.form.campaign.company_id != user.company_id:
        raise HTTPException(404, "Réponse introuvable")
    db.delete(response)
    db.commit()
