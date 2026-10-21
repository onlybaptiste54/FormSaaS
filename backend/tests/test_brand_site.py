import json

import httpx
import pytest

from app.brand_site import (MAX_IMAGES, SiteError, _families, accent_color, check_url, extract,
                            fetch_image, image_candidates, proxy_path, read_site, sign_image,
                            site_name, usable_images)
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


def test_accent_color_skips_the_neutrals_that_cover_a_site():
    """Classer par frequence met le blanc en tete et relegue la signature."""
    releve = [{"value": "#ffffff"}, {"value": "#000000"}, {"value": "#5b2d8b"},
              {"value": "#69727d"}, {"value": "#d9534f"}]
    assert accent_color(releve) == "#5b2d8b"
    assert accent_color([{"value": "#ffffff"}, {"value": "#333333"}]) is None


def test_extract_names_the_accent_of_the_site():
    faits = extract(PAGE, [FEUILLE], url="https://smartduck.fr/")
    assert faits["accent"] == "#7a3ff2"


PAGE_VISUELS = (
    '<html><head><title>Smart Duck</title>'
    '<meta property="og:image" content="https://smartduck.fr/partage.jpg">'
    '<style>.hero{background-image:url("https://smartduck.fr/fond.jpg")}</style>'
    '</head><body>'
    '<img src="/media/equipe.jpg" alt="L equipe en cabine">'
    '<img src="https://smartduck.fr/media/equipe.jpg" alt="doublon">'
    '<img src="/media/icon-check.svg" alt="">'
    '<img src="data:image/gif;base64,R0lGOD" alt="">'
    '<img srcset="/media/large.jpg 2x, /media/small.jpg 1x" alt="Cabine">'
    '</body></html>'
)


def test_image_candidates_resolves_filters_and_deduplicates():
    candidats = image_candidates(_parse(PAGE_VISUELS), [], base_url="https://smartduck.fr/")
    urls = [c["url"] for c in candidats]
    assert urls[0] == "https://smartduck.fr/partage.jpg", "le visuel de partage passe en tete"
    assert urls.count("https://smartduck.fr/media/equipe.jpg") == 1, "le doublon absolu est fusionne"
    assert "https://smartduck.fr/media/large.jpg" in urls, "srcset est lu"
    assert not any("icon" in url for url in urls), "les pictogrammes sont ecartes"
    assert not any(url.startswith("data:") for url in urls)
    alt = next(c["alt"] for c in candidats if c["url"].endswith("equipe.jpg"))
    assert alt == "L equipe en cabine"


def test_image_candidates_reads_css_backgrounds():
    faits = extract(PAGE_VISUELS, [], url="https://smartduck.fr/")
    assert "https://smartduck.fr/fond.jpg" in [c["url"] for c in faits["images"]]


def test_usable_images_drops_what_does_not_exist_or_weighs_nothing():
    def handler(request: httpx.Request) -> httpx.Response:
        chemin = request.url.path
        if chemin.endswith("absente.jpg"):
            return httpx.Response(404)
        if chemin.endswith("page.jpg"):
            return httpx.Response(200, headers={"content-type": "text/html"})
        if chemin.endswith("pixel.jpg"):
            return httpx.Response(200, headers={"content-type": "image/jpeg", "content-length": "80"})
        return httpx.Response(200, headers={"content-type": "image/jpeg", "content-length": "250000"})

    candidats = [{"url": f"https://smartduck.fr/{nom}", "alt": ""} for nom in
                 ("absente.jpg", "page.jpg", "pixel.jpg", "vraie.jpg", "autre.jpg")]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        gardees = usable_images(candidats, client=client, resolve=PUBLIC)
    assert [g["url"].rsplit("/", 1)[-1] for g in gardees] == ["vraie.jpg", "autre.jpg"]
    assert gardees[0]["type"] == "image/jpeg"


def test_usable_images_revalidates_a_redirect_towards_a_private_address():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://10.0.0.5/secret.jpg"})

    def resolve(host):
        return ["10.0.0.5"] if host == "10.0.0.5" else ["93.184.216.34"]

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert usable_images([{"url": "https://smartduck.fr/a.jpg", "alt": ""}], client=client, resolve=resolve) == []


def _parse(html: str):
    from app.brand_site import _Page
    page = _Page()
    page.feed(html)
    page.close()
    return page


def test_image_candidates_keeps_only_the_brand_own_domain():
    """Les avatars d avis clients heberges chez Google sont des visages tiers."""
    html = ('<body><img src="https://smartduck.fr/media/cabine.jpg" alt="Cabine">'
            '<img src="https://media.smartduck.fr/salle.jpg" alt="Salle">'
            '<img src="https://lh3.googleusercontent.com/a/ACg8ocI" alt="Avis de Sophie">'
            '</body>')
    urls = [c["url"] for c in image_candidates(_parse(html), [], base_url="https://www.smartduck.fr/")]
    assert urls == ["https://smartduck.fr/media/cabine.jpg", "https://media.smartduck.fr/salle.jpg"]


def test_proxy_path_is_signed_and_reversible():
    chemin = proxy_path("https://smartduck.fr/a.png", "secret-de-test")
    assert chemin.startswith("/media/brand?u=https%3A%2F%2Fsmartduck.fr%2Fa.png&s=")
    assert chemin.endswith(sign_image("https://smartduck.fr/a.png", "secret-de-test"))
    # Une autre URL, ou un autre secret, ne donne pas la meme signature.
    assert sign_image("https://ailleurs.test/a.png", "secret-de-test") not in chemin
    assert sign_image("https://smartduck.fr/a.png", "autre-secret") not in chemin


def test_fetch_image_refuses_what_is_not_an_image():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("page.html"):
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 9000)
        if request.url.path.endswith("minuscule.png"):
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"x" * 10)
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"x" * 9000)

    transport = httpx.MockTransport(handler)
    for mauvais in ("https://smartduck.fr/page.html", "https://smartduck.fr/minuscule.png"):
        with pytest.raises(SiteError):
            fetch_image(mauvais, transport=transport, resolve=PUBLIC)
    contenu, type_mime = fetch_image("https://smartduck.fr/vraie.png", transport=transport, resolve=PUBLIC)
    assert type_mime == "image/png" and len(contenu) == 9000


def test_fetch_image_revalidates_redirects_towards_private_addresses():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/api/health"})

    def resolve(host):
        return ["127.0.0.1"] if host == "127.0.0.1" else ["93.184.216.34"]

    with pytest.raises(SiteError, match="réseau privé"):
        fetch_image("https://smartduck.fr/a.png", transport=httpx.MockTransport(handler), resolve=resolve)
