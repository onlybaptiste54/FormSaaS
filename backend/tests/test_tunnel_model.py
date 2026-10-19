from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

def test_tunnel_can_order_multiple_pages_with_the_same_role():
    from app.models import Base, Campaign, Company, Page, Tunnel, User
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(Company(id="company", name="Atelier"))
            db.add(User(id="user", company_id="company", email="a@example.fr", full_name="A", password_hash="x"))
            db.add(Campaign(id="campaign", company_id="company", creator_id="user", name="Campagne"))
            db.add(Tunnel(id="tunnel", campaign_id="campaign", name="Parcours", slug="parcours"))
            db.flush()
            db.add_all([
                Page(id="landing", tunnel_id="tunnel", form_id=None, role="landing", position=0,
                     html="<h1>Accueil</h1>"),
                Page(id="step1", tunnel_id="tunnel", form_id=None, role="step", position=1,
                     html="<h1>Étape 1</h1>"),
                Page(id="step2", tunnel_id="tunnel", form_id=None, role="step", position=2,
                     html="<h1>Étape 2</h1>"),
            ])
            db.flush()
            db.get(Page, "landing").next_page_id = "step1"
            db.get(Page, "step1").next_page_id = "step2"
            db.get(Tunnel, "tunnel").entry_page_id = "landing"
            db.commit()

        with Session(engine) as db:
            campaign = db.scalar(select(Campaign))
            tunnel = campaign.tunnels[0]
            assert tunnel.entry_page.id == "landing"
            assert [(page.id, page.role) for page in tunnel.pages] == [
                ("landing", "landing"), ("step1", "step"), ("step2", "step")
            ]
            assert [page.form_id for page in tunnel.pages] == [None, None, None]
            assert [page.next_page_id for page in tunnel.pages] == ["step1", "step2", None]
    finally:
        engine.dispose()
