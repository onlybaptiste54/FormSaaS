"""Campagnes : liste, creation, modification et statistiques."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Campaign, Form, FormResponse, Tunnel, User
from .schemas import CampaignCreate, CampaignUpdate
from .security import current_user, write_user


router = APIRouter()


def campaign_summaries(db: Session, campaigns: list[Campaign]) -> dict[str, dict]:
    """Bilan de chaque campagne, compte en SQL : jamais en chargeant les reponses."""
    ids = [c.id for c in campaigns]
    empty = {"forms": 0, "active": 0, "visits": 0, "responses": 0, "last_activity": None}
    if not ids:
        return {}
    summaries = {campaign_id: dict(empty) for campaign_id in ids}
    forms = db.execute(
        select(Form.campaign_id, func.count(Form.id), func.coalesce(func.sum(Form.visits), 0), func.max(Form.updated_at))
        .where(Form.campaign_id.in_(ids), Form.archived.is_(False))
        .group_by(Form.campaign_id)
    ).all()
    for campaign_id, total, visits, updated in forms:
        summaries[campaign_id].update({"forms": total, "visits": int(visits or 0), "last_activity": updated})
    active = db.execute(
        select(Form.campaign_id, func.count(Form.id))
        .where(Form.campaign_id.in_(ids), Form.archived.is_(False), Form.status == "active")
        .group_by(Form.campaign_id)
    ).all()
    for campaign_id, total in active:
        summaries[campaign_id]["active"] = total
    responses = db.execute(
        select(Form.campaign_id, func.count(FormResponse.id), func.max(FormResponse.created_at))
        .join(FormResponse, FormResponse.form_id == Form.id)
        .where(Form.campaign_id.in_(ids))
        .group_by(Form.campaign_id)
    ).all()
    for campaign_id, total, last in responses:
        summary = summaries[campaign_id]
        summary["responses"] = total
        if last and (not summary["last_activity"] or last > summary["last_activity"]):
            summary["last_activity"] = last
    return summaries


def campaign_json(c: Campaign, summary: dict):
    visits = summary["visits"]
    responses = summary["responses"]
    last = summary["last_activity"] or c.updated_at
    return {
        "id": c.id,
        "name": c.name,
        "client": c.client,
        "objective": c.objective,
        "starts_on": c.starts_on.isoformat() if c.starts_on else None,
        "ends_on": c.ends_on.isoformat() if c.ends_on else None,
        "forms": summary["forms"],
        "active": summary["active"],
        "visits": visits,
        "responses": responses,
        "conversion": round((responses / visits * 100) if visits else 0, 1),
        "last_activity": last.isoformat(),
        "archived": c.archived,
        "created_at": c.created_at.isoformat(),
        "updated_at": c.updated_at.isoformat(),
    }


def one_campaign_json(db: Session, c: Campaign):
    return campaign_json(c, campaign_summaries(db, [c])[c.id])


def owned_campaign(campaign_id: str, db: Session, user: User) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if not campaign or campaign.company_id != user.company_id:
        raise HTTPException(404, "Campagne introuvable")
    return campaign


@router.get("/api/campaigns")
def list_campaigns(archived: bool = False, db: Session = Depends(get_db), user: User = Depends(current_user)):
    campaigns = db.scalars(select(Campaign).where(
        Campaign.company_id == user.company_id, Campaign.archived == archived,
        ~Campaign.tunnels.any(Tunnel.kind == "sales")
    ).order_by(desc(Campaign.updated_at))).all()
    summaries = campaign_summaries(db, list(campaigns))
    return [campaign_json(c, summaries[c.id]) for c in campaigns]


@router.post("/api/campaigns", status_code=201)
def create_campaign(data: CampaignCreate, db: Session = Depends(get_db), user: User = Depends(write_user)):
    campaign = Campaign(company_id=user.company_id, creator_id=user.id, **data.model_dump())
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return one_campaign_json(db, campaign)


@router.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return one_campaign_json(db, owned_campaign(campaign_id, db, user))


@router.patch("/api/campaigns/{campaign_id}")
def update_campaign(campaign_id: str, data: CampaignUpdate, db: Session = Depends(get_db), user: User = Depends(write_user)):
    campaign = owned_campaign(campaign_id, db, user)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(campaign, key, value)
    db.commit()
    return one_campaign_json(db, campaign)


@router.get("/api/campaigns/{campaign_id}/stats")
def campaign_stats(campaign_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Bilan de la campagne : ce que chaque formulaire apporte, agrege en SQL."""
    campaign = owned_campaign(campaign_id, db, user)
    forms = db.scalars(select(Form).where(Form.campaign_id == campaign.id, Form.archived.is_(False)).order_by(Form.created_at)).all()
    ids = [f.id for f in forms]
    counts = dict(db.execute(select(FormResponse.form_id, func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids)).group_by(FormResponse.form_id)).all()) if ids else {}
    visits = sum(f.visits for f in forms)
    responses = sum(counts.values())
    breakdown = [
        {
            "id": f.id,
            "name": f.name,
            "status": f.status,
            "visits": f.visits,
            "responses": counts.get(f.id, 0),
            "conversion": round((counts.get(f.id, 0) / f.visits * 100) if f.visits else 0, 1),
        }
        for f in forms
    ]
    daily = []
    for offset in range(6, -1, -1):
        day = (datetime.now(timezone.utc) - timedelta(days=offset)).date()
        count = db.scalar(select(func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids), func.date(FormResponse.created_at) == day)) if ids else 0
        daily.append({"date": day.isoformat(), "count": count or 0})
    sources = db.execute(select(FormResponse.source, func.count(FormResponse.id)).where(FormResponse.form_id.in_(ids)).group_by(FormResponse.source).order_by(desc(func.count(FormResponse.id)))).all() if ids else []
    best = max(breakdown, key=lambda row: (row["responses"], row["conversion"]), default=None)
    return {
        "forms": len(forms),
        "active": sum(f.status == "active" for f in forms),
        "visits": visits,
        "responses": responses,
        "conversion": round((responses / visits * 100) if visits else 0, 1),
        "best": best if best and best["responses"] else None,
        "breakdown": breakdown,
        "daily": daily,
        "sources": [{"name": name, "count": count} for name, count in sources],
    }
