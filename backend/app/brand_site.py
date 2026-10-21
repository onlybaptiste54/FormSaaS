"""Lecture d'une charte graphique depuis une URL publique.

L'extraction est déterministe : on télécharge la page et ses feuilles de style,
on relève les couleurs et les polices réellement déclarées, avec leur rôle et
leur fréquence, et on rend des faits. L'interprétation — quelle couleur est
structurante, quel ton se dégage — revient au modèle, qui reçoit ces faits.

L'URL vient de l'utilisateur, donc le téléchargement est traité comme hostile :
schéma restreint, adresses privées refusées à chaque saut, taille, délai et
nombre de redirections plafonnés. Sans cette garde, le formulaire de création
devient un moyen d'aller interroger les services internes depuis l'API.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from collections import Counter
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
import tinycss2


MAX_BYTES = 2_000_000
MAX_STYLESHEETS = 4
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 10.0
USER_AGENT = "SillageBrandReader/1.0 (+https://sillage.fr)"

# Familles génériques : elles ne disent rien de la marque.
_GENERIC_FONTS = {
    "sans-serif", "serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-sans-serif", "ui-serif", "ui-monospace", "ui-rounded", "inherit",
    "initial", "unset", "revert", "-apple-system", "blinkmacsystemfont",
}

_ROLES = (
    ("fond", ("background", "background-color", "background-image")),
    ("texte", ("color", "-webkit-text-fill-color")),
    ("bordure", ("border", "border-color", "border-top-color", "border-bottom-color",
                 "border-left-color", "border-right-color", "outline-color")),
)

# Les longueurs vont de la plus longue à la plus courte : une alternance qui
# commence par {3} lirait #7A3FF2 comme #7A3, soit une couleur inventée.
_HEX = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})")
_RGB = re.compile(r"rgba?\(\s*([0-9.]+)[\s,]+([0-9.]+)[\s,]+([0-9.]+)")


class SiteError(ValueError):
    """Le site ne peut pas être lu, avec une raison dicible à l'utilisateur."""


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SiteError(f"Le domaine « {host} » est introuvable.") from exc
    return [info[4][0] for info in infos]


def check_url(url: str, *, resolve=_resolve) -> str:
    """Refuse tout ce qui n'est pas un site public, avant le moindre appel."""
    url = url.strip()
    if not urlsplit(url).scheme:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise SiteError("Seules les adresses http et https peuvent être lues.")
    if not parts.hostname:
        raise SiteError("Cette adresse ne contient pas de domaine.")
    for address in resolve(parts.hostname):
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise SiteError("Cette adresse ne mène pas à un site public.") from None
        if not ip.is_global or ip.is_multicast:
            raise SiteError("Cette adresse mène à un réseau privé : elle ne peut pas être lue.")
    return url


def _get(client: httpx.Client, url: str, *, resolve) -> tuple[str, str]:
    """Suit les redirections à la main : chaque saut est revalidé."""
    for _ in range(MAX_REDIRECTS + 1):
        url = check_url(url, resolve=resolve)
        response = client.get(url, follow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise SiteError("Le site renvoie une redirection incomplète.")
            url = urljoin(url, location)
            continue
        if response.status_code >= 400:
            raise SiteError(f"Le site a répondu {response.status_code}.")
        return url, response.content[:MAX_BYTES].decode(response.encoding or "utf-8", "replace")
    raise SiteError("Le site enchaîne trop de redirections.")


class _Page(HTMLParser):
    """Ce qui nous intéresse dans le document : styles, titre, intertitres."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stylesheets: list[str] = []
        self.inline_css: list[str] = []
        self.style_attrs: list[str] = []
        self.title = ""
        self.description = ""
        self.headings: list[str] = []
        self.images: list[tuple[str, str]] = []
        self.og_image = ""
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = {key: (value or "") for key, value in attrs}
        if style := attributes.get("style"):
            self.style_attrs.append(style)
        if tag == "img":
            source = attributes.get("src") or attributes.get("data-src") or ""
            if not source and (jeu := attributes.get("srcset")):
                source = jeu.split(",")[0].strip().split(" ")[0]
            if source:
                self.images.append((source, attributes.get("alt", "").strip()[:120]))
        if tag == "link" and "stylesheet" in attributes.get("rel", "").lower():
            if href := attributes.get("href"):
                self.stylesheets.append(href)
        elif tag == "style":
            self._capture = "style"
        elif tag == "title":
            self._capture = "title"
        elif tag in ("h1", "h2", "h3"):
            self._capture = "heading"
        elif tag == "meta":
            nom = (attributes.get("name") or attributes.get("property") or "").lower()
            if nom in ("description", "og:description") and not self.description:
                self.description = attributes.get("content", "")[:300]
            elif nom in ("og:image", "twitter:image") and not self.og_image:
                self.og_image = attributes.get("content", "")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "title", "h1", "h2", "h3"):
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture == "style":
            self.inline_css.append(data)
        elif self._capture == "title" and not self.title:
            self.title = data.strip()[:160]
        elif self._capture == "heading" and data.strip() and len(self.headings) < 8:
            self.headings.append(data.strip()[:120])


def _normalise_color(value: str) -> str | None:
    if match := _HEX.match(value):
        digits = match.group(1)
        if len(digits) in (3, 4):
            digits = "".join(char * 2 for char in digits[:3])
        return "#" + digits[:6].lower()
    if match := _RGB.match(value):
        try:
            channels = [max(0, min(255, round(float(part)))) for part in match.groups()]
        except ValueError:
            return None
        return "#{:02x}{:02x}{:02x}".format(*channels)
    return None


def _colors_in(value: str) -> list[str]:
    found = []
    for pattern in (_HEX, _RGB):
        for match in pattern.finditer(value):
            if color := _normalise_color(match.group(0)):
                found.append(color)
    return found


_SIZE_TOKEN = re.compile(r"^\S*\d\S*$")
_ICON_FONT = re.compile(r"icons?$", re.IGNORECASE)


def _families(propriete: str, valeur: str) -> list[str]:
    """Les familles nommées d'une déclaration, dans l'ordre de préférence.

    La propriété raccourcie `font` porte la famille à la fin, après la graisse
    et la taille : la lire comme `font-family` donnerait « 400 15px/1.55 ».
    """
    if propriete == "font":
        mots = valeur.split()
        derniere_taille = max((index for index, mot in enumerate(mots) if _SIZE_TOKEN.match(mot)), default=-1)
        valeur = " ".join(mots[derniere_taille + 1:])

    familles = []
    for famille in valeur.split(","):
        famille = famille.strip().strip("\"'")[:60]
        if not famille or famille.startswith("var("):
            continue
        # Les polices d'icônes habillent des pictogrammes, pas la marque.
        if famille.lower() in _GENERIC_FONTS or _ICON_FONT.search(famille):
            continue
        familles.append(famille)
    return familles


def _declarations(css: str):
    """Toutes les déclarations du CSS, y compris sous @media et @supports."""
    def walk(rules):
        for rule in rules:
            if rule.type == "qualified-rule":
                yield from tinycss2.parse_blocks_contents(rule.content)
            elif rule.type == "at-rule" and rule.content:
                yield from walk(tinycss2.parse_rule_list(rule.content, skip_comments=True, skip_whitespace=True))

    for node in walk(tinycss2.parse_stylesheet(css, skip_comments=True, skip_whitespace=True)):
        if node.type == "declaration":
            yield node.lower_name, tinycss2.serialize(node.value).strip()


MAX_IMAGES = 6
MIN_IMAGE_BYTES = 4_000
MAX_IMAGE_BYTES = 6_000_000

_CSS_URL = re.compile(r"""url\(\s*['"]?([^)'"]+)""")
# Les pictogrammes et les pixels de mesure ne racontent rien de la marque. Le
# logo, lui, est garde : une page en a besoin pour s'identifier.
_DECORATIVE = re.compile(
    r"(sprite|icon|favicon|pixel|spacer|blank|placeholder|loader|avatar"
    r"|badge|flag|arrow|chevron|bullet|separator|pattern)", re.IGNORECASE)


def _domain(host: str) -> str:
    """Les deux derniers labels : media.smartduck.fr et smartduck.fr sont un."""
    return ".".join((host or "").lower().removeprefix("www.").split(".")[-2:])


def image_candidates(page: "_Page", css_urls: list[str], *, base_url: str) -> list[dict]:
    """Les visuels declares par le site, adresses absolues et texte alternatif.

    Seules les images servies par le domaine du site sont retenues. Les sites
    affichent volontiers des avatars d'avis clients heberges chez Google :
    ce sont les visages de personnes reelles, qui n'ont rien a faire sur une
    page de captation et ne disent rien de la marque.
    """
    domaine = _domain(urlsplit(base_url).hostname or "")
    sources: list[tuple[str, str]] = []
    if page.og_image:
        # L'image de partage est celle que le site met lui-meme en avant.
        sources.append((page.og_image, "Visuel mis en avant par le site"))
    sources += page.images
    sources += [(url, "") for url in css_urls]

    vus: set[str] = set()
    candidats: list[dict] = []
    for source, alt in sources:
        source = (source or "").strip()
        if not source or source.startswith("data:"):
            continue
        absolu = urljoin(base_url, source)
        parts = urlsplit(absolu)
        if parts.scheme != "https" or not parts.hostname or _DECORATIVE.search(parts.path):
            continue
        if domaine and _domain(parts.hostname) != domaine:
            continue
        if absolu in vus:
            continue
        vus.add(absolu)
        candidats.append({"url": absolu, "alt": alt})
        if len(candidats) >= 20:
            break
    return candidats


def _head(client: httpx.Client, url: str, *, resolve) -> httpx.Response:
    """Un HEAD qui revalide chaque redirection, comme le telechargement."""
    for _ in range(MAX_REDIRECTS + 1):
        url = check_url(url, resolve=resolve)
        response = client.head(url, follow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise SiteError("Redirection incomplete.")
            url = urljoin(url, location)
            continue
        return response
    raise SiteError("Trop de redirections.")


def usable_images(candidats: list[dict], *, client: httpx.Client, resolve=_resolve) -> list[dict]:
    """Ne garde que les visuels qui existent vraiment et pesent leur poids.

    Une URL morte ou un pixel de mesure dans la page produite serait pire que
    pas d'image du tout : on verifie avant de les proposer au modele.
    """
    gardees: list[dict] = []
    for candidat in candidats:
        if len(gardees) >= MAX_IMAGES:
            break
        try:
            response = _head(client, candidat["url"], resolve=resolve)
        except (SiteError, httpx.HTTPError):
            continue
        if response.status_code >= 400:
            continue
        type_mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
        if not type_mime.startswith("image/"):
            continue
        taille = response.headers.get("content-length")
        if taille and taille.isdigit() and not (MIN_IMAGE_BYTES <= int(taille) <= MAX_IMAGE_BYTES):
            continue
        gardees.append({**candidat, "type": type_mime})
    return gardees


def _saturation_lightness(couleur: str) -> tuple[float, float]:
    rouge, vert, bleu = (int(couleur[index:index + 2], 16) / 255 for index in (1, 3, 5))
    haut, bas = max(rouge, vert, bleu), min(rouge, vert, bleu)
    clarte = (haut + bas) / 2
    if haut == bas:
        return 0.0, clarte
    ecart = haut - bas
    return ecart / (2 - haut - bas if clarte > 0.5 else haut + bas), clarte


def accent_color(couleurs: list[dict]) -> str | None:
    """La couleur qui signe la marque, pas celle qui occupe le plus de surface.

    Un site est surtout fait de blanc, de noir et de gris : les classer par
    fréquence met donc le neutre en tête et relègue la couleur distinctive au
    troisième rang, où elle finit en garniture. On écarte les neutres et on
    garde la teinte franche la plus employée.
    """
    for couleur in couleurs:
        saturation, clarte = _saturation_lightness(couleur["value"])
        if saturation >= 0.25 and 0.12 <= clarte <= 0.88:
            return couleur["value"]
    return None


def extract(html: str, stylesheets: list[str], *, url: str) -> dict:
    """Les faits bruts du site : couleurs par rôle, polices, titre, intertitres."""
    page = _Page()
    page.feed(html)
    page.close()

    par_role: dict[str, Counter] = {role: Counter() for role, _ in _ROLES}
    total: Counter = Counter()
    polices: Counter = Counter()
    fonds: list[str] = []
    sources = page.inline_css + stylesheets + ["x{" + attr + "}" for attr in page.style_attrs]
    for css in sources:
        for propriete, valeur in _declarations(css):
            if propriete.startswith("background"):
                fonds.extend(_CSS_URL.findall(valeur))
            if propriete in ("font-family", "font"):
                for famille in _families(propriete, valeur):
                    polices[famille] += 1
                    break
            for couleur in _colors_in(valeur):
                total[couleur] += 1
                for role, proprietes in _ROLES:
                    # Une variable CSS porte souvent la couleur de marque sans
                    # dire son rôle : on la compte partout plutôt que nulle part.
                    if propriete in proprietes or propriete.startswith("--"):
                        par_role[role][couleur] += 1

    couleurs = []
    for couleur, occurrences in total.most_common(12):
        roles = [role for role, compteur in par_role.items() if compteur[couleur]]
        couleurs.append({"value": couleur, "count": occurrences, "roles": roles})

    return {
        "url": url,
        "accent": accent_color(couleurs),
        "images": image_candidates(page, fonds, base_url=url),
        "title": page.title,
        "description": page.description,
        "headings": page.headings,
        "colors": couleurs,
        "fonts": [{"name": nom, "count": n} for nom, n in polices.most_common(6)],
        "stylesheets_read": len(stylesheets),
    }


_TITLE_SPLIT = re.compile(r"\s[:|–—]\s|\s[-]\s")


def site_name(facts: dict) -> str:
    """Le nom de la marque, tel qu'une page pourrait l'afficher.

    Le titre d'une page porte presque toujours la marque en tête, suivie d'un
    séparateur et d'une promesse (« smartduck : épilation laser définitive »).
    On garde la tête quand elle a une taille plausible, sinon on retombe sur le
    domaine, qui ne ment jamais.
    """
    titre = (facts.get("title") or "").strip()
    tete = _TITLE_SPLIT.split(titre)[0].strip() if titre else ""
    if 2 <= len(tete) <= 40:
        return tete

    hote = (urlsplit(facts.get("url") or "").hostname or "").removeprefix("www.")
    etiquette = hote.split(".")[0] if hote else ""
    return etiquette[:40] or "cette marque"


def read_site(url: str, *, transport: httpx.BaseTransport | None = None, resolve=_resolve) -> dict:
    """Télécharge un site public et en extrait les faits de charte graphique."""
    with httpx.Client(timeout=TIMEOUT_SECONDS, transport=transport,
                      headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:
        final_url, html = _get(client, url, resolve=resolve)

        page = _Page()
        page.feed(html)
        page.close()

        feuilles = []
        for href in page.stylesheets[:MAX_STYLESHEETS]:
            try:
                _, css = _get(client, urljoin(final_url, href), resolve=resolve)
            except (SiteError, httpx.HTTPError):
                continue  # une feuille inaccessible ne doit pas tout faire échouer
            feuilles.append(css)

        faits = extract(html, feuilles, url=final_url)
        faits["images"] = usable_images(faits["images"], client=client, resolve=resolve)
    return faits
