import json

import httpx
import pytest

from app.brand_site import SiteError, _families, check_url, extract, read_site, site_name
from app.luna import LunaAPIError, analyze_site_brand


PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731 - resolveur de test

PAGE = (
    '<html><head><title>Smart Duck</title>'
    '<meta name="description" content="Pilotage simple">'
    '<link rel="stylesheet" href="/assets/app.css">'
    '<style>body{background:#FFFFFF;color:#1A1A2E;font-family:"Inter",sans-serif}</style>'
    '</head><body><h1>Pilotez votre activité</h1><h2>Sans tableur</h2></body></html>'
)

FEUILLE = (
    ':root{--brand:#7A3FF2}'
    '.btn{background:#7A3FF2;color:#fff;border:1px solid rgb(122,63,242)}'
    '@media(max-width:600px){.btn{background:#7A3FF2;font-family:Georgia,serif}}'
)


def test_check_url_refuses_everything_that_is_not_a_public_site():
    for adresse in ("file:///etc/passwd", "ftp://exemple.fr"):
        with pytest.raises(SiteError):
            check_url(adresse, resolve=PUBLIC)
    for prive in ("127.0.0.1", "10.0.0.5", "192.168.1.4", "169.254.169.254", "::1"):
        with pytest.raises(SiteError, match="réseau privé"):
            check_url(f"http://cible.test/", resolve=lambda host, ip=prive: [ip])


def test_check_url_adds_https_and_accepts_a_public_host():
    assert check_url("smartduck.fr/tarifs", resolve=PUBLIC) == "https://smartduck.fr/tarifs"


def test_extract_keeps_full_hex_colors_and_real_font_families():
    """Regression : une alternance mal ordonnee lisait #7A3FF2 comme #7A3."""
    faits = extract(PAGE, [FEUILLE], url="https://smartduck.fr/")
    valeurs = [couleur["value"] for couleur in faits["colors"]]
    assert valeurs[0] == "#7a3ff2", "la couleur de marque doit dominer"
    assert "#77aa33" not in valeurs
    assert "#1a1a2e" in valeurs
    assert [police["name"] for police in faits["fonts"]] == ["Inter", "Georgia"]
    assert faits["title"] == "Smart Duck"
    assert faits["headings"] == ["Pilotez votre activité", "Sans tableur"]
    accent = next(couleur for couleur in faits["colors"] if couleur["value"] == "#7a3ff2")
    assert {"fond", "bordure"} <= set(accent["roles"])


def test_read_site_follows_one_redirect_and_loads_the_linked_stylesheet():
    vues = []

    def handler(request: httpx.Request) -> httpx.Response:
        vues.append(str(request.url))
        if request.url.path == "/":
            return httpx.Response(301, headers={"location": "https://smartduck.fr/accueil"})
        if request.url.path == "/accueil":
            return httpx.Response(200, text=PAGE)
        return httpx.Response(200, text=FEUILLE)

    faits = read_site("https://smartduck.fr/", transport=httpx.MockTransport(handler), resolve=PUBLIC)
    assert vues == ["https://smartduck.fr/", "https://smartduck.fr/accueil", "https://smartduck.fr/assets/app.css"]
    assert faits["url"] == "https://smartduck.fr/accueil"
    assert faits["stylesheets_read"] == 1
    assert faits["colors"][0]["value"] == "#7a3ff2"


def test_read_site_refuses_a_redirect_towards_a_private_address():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    def resolve(host):
        return ["169.254.169.254"] if host == "169.254.169.254" else ["93.184.216.34"]

    with pytest.raises(SiteError, match="réseau privé"):
        read_site("https://smartduck.fr/", transport=httpx.MockTransport(handler), resolve=resolve)


def _profile_response(palette: list[str]) -> httpx.Response:
    profil = {
        "palette": palette, "font": "sans", "tone": "sobre et direct",
        "rules_do": ["garder du blanc"], "rules_avoid": ["les dégradés"],
        "summary": "Une identité violette, nette et contemporaine.",
    }
    return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(profil)}]}]})


def test_analyze_site_brand_refuses_a_color_absent_from_the_site():
    faits = extract(PAGE, [FEUILLE], url="https://smartduck.fr/")
    appels = []

    def handler(request: httpx.Request) -> httpx.Response:
        appels.append(json.loads(request.content))
        if len(appels) == 1:
            return _profile_response(["#7a3ff2", "#ff0000"])
        return _profile_response(["#7a3ff2", "#ffffff", "#1a1a2e"])

    profil = analyze_site_brand(faits, {"name": "Atelier"}, api_key="test-key",
                                transport=httpx.MockTransport(handler))
    assert len(appels) == 2
    assert "#ff0000" in json.dumps(appels[1], ensure_ascii=False)
    assert profil["palette"] == ["#7a3ff2", "#ffffff", "#1a1a2e"]


def test_analyze_site_brand_gives_up_rather_than_invent_a_palette():
    faits = extract(PAGE, [FEUILLE], url="https://smartduck.fr/")

    def handler(request: httpx.Request) -> httpx.Response:
        return _profile_response(["#111111", "#222222"])

    with pytest.raises(LunaAPIError):
        analyze_site_brand(faits, {"name": "Atelier"}, api_key="test-key",
                           transport=httpx.MockTransport(handler))


def test_font_shorthand_and_icon_fonts_do_not_pollute_the_families():
    """La propriete raccourcie porte la famille apres la taille, pas avant."""
    assert _families("font", '400 15px/1.55 system-ui, "Segoe UI", Roboto') == ["Segoe UI", "Roboto"]
    assert _families("font", "600 14px system-ui") == []
    assert _families("font-family", "eicons") == []
    assert _families("font-family", "var(--police), sans-serif") == []
    assert _families("font-family", '"Open Sans", sans-serif') == ["Open Sans"]


def test_site_name_keeps_the_brand_and_drops_the_promise():
    assert site_name({"title": "smartduck : épilation laser définitive, prix tout compris",
                      "url": "https://smartduck.fr/"}) == "smartduck"
    assert site_name({"title": "Atelier Rivage — Menuiserie", "url": "https://x.fr/"}) == "Atelier Rivage"
    # Un titre sans separateur et trop long : le domaine ne ment jamais.
    assert site_name({"title": "Bienvenue sur le site officiel de la menuiserie artisanale du Grand Ouest",
                      "url": "https://www.menuiserie-ouest.fr/"}) == "menuiserie-ouest"
    assert site_name({"title": "", "url": "https://smartduck.fr/"}) == "smartduck"
