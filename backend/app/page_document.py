"""HTML documents stored for Sillage pages.

The legacy converter is deliberately self-contained: old form snapshots must
remain readable after the React renderer is removed.
"""

from __future__ import annotations

from html import escape, unescape
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import bleach
import tinycss2
from bleach._vendor import html5lib
from bleach.css_sanitizer import CSSSanitizer


MAX_PAGE_HTML = 250_000
_TAGS = frozenset("a abbr article aside b blockquote br button caption cite code col colgroup dd del details div dl dt em fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr i img input label legend li main mark nav ol option p picture pre q s section select small source span strong sub summary sup table tbody td textarea th thead time title tr u ul video".split()) | {"style"}
_GLOBAL_ATTRS = frozenset("class id title lang dir role aria-label aria-labelledby aria-describedby aria-hidden aria-pressed tabindex data-sillage data-sillage-next data-sillage-region data-luna-id data-field data-rating style".split())
_TAG_ATTRS = {
    "a": {"href", "target", "rel"}, "img": {"src", "alt", "width", "height", "loading"},
    "source": {"src", "type", "media"}, "video": {"poster", "controls", "width", "height"},
    "form": {"method", "novalidate"}, "input": {"name", "type", "value", "placeholder", "required", "checked", "min", "max", "step", "minlength", "maxlength", "autocomplete", "disabled"},
    "select": {"name", "required", "multiple", "disabled"},
    "textarea": {"name", "placeholder", "required", "rows", "minlength", "maxlength", "disabled"},
    "option": {"value", "selected", "disabled"}, "label": {"for"}, "button": {"type", "name", "value", "disabled"},
    "td": {"colspan", "rowspan"}, "th": {"scope", "colspan", "rowspan"},
}
_VOID = frozenset("br hr img input source col".split())
_DROP_CONTENT = frozenset("script iframe object embed svg math noscript template".split())
_DROP_VOID = frozenset("base link meta".split())
_CSS_BAD_PROPERTIES = frozenset({"behavior", "-moz-binding"})
_PAGE_CSP = (
    "default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; "
    # 'self' autorise le relais des visuels du client, servi a la meme origine
    # que la page. Sans lui, ils passent en https mais pas en http local.
    "img-src 'self' https: data:; object-src 'none'; base-uri 'none'; "
    "form-action 'none'; connect-src 'none'; frame-src 'none'"
)


# Les visuels du client sont servis par Sillage, a la meme origine que la page :
# une image d'une autre origine souille le canvas et casse la capture de zone.
PROXY_PREFIX = "/media/brand?"


def _safe_url(value: str, *, image: bool = False) -> bool:
    value = value.strip()
    if value.lower().startswith("https://"):
        return True
    # Seul ce chemin relatif est accepte : // mene ailleurs, pas chez nous.
    if image and value.startswith(PROXY_PREFIX):
        return True
    return image and bool(re.match(r"(?is)^data:image/(?:png|jpe?g|gif|webp|avif);base64,[a-z0-9+/=]+$", value))


def _safe_tokens(tokens: list, *, allow_image: bool = False) -> bool:
    for token in tokens:
        if token.type in {"error", "bad-url", "bad-string"}:
            return False
        if token.type == "url" and not (allow_image and _safe_url(token.value, image=True) and token.value.startswith("data:")):
            return False
        if token.type == "function":
            if token.lower_name in {"expression", "-moz-binding", "image-set", "-webkit-image-set"}:
                return False
            if token.lower_name == "url":
                value = tinycss2.serialize(token.arguments).strip().strip('"\'')
                if not (allow_image and _safe_url(value, image=True) and value.startswith("data:")):
                    return False
            elif not _safe_tokens(token.arguments, allow_image=allow_image):
                return False
        if hasattr(token, "content") and token.content is not None and not _safe_tokens(token.content, allow_image=allow_image):
            return False
    return True


def _clean_declarations(css: str) -> str:
    declarations = tinycss2.parse_declaration_list(css, skip_comments=True, skip_whitespace=True)
    output = []
    for item in declarations:
        if item.type != "declaration" or item.lower_name in _CSS_BAD_PROPERTIES:
            continue
        if not _safe_tokens(item.value, allow_image=True):
            continue
        value = tinycss2.serialize(item.value).strip()
        if value:
            output.append(f"{item.name}:{value}{'!important' if item.important else ''}")
    return ";".join(output)


def _clean_stylesheet(css: str) -> str:
    def rules(source: str) -> str:
        output = []
        for rule in tinycss2.parse_rule_list(source, skip_comments=True, skip_whitespace=True):
            if rule.type == "qualified-rule":
                if not _safe_tokens(rule.prelude):
                    continue
                declarations = _clean_declarations(tinycss2.serialize(rule.content))
                if declarations:
                    output.append(f"{tinycss2.serialize(rule.prelude)}{{{declarations}}}")
            elif rule.type == "at-rule" and rule.lower_at_keyword in {"media", "supports", "container", "layer", "keyframes", "-webkit-keyframes"} and rule.content is not None:
                if not _safe_tokens(rule.prelude):
                    continue
                nested = rules(tinycss2.serialize(rule.content))
                if nested:
                    output.append(f"@{rule.at_keyword} {tinycss2.serialize(rule.prelude)}{{{nested}}}")
        return "".join(output)
    return rules(css)


class _StyleGuard(HTMLParser):
    """Remove executable raw content and sanitize style blocks before Bleach."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.dropped: list[str] = []
        self.in_style = False
        self.style_parts: list[str] = []
        self.consent_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_VOID:
            return
        if self.consent_depth:
            if tag not in _VOID:
                self.consent_depth += 1
            return
        if self.dropped:
            if tag in _DROP_CONTENT:
                self.dropped.append(tag)
            return
        if tag in _DROP_CONTENT:
            self.dropped.append(tag)
            return
        if self.in_style:
            return
        if tag == "div" and ("data-sillage", "consent") in attrs:
            self.parts.append('<div data-sillage="consent"></div>')
            self.consent_depth = 1
            return
        if tag == "style":
            self.in_style = True
            self.style_parts = []
            return
        values = "".join(f' {name}="{escape(value or "", quote=True)}"' for name, value in attrs)
        self.parts.append(f"<{tag}{values}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self.consent_depth:
            self.consent_depth -= 1
            return
        if self.dropped:
            if tag == self.dropped[-1]:
                self.dropped.pop()
            return
        if self.in_style:
            if tag == "style":
                self.parts.append(f"<style>{_clean_stylesheet(''.join(self.style_parts))}</style>")
                self.in_style = False
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self.consent_depth:
            return
        if self.in_style:
            self.style_parts.append(data)
        elif not self.dropped:
            self.parts.append(escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if self.in_style:
            self.style_parts.append(f"&{name};")
        elif not self.dropped and not self.consent_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.in_style:
            self.style_parts.append(f"&#{name};")
        elif not self.dropped and not self.consent_depth:
            self.parts.append(f"&#{name};")


_NAME_KEYS = ("name", "prenom", "first_name", "fullname", "full_name")


def _first_name(answers: dict[str, object]) -> str:
    for key in _NAME_KEYS:
        value = answers.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip().split()[0]
    return ""


def _personalized_text(value: str, first_name: str) -> str:
    if "{prenom}" not in value:
        return value
    if first_name:
        return value.replace("{prenom}", escape(first_name, quote=False))
    return re.sub(r"\s+([.,])", r"\1", re.sub(r"\s*\{prenom\}\s*", " ", value))


class _TextVariables(HTMLParser):
    """Replace visitor variables in text nodes, never in markup or CSS."""

    def __init__(self, first_name: str) -> None:
        super().__init__(convert_charrefs=False)
        self.first_name = first_name
        self.parts: list[str] = []
        self.in_style = False

    def handle_decl(self, decl: str) -> None:
        self.parts.append(f"<!{decl}>")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self.get_starttag_text())
        if tag == "style":
            self.in_style = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(f"</{tag}>")
        if tag == "style":
            self.in_style = False

    def handle_data(self, data: str) -> None:
        self.parts.append(data if self.in_style else _personalized_text(data, self.first_name))

    def handle_entityref(self, name: str) -> None:
        self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.parts.append(f"&#{name};")


def personalize_page(html: str, answers: dict[str, object]) -> str:
    """Safely replace thank-you variables in sanitized document text."""
    renderer = _TextVariables(_first_name(answers))
    renderer.feed(html)
    return "".join(renderer.parts)


def _allowed_attr(tag: str, name: str, value: str) -> bool:
    if name.startswith("on") or name not in (_GLOBAL_ATTRS | _TAG_ATTRS.get(tag, set())):
        return False
    if name == "data-sillage":
        return (tag == "form" and value == "form") or (tag == "div" and value == "consent")
    if name == "data-sillage-region":
        return bool(re.fullmatch(r"[a-zA-Z][\w-]{0,63}", value))
    if name == "data-sillage-next":
        return tag in {"a", "button"} and value == ""
    if name in {"href", "src", "poster"}:
        return _safe_url(value, image=name != "href")
    if name == "target":
        return value == "_blank"
    if name == "style":
        return bool(_clean_declarations(value))
    if name == "type" and tag == "input":
        return value in {"text", "email", "tel", "number", "date", "radio", "checkbox", "hidden"}
    if name == "method":
        return value.lower() == "post"
    return True


class _PageCSS(CSSSanitizer):
    def sanitize_css(self, style: str) -> str:
        return _clean_declarations(style)


def _nodes(html: str):
    return html5lib.parseFragment(html, treebuilder="etree", namespaceHTMLElements=False)


def _label_text(node) -> str:
    pieces = [node.text or ""]
    for child in node:
        if child.tag not in {"input", "select", "textarea"}:
            pieces.append(_label_text(child))
        pieces.append(child.tail or "")
    return " ".join(" ".join(pieces).split()).removesuffix(" *")


def _manifest(html: str, *, require_form: bool) -> list[dict]:
    root = _nodes(html)
    parents = {child: parent for parent in root.iter() for child in parent}
    forms = [node for node in root.iter("form") if node.get("data-sillage") == "form"]
    if require_form and len(forms) != 1:
        raise ValueError("La page de formulaire doit contenir un seul <form data-sillage=\"form\">.")
    if len(forms) > 1:
        raise ValueError("Une page ne peut contenir qu'un formulaire Sillage.")
    placeholders = [node for node in root.iter("div") if node.get("data-sillage") == "consent"]
    manifest: list[dict] = []
    if not forms:
        if placeholders:
            raise ValueError("Le consentement Sillage doit être placé dans le formulaire.")
        return manifest
    form = forms[0]
    consent = [node for node in form.iter("div") if node.get("data-sillage") == "consent"]
    if len(placeholders) != 1 or len(consent) != 1:
        raise ValueError("Le formulaire doit contenir un seul <div data-sillage=\"consent\">.")
    seen: dict[str, dict] = {}
    for node in form.iter():
        if node.tag not in {"input", "select", "textarea"}:
            continue
        name = node.get("name", "").strip()
        kind = node.get("type", "text") if node.tag == "input" else node.tag
        if kind in {"submit", "button", "reset", "hidden"} or not name:
            continue
        if name == "sillage_consent":
            raise ValueError("Le nom sillage_consent est réservé au consentement serveur.")
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,39}", name):
            raise ValueError(f"Nom de champ invalide : {name[:64]}")
        labels = [label for label in form.iter("label") if node.get("id") and label.get("for") == node.get("id")]
        parent = parents.get(node)
        while not labels and parent is not None and parent is not form:
            if parent.tag == "label" and kind != "radio":
                labels = [parent]
            elif parent.tag == "fieldset":
                legend = next(parent.iter("legend"), None)
                if legend is not None:
                    labels = [legend]
            parent = parents.get(parent)
        label = _label_text(labels[0]) if labels else name
        field_type = "radio" if kind == "radio" else kind
        if node.tag == "select":
            options = []
            for option in node.iter("option"):
                value = option.get("value")
                if value is None:
                    value = "".join(option.itertext()).strip()
                if value:
                    options.append(value)
        elif kind == "radio":
            options = [item.get("value", "") for item in form.iter("input") if item.get("name") == name and item.get("type") == "radio"]
        else:
            options = []
        field = {"id": name, "name": name, "type": field_type, "label": label,
                 "required": node.get("required") is not None}
        if options:
            field["options"] = list(dict.fromkeys(options))
        if kind == "radio" and node.get("data-rating"):
            field["type"] = "rating"
            field["scale"] = len(options)
        if name in seen:
            if kind != "radio" or seen[name]["type"] not in {"radio", "rating"}:
                raise ValueError(f"Nom de champ utilisé plusieurs fois : {name}")
            seen[name]["required"] |= field["required"]
            continue
        seen[name] = field
        manifest.append(field)
        if len(manifest) > 40:
            raise ValueError("Le formulaire dépasse la limite de 40 champs.")
    return manifest


def prepare_page(html: str, *, require_form: bool) -> tuple[str, list[dict]]:
    """Return stored safe HTML and its collection manifest."""
    if not isinstance(html, str) or not html.strip():
        raise ValueError("La page HTML est vide.")
    if len(html) > MAX_PAGE_HTML:
        raise ValueError(f"La page HTML dépasse la limite de {MAX_PAGE_HTML} caractères.")
    guard = _StyleGuard()
    guard.feed(html)
    guarded = "".join(guard.parts)
    cleaned = bleach.clean(guarded, tags=_TAGS, attributes=_allowed_attr,
                           protocols={"https", "data", ""}, strip=True,
                           strip_comments=True, css_sanitizer=_PageCSS())
    cleaned = _clean_links(cleaned)
    manifest = _manifest(cleaned, require_form=require_form)
    document = f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>{cleaned}</body></html>'
    if len(document) > MAX_PAGE_HTML:
        raise ValueError(f"La page HTML assainie dépasse la limite de {MAX_PAGE_HTML} caractères.")
    return document, manifest


def render_page(html: str, consent_text: str, answers: dict[str, object] | None = None) -> str:
    """Inject server-owned legal consent into a previously sanitized page."""
    if answers is not None:
        html = personalize_page(html, answers)
    # This meta policy applies inside srcdoc. The parent intercepts submit and
    # calls preventDefault, so blocking native form navigation does not affect
    # collection. The public Next route also sets a response CSP header.
    csp = f'<meta http-equiv="Content-Security-Policy" content="{_PAGE_CSP}">'
    html = html.replace("<head>", f"<head>{csp}", 1)
    root = _nodes(html)
    forms = [node for node in root.iter("form") if node.get("data-sillage") == "form"]
    placeholders = [node for node in root.iter("div") if node.get("data-sillage") == "consent"]
    in_form = [node for node in forms[0].iter("div") if node.get("data-sillage") == "consent"] if len(forms) == 1 else []
    if len(placeholders) != 1 or len(in_form) != 1:
        return html
    # The stored placeholder is emptied at render time, so Luna cannot replace
    # the legal text or add a pre-checked consent control.
    safe_text = escape(consent_text, quote=False)
    replacement = f'<div data-sillage="consent"><label class="public-consent"><input type="checkbox" name="sillage_consent" value="yes" required><span>{safe_text}</span></label></div>'
    return re.sub(r'<div\b(?=[^>]*\bdata-sillage="consent")[^>]*>.*?</div>', lambda _: replacement, html,
                  count=1, flags=re.IGNORECASE | re.DOTALL)

_BACKGROUNDS = {
    "warm": ("#efeee8", "#efeee8", False),
    "mist": ("#eaf0ed", "#eaf0ed", False),
    "white": ("#ffffff", "#ffffff", False),
    "ink": ("#17231d", "#17231d", True),
}
_RADII = {"subtle": 7, "rounded": 18, "pill": 28}
_STYLE_DEFAULTS = {
    "surface_alpha": 1, "border_alpha": 1, "accent": "#2f6b4f",
    "accent_ink": "#ffffff", "blur_px": 0, "glow": 0,
    "font": "sans", "heading_font": "serif", "title_scale": 1,
    "title_case": "normal",
}
_FONTS = {
    "sans": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
    "grotesk": "'Segoe UI Variable Display', 'Segoe UI', system-ui, sans-serif",
    "serif": "Georgia, 'Times New Roman', serif",
    "mono": "ui-monospace, 'Cascadia Mono', Menlo, monospace",
}


def _text(value: object) -> str:
    return escape(str(value or ""), quote=True)


def _rgb(value: str) -> str:
    hex_value = value.lstrip("#")
    return " ".join(str(int(hex_value[index:index + 2], 16)) for index in (0, 2, 4))


def _style(form_state: dict) -> tuple[dict, dict]:
    design = form_state.get("design") or {}
    background = _BACKGROUNDS.get(design.get("background"), _BACKGROUNDS["warm"])
    style = {
        **_STYLE_DEFAULTS,
        "page_from": background[0], "page_to": background[1],
        "surface": "#1e2b24" if background[2] else "#ffffff",
        "border": "#3a4a41" if background[2] else "#d9ddd6",
        "ink": "#f2f5f1" if background[2] else "#17211b",
        "ink_soft": "#adbab2" if background[2] else "#566159",
        "radius_px": _RADII.get(design.get("radius"), 18),
        **(design.get("style") or {}),
    }
    return design, style


def _field_html(field: dict) -> str:
    kind = str(field.get("type") or "text")
    if kind == "consent":
        return '<div data-sillage="consent"></div>'
    name = _text(field.get("id") or field.get("name"))
    label = _text(field.get("label"))
    required = " required" if field.get("required") else ""
    title = f"{label}{' *' if required else ''}"
    common = f' name="{name}" id="field-{name}"{required}'
    placeholder = f' placeholder="{_text(field.get("placeholder"))}"' if field.get("placeholder") else ""
    if kind in {"radio", "rating"}:
        values = field.get("options") or [] if kind == "radio" else range(1, max(1, min(int(field.get("scale") or 5), 20)) + 1)
        choices = "".join(
            f'<label class="choice"><input type="radio" name="{name}" value="{_text(value)}"{required}{" data-rating=\"1\"" if kind == "rating" else ""}>'
            f'<span>{_text(value)}</span></label>' for value in values
        )
        return f'<fieldset class="public-field" data-luna-id="field:{name}" data-field="{name}"><legend data-luna-id="field:{name}.label">{title}</legend><div class="choices">{choices}</div></fieldset>'
    if kind == "select":
        options = '<option value="">Sélectionnez une option</option>' + "".join(
            f'<option value="{_text(option)}">{_text(option)}</option>' for option in field.get("options") or []
        )
        control = f'<select{common}>{options}</select>'
    elif kind == "textarea":
        control = f'<textarea{common}{placeholder}></textarea>'
    else:
        input_type = kind if kind in {"text", "email", "tel", "date", "number"} else "text"
        control = f'<input type="{input_type}"{common}{placeholder}>'
    return f'<label class="public-field" for="field-{name}" data-luna-id="field:{name}" data-field="{name}"><span data-luna-id="field:{name}.label">{title}</span>{control}</label>'


def legacy_to_html(form_state: dict, company: dict, *, role: str = "form") -> str:
    """Replay the old form's visible content in a standalone responsive page."""
    design, style = _style(form_state)
    content = {"eyebrow": "PRENONS CONTACT", "submit_label": "Envoyer ma réponse",
               "trust_note": "Vos données sont protégées et utilisées uniquement pour traiter votre demande.",
               **(form_state.get("content") or {})}
    company_name = str(company.get("name") or "")
    display = design.get("brand_display") or "logo_and_name"
    logo = company.get("logo")
    brand = ""
    if display != "hidden":
        mark = ""
        if display != "name":
            initials = "".join(word[0] for word in company_name.split() if word)[:2].upper()
            # Stored logos are normalized by the image URL policy in prepare_page.
            mark = f'<img src="{_text(logo)}" alt="{_text(company_name)}">' if logo else f'<span>{_text(initials)}</span>'
        brand = f'<div class="public-brand brand-{_text(design.get("brand_size") or "medium")}" data-luna-id="brand">{mark}'
        if display != "logo":
            brand += f'<strong>{_text(company_name)}</strong>'
        brand += "</div>"
    legal = _text(company.get("legal_name") or company_name)
    if company.get("address"):
        legal += f' · {_text(company["address"])}'
    if company.get("dpo_email"):
        legal += f' · Vos données : {_text(company["dpo_email"])}'
    footer = f'<footer data-luna-id="footer">{legal}</footer>'
    radius = float(style["radius_px"])
    surface_rgb = _rgb(style["surface"])
    border_rgb = _rgb(style["border"])
    accent_rgb = _rgb(style["accent"])
    surface_color = f'rgb({surface_rgb} / {style["surface_alpha"]})'
    border_color = f'rgb({border_rgb} / {style["border_alpha"]})'
    input_surface = f'rgb({surface_rgb} / {float(style["surface_alpha"])*.55})'
    css = f"""
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:50px 20px;background:linear-gradient(160deg,{style['page_from']},{style['page_to']});color:{style['ink']};font-family:{_FONTS.get(style['font'],_FONTS['sans'])}}}
body:before{{content:'';position:fixed;inset:0 0 auto;height:5px;background:{_text(company.get('primary_color') or style['accent'])}}}
.public-card{{width:min(620px,100%);padding:42px 50px;background:{surface_color};border:1px solid {border_color};border-radius:{radius}px;box-shadow:0 24px 60px rgb(0 0 0 / .35),0 0 {float(style['glow'])*70}px rgb({accent_rgb} / {float(style['glow'])*.45});backdrop-filter:blur({style['blur_px']}px)}}
.public-brand{{display:flex;align-items:center;gap:10px;margin-bottom:35px}}.public-brand>span{{width:37px;height:37px;border-radius:50%;display:grid;place-items:center;background:rgb({accent_rgb} / .18);color:{style['accent']};font:12px Georgia,serif}}.public-brand img{{width:38px;height:38px;object-fit:contain}}.public-brand strong{{font-size:13px}}.brand-small img,.brand-small>span{{width:28px;height:28px}}.brand-large img,.brand-large>span{{width:56px;height:56px}}
header h1{{font-family:{_FONTS.get(style['heading_font'],_FONTS['serif'])};font-size:{36*float(style['title_scale'])}px;font-weight:500;line-height:1.08;margin:0 0 12px;text-transform:{'uppercase' if style['title_case']=='uppercase' else 'none'}}}header p{{font-size:14px;line-height:1.65;color:{style['ink_soft']}}}.eyebrow{{font-size:11px;font-weight:750;letter-spacing:.1em;color:{style['accent']}}}
.public-fields{{display:grid;gap:19px;margin-top:30px}}.public-field{{display:grid;gap:8px;margin:0;padding:0;border:0;font-size:12px;font-weight:700}}.public-field>span,.public-field legend{{color:{style['ink']}}}.public-field input:not([type=radio]),.public-field textarea,.public-field select{{width:100%;min-height:42px;padding:10px 12px;background:{input_surface};border:1px solid {border_color};border-radius:{min(radius*.55,18)}px;color:{style['ink']};font:400 13px {_FONTS.get(style['font'],_FONTS['sans'])}}}.public-field textarea{{min-height:90px}}.public-field input:focus,.public-field textarea:focus,.public-field select:focus{{outline:3px solid {style['accent']};outline-offset:1px}}
.choices{{display:flex;flex-wrap:wrap;gap:8px}}.choice input{{position:absolute;opacity:0}}.choice span{{display:grid;place-items:center;min-width:72px;min-height:40px;padding:8px;border:1px solid {style['border']};border-radius:8px;font-size:11px;cursor:pointer}}.choice input:checked+span{{background:{style['accent']};border-color:{style['accent']};color:{style['accent_ink']}}}.choice input:focus-visible+span{{outline:2px solid {style['accent']};outline-offset:2px}}
.public-submit{{width:100%;min-height:48px;margin-top:25px;border:0;border-radius:{min(radius*.55,18)}px;background:{style['accent']};color:{style['accent_ink']};display:flex;align-items:center;justify-content:center;text-decoration:none;font-weight:750;cursor:pointer;box-shadow:0 0 {float(style['glow'])*40}px rgb({accent_rgb} / {float(style['glow'])*.55})}}.secure-note{{margin:12px 0 25px;text-align:center;font-size:9px;color:{style['ink_soft']}}}footer{{border-top:1px solid {border_color};padding-top:17px;text-align:center;font-size:8px;color:{style['ink_soft']}}}
.thank-you-card{{text-align:center}}.thank-you-card .public-brand{{justify-content:center}}.thanks-check{{margin:0 auto 20px;width:48px;height:48px;border-radius:50%;display:grid;place-items:center;background:{style['accent']};color:{style['accent_ink']}}}.thank-you-card h1{{font-family:{_FONTS.get(style['heading_font'],_FONTS['serif'])};font-size:40px;font-weight:500}}
.design-layout-minimal{{box-shadow:none;border-color:transparent}}.design-density-compact{{padding-top:30px;padding-bottom:30px}}.design-density-compact .public-fields{{gap:12px;margin-top:20px}}.design-density-airy{{padding-top:55px;padding-bottom:55px}}.design-density-airy .public-fields{{gap:24px;margin-top:36px}}.design-fields-filled input:not([type=radio]),.design-fields-filled textarea,.design-fields-filled select{{border-color:transparent;background:#f1f3ef}}.design-fields-underline input:not([type=radio]),.design-fields-underline textarea,.design-fields-underline select{{border:0;border-bottom:1px solid {style['border']};border-radius:0;background:transparent}}.design-button-outline .public-submit{{background:transparent;color:{style['accent']};border:1px solid {style['accent']}}}.design-button-soft .public-submit{{background:color-mix(in srgb,{style['accent']} 13%,white);color:{style['accent']}}}.design-heading-center header{{text-align:center}}
.design-layout-split:not(.thank-you-card){{width:min(900px,100%);display:grid;grid-template-columns:minmax(0,.85fr) minmax(280px,1.15fr);column-gap:45px;align-items:start}}.design-layout-split:not(.thank-you-card) .public-brand,.design-layout-split:not(.thank-you-card) header{{grid-column:1}}.design-layout-split:not(.thank-you-card) .public-fields{{grid-column:2;grid-row:1/span 4;margin-top:0}}.design-layout-split:not(.thank-you-card)>.public-submit,.design-layout-split:not(.thank-you-card)>.secure-note,.design-layout-split:not(.thank-you-card)>footer{{grid-column:2}}
@media(max-width:720px){{body{{padding:20px 10px}}.public-card{{padding:34px 25px}}header h1{{font-size:31px}}.design-layout-split:not(.thank-you-card){{display:block}}.design-layout-split:not(.thank-you-card) .public-fields{{margin-top:26px}}}}
"""
    classes = f'public-card design-layout-{_text(design.get("layout") or "card")} design-density-{_text(design.get("density") or "comfortable")} design-fields-{_text(design.get("field_style") or "outline")} design-button-{_text(design.get("button_style") or "solid")} design-heading-{_text(design.get("heading_align") or "left")}'
    if role == "thanks":
        thanks = form_state.get("thank_you") or {}
        title = _text(thanks.get("title") or "Merci !")
        message = _text(thanks.get("message"))
        button = ""
        if thanks.get("action") != "none" and thanks.get("button_url"):
            button = f'<a class="public-submit" data-luna-id="thanks.button" href="{_text(thanks["button_url"])}">{_text(thanks.get("button_label") or "Continuer")}</a>'
        body = f'<main class="{classes} thank-you-card" data-luna-id="card" data-sillage-region="card">{brand}<div class="thanks-check">✓</div><h1 data-luna-id="thanks.title">{title}</h1><p data-luna-id="thanks.message">{message}</p>{button}{footer}</main>'
    else:
        fields = "".join(_field_html(field) for field in form_state.get("fields") or [])
        if 'data-sillage="consent"' not in fields:
            fields += '<div data-sillage="consent"></div>'
        body = (f'<form class="{classes}" data-sillage="form" data-luna-id="card" data-sillage-region="card">{brand}<header><p class="eyebrow" data-luna-id="eyebrow">{_text(content["eyebrow"])}</p>'
                f'<h1 data-luna-id="title">{_text(form_state.get("name"))}</h1><p data-luna-id="description">{_text(form_state.get("description"))}</p></header>'
                f'<div class="public-fields">{fields}</div><button class="public-submit" type="submit" data-luna-id="submit">{_text(content["submit_label"])}</button>'
                f'<p class="secure-note" data-luna-id="trust">{_text(content["trust_note"])}</p>{footer}</form>')
    return f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head><body>{body}</body></html>'


def blank_form_html(title: str) -> str:
    """Build an editable empty form canvas without copying the current page."""
    body = (
        '<main data-sillage-region="page">'
        '<form data-sillage="form" data-luna-id="card">'
        f'<header data-sillage-region="intro"><h1 data-luna-id="title">{_text(title)}</h1>'
        '<p data-luna-id="description"></p></header>'
        '<div data-sillage-region="fields"><div data-sillage="consent"></div></div>'
        '<button type="submit" data-luna-id="submit">Envoyer ma réponse</button>'
        '</form></main>'
    )
    css = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;padding:40px 20px;font-family:system-ui,sans-serif;color:#17211b;background:#f4f4ee}
main{width:min(720px,100%);margin:8vh auto}form{display:grid;gap:24px}header{max-width:520px}h1{font-size:clamp(30px,5vw,48px);line-height:1.08;margin:0 0 12px}header p{color:#566159;line-height:1.6}
[data-sillage-region=fields]{display:grid;gap:18px}.public-field{display:grid;gap:7px;font-size:14px}.public-field input:not([type=radio]),.public-field textarea,.public-field select{width:100%;min-height:44px;padding:10px 12px;border:1px solid #ccd2ca;border-radius:7px;background:#fff;color:inherit;font:inherit}.public-field textarea{min-height:100px}
fieldset{padding:0;border:0}.choices{display:flex;flex-wrap:wrap;gap:10px}.choice{display:flex;align-items:center;gap:7px}
button{justify-self:start;min-height:46px;padding:0 24px;border:0;border-radius:7px;background:#17211b;color:#fff;font:inherit;font-weight:700;cursor:pointer}
@media(max-width:600px){body{padding:24px 16px}main{margin:4vh auto}button{width:100%}}
"""
    return f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>{css}</style></head><body>{body}</body></html>'


# --- Méta-discours -----------------------------------------------------------
#
# Une page produite par Luna s'adresse aux visiteurs. Il lui arrive pourtant d'y
# écrire ce qu'elle dirait à la personne qui l'a commandée : la demande
# reformulée (« un formulaire opt-in clair et rassurant pour capter des
# prospects »), ou un encart qui justifie ses choix et ses sources. Le visiteur
# le lit, et ça décrédibilise la page.
#
# La liste de marqueurs ci-dessous est volontairement étroite. Elle ne cherche
# pas à juger un style : elle attrape le vocabulaire du livrable, qu'on n'écrit
# pas à un visiteur, et les tournures par lesquelles Luna se raconte. Mieux vaut
# laisser passer une phrase douteuse que refuser une page légitime.

_META_JARGON = (
    "opt-in", "optin", "opt in",
    "landing page", "page de capture", "tunnel de conversion",
    "call-to-action", "call to action", "taux de conversion",
    "lead magnet", "copywriting", "wireframe",
)

_META_JUSTIFICATION = (
    "met l'accent sur",
    "le contenu s'appuie", "ce contenu s'appuie", "s'appuie sur les messages",
    "je me suis appuye", "je me suis inspire",
    "mis en avant publiquement", "selon le site officiel",
    "le brief", "votre brief",
    "cette page a ete concue", "ce formulaire a ete concu",
)


class _VisibleText(HTMLParser):
    """Texte que le visiteur lit réellement, sans le style ni l'en-tête."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._muted = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("style", "script", "title", "head"):
            self._muted += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "title", "head") and self._muted:
            self._muted -= 1

    def handle_data(self, data: str) -> None:
        if not self._muted and data.strip():
            self.chunks.append(data.strip())


def _flatten(value: str) -> str:
    """Minuscules sans accents ni apostrophe typographique, pour comparer."""
    value = value.replace("\u2019", "'").replace("\u02bc", "'")
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char)).lower()


def meta_discourse(html: str) -> list[str]:
    """Phrases où la page se décrit elle-même, au lieu de s'adresser au visiteur.

    Renvoie les extraits fautifs pour qu'on puisse les citer au modèle : une
    reprise corrige bien mieux quand elle sait quelle phrase retirer.
    """
    parser = _VisibleText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # un HTML cassé est traité ailleurs, pas ici
        return []

    marqueurs = _META_JARGON + _META_JUSTIFICATION
    fautifs: list[str] = []
    for chunk in parser.chunks:
        for phrase in re.split(r"(?<=[.!?;])\s+|\n+", chunk):
            phrase = phrase.strip()
            if not phrase:
                continue
            plat = _flatten(phrase)
            if any(marqueur in plat for marqueur in marqueurs) and phrase not in fautifs:
                fautifs.append(phrase[:160])
    return fautifs[:6]


# --- Markdown et parametres de suivi -----------------------------------------
#
# Luna ecrit parfois un lien en Markdown dans un document HTML : le visiteur lit
# alors « ([smartduck.fr](https://smartduck.fr/?utm_source=openai)) », crochets
# et URL compris. L'outil de recherche web ajoute de son cote un utm_source qui
# annonce aux prospects d'ou vient le texte.

_MARKDOWN_LINK = re.compile(r"\[[^\]\r\n]{1,120}\]\(\s*<?https?://[^)\s]+>?\s*\)")
_MARKDOWN_EMPHASIS = re.compile(r"\*\*[^*\r\n]{2,80}\*\*")
_BARE_URL = re.compile(r"(?<![\w@])https?://\S{4,}")
_TRACKING = re.compile(r"^(utm_|mc_|_hs|pk_|piwik_)|^(gclid|fbclid|msclkid|igshid|ref_src|yclid)$", re.IGNORECASE)


def markdown_leftovers(html: str) -> list[str]:
    """Passages ou la page montre du Markdown ou une URL brute au visiteur."""
    parser = _VisibleText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # un HTML casse est traite ailleurs
        return []

    fautifs: list[str] = []
    for chunk in parser.chunks:
        for motif in (_MARKDOWN_LINK, _MARKDOWN_EMPHASIS, _BARE_URL):
            for trouve in motif.findall(chunk):
                extrait = (trouve if isinstance(trouve, str) else trouve[0])[:160]
                if extrait not in fautifs:
                    fautifs.append(extrait)
    return fautifs[:6]


_IMAGE_SOURCE = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"', re.IGNORECASE)
_CSS_IMAGE = re.compile(r"""url\(\s*['"]?(https?://[^)'"]+)""", re.IGNORECASE)


def foreign_images(html: str, allowed: set[str]) -> list[str]:
    """Images de la page qui ne viennent pas des visuels fournis.

    Le modele n'a aucun moyen de savoir si une URL trouvee sur le web existe
    encore, ni si elle lui appartient. Une image inventee casse la page ou
    emprunte le bien d'autrui : on n'accepte que ce qu'on a nous-memes valide.
    """
    trouvees = _IMAGE_SOURCE.findall(html) + _CSS_IMAGE.findall(html)
    intruses = []
    for source in trouvees:
        source = source.strip()
        if source.startswith("data:") or source in allowed:
            continue
        if source not in intruses:
            intruses.append(source[:160])
    return intruses[:6]


def strip_tracking(url: str) -> str:
    """Retire les parametres de suivi d'une URL, en gardant le reste intact."""
    if "?" not in url:
        return url
    parts = urlsplit(url)
    gardes = [(cle, valeur) for cle, valeur in parse_qsl(parts.query, keep_blank_values=True)
              if not _TRACKING.match(cle)]
    return urlunsplit(parts._replace(query=urlencode(gardes)))


def _clean_links(html: str) -> str:
    """Nettoie les URL des attributs du document deja assaini.

    La valeur lue est deja echappee : sans le unescape, un &amp; d'origine
    ressortirait en &amp;amp; et couperait le parametre suivant.
    """
    def remplacer(trouve: re.Match) -> str:
        propre = strip_tracking(unescape(trouve.group(2)))
        return f'{trouve.group(1)}="{escape(propre, quote=True)}"'

    return re.sub(r'(href|src)="([^"]*)"', remplacer, html)
