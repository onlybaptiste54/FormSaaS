from app.luna import generate_campaign


def test_survey_generation_stays_short_and_rgpd_ready():
    campaign = generate_campaign("Je veux un sondage de satisfaction avec une note", "Atelier Test")
    assert campaign["kind"] == "survey"
    assert len(campaign["fields"]) <= 6
    assert campaign["fields"][-1]["type"] == "consent"
    assert campaign["fields"][-1]["required"] is True


def test_contact_generation_understands_urgency():
    campaign = generate_campaign("Formulaire plombier avec type intervention et urgence", "Plombier Martin")
    ids = [field["id"] for field in campaign["fields"]]
    assert "urgent" in ids
    assert campaign["kind"] == "contact"
