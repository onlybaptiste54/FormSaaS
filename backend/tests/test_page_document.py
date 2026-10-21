import pytest

from app.page_document import MAX_PAGE_HTML, legacy_to_html, foreign_images, markdown_leftovers, meta_discourse, prepare_page, render_page, strip_tracking


def _form(inner: str) -> str:
    return f'<form data-sillage="form">{inner}<div data-sillage="consent"></div></form>'


def test_prepare_page_removes_active_content_and_external_urls():
    source = (
        '<style>@import url(https://evil.test/a.css);'
        'h1{color:red;background:url(https://evil.test/x.png)}'
        '@media(max-width:600px){h1{font-size:2rem}}</style>'
        '<script>alert(1)</script><iframe src="https://evil.test"></iframe>'
        + _form('<h1 onclick="alert(1)">Titre</h1>'
                '<a href="javascript:alert(1)">Lien</a>'
                '<img src="data:image/svg+xml;base64,PHN2Zz4=" onerror="alert(1)">'
                '<input name="email" type="email" required style="color:blue;background:url(https://evil.test)">')
    )
    cleaned, manifest = prepare_page(source, require_form=True)
    for dangerous in ("<script", "<iframe", "onclick", "onerror", "javascript:",
                      "@import", "evil.test", "svg+xml", "alert(1)"):
        assert dangerous not in cleaned
    assert "color:red" in cleaned and "font-size:2rem" in cleaned
    assert manifest == [{"id": "email", "name": "email", "type": "email", "label": "email", "required": True}]


def test_manifest_reads_labels_select_options_and_radio_group():
    source = _form(
        '<label for="contact">Courriel</label><input id="contact" name="email" type="email" required>'
        '<label>Choix<select name="choice"><option value="">—</option>'
        '<option value="a">A</option><option value="b">B</option></select></label>'
        '<fieldset><legend>Satisfaction</legend>'
        '<label><input type="radio" name="rating" value="1" data-rating="1" required>1</label>'
        '<label><input type="radio" name="rating" value="2" data-rating="1">2</label></fieldset>'
    )
    _, manifest = prepare_page(source, require_form=True)
    assert manifest == [
        {"id": "email", "name": "email", "type": "email", "label": "Courriel", "required": True},
        {"id": "choice", "name": "choice", "type": "select", "label": "Choix", "required": False, "options": ["a", "b"]},
        {"id": "rating", "name": "rating", "type": "rating", "label": "Satisfaction", "required": True, "options": ["1", "2"], "scale": 2},
    ]


def test_manifest_uses_option_text_when_value_is_omitted():
    source = _form(
        '<label>Pays<select name="country">'
        '<option value="">Choisissez</option><option>France</option><option value="be">Belgique</option>'
        '</select></label>'
    )
    _, manifest = prepare_page(source, require_form=True)
    assert manifest[0]["options"] == ["France", "be"]


def test_consent_content_is_server_owned():
    source = '<form data-sillage="form"><div data-sillage="consent"><div><input checked name="sillage_consent">Faux texte</div></div><input name="email"></form>'
    cleaned, _ = prepare_page(source, require_form=True)
    assert "Faux texte" not in cleaned
    assert "checked" not in cleaned
    rendered = render_page(cleaned, '<Confidentiel & légal>')
    assert '&lt;Confidentiel &amp; légal&gt;' in rendered
    assert 'name="sillage_consent"' in rendered
    assert " required" in rendered
    assert render_page(cleaned, r"Texte \g<1>").count(r"\g&lt;1&gt;") == 1


@pytest.mark.parametrize("html", [
    '<div data-sillage="consent"></div>' + _form('<input name="email">'),
    _form('<input name="email"><div data-sillage="consent"></div>'),
    '<div data-sillage="consent"></div><main>Sans formulaire</main>',
])
def test_consent_placeholder_must_be_unique_and_inside_the_form(html):
    with pytest.raises(ValueError, match="consent"):
        prepare_page(html, require_form='data-sillage="form"' in html)


def test_thanks_personalization_only_rewrites_text_nodes():
    stored, _ = prepare_page(
        '<style>body{--visitor:"{prenom}"}</style>'
        '<h1>Merci {prenom} !</h1>'
        '<a href="https://example.test/{prenom}">Continuer</a>',
        require_form=False,
    )
    assert "Merci {prenom} !" in stored

    rendered = render_page(stored, "", {"name": "<Noémie> Martin"})
    assert "Merci &lt;Noémie&gt; !" in rendered
    assert "<Noémie>" not in rendered
    assert '--visitor:"{prenom}"' in rendered
    assert 'href="https://example.test/{prenom}"' in rendered

    anonymous = render_page(stored, "", {})
    assert "Merci !" in anonymous and "Merci  !" not in anonymous


def test_css_escapes_nested_urls_and_aggressive_rules():
    source = ('<style>*{display:none}body{background:u\\72l(https://evil.test/x)}'
              '@media(max-width:600px){div{background:image-set("https://evil.test/x" 1x);color:red}}'
              '</style>' + _form('<input name="email">'))
    cleaned, _ = prepare_page(source, require_form=True)
    assert "*{display:none}" in cleaned  # the iframe contains the effect
    assert "evil.test" not in cleaned
    assert "color:red" in cleaned


def test_malformed_html_cannot_keep_script_or_fake_consent():
    source = ('<form data-sillage="form"><input name="email"><div data-sillage="consent">'
              '<div>Faux<input checked></div></div><script src="https://evil.test/x"></script></form>')
    cleaned, _ = prepare_page(source, require_form=True)
    assert "Faux" not in cleaned and "checked" not in cleaned
    assert "script" not in cleaned and "evil.test" not in cleaned


def test_render_adds_csp_to_form_and_thanks_documents():
    form_html, _ = prepare_page(_form('<input name="email">'), require_form=True)
    thanks_html, _ = prepare_page('<main>Merci</main>', require_form=False)
    assert "Content-Security-Policy" not in form_html
    for rendered in (render_page(form_html, "Consentement"), render_page(thanks_html, "")):
        assert '<head><meta http-equiv="Content-Security-Policy"' in rendered
        assert "script-src 'none'" in rendered
        assert "style-src 'unsafe-inline'" in rendered
        # 'self' couvre le relais des visuels du client, a la meme origine.
        assert "img-src 'self' https: data:" in rendered
        assert "object-src 'none'" in rendered
        assert "base-uri 'none'" in rendered
        assert "form-action 'none'" in rendered


@pytest.mark.parametrize("html", [
    '<form data-sillage="form"><input name="email"></form>',
    '<form data-sillage="form"><div data-sillage="consent"></div><input name="Bad-Name"></form>',
    '<form data-sillage="form"><div data-sillage="consent"></div><input name="email"><input name="email"></form>',
])
def test_invalid_collection_documents_are_rejected(html):
    with pytest.raises(ValueError):
        prepare_page(html, require_form=True)


def test_html_limit_is_enforced():
    with pytest.raises(ValueError, match="limite"):
        prepare_page("x" * (MAX_PAGE_HTML + 1), require_form=False)


def test_legacy_conversion_preserves_fields_and_older_style_tokens():
    state = {
        "name": "Satisfaction", "description": "Votre avis compte", "design": {"background": "ink", "radius": "pill"},
        "fields": [
            {"id": "email", "label": "Courriel", "type": "email", "required": True},
            {"id": "rating", "label": "Note", "type": "rating", "required": True, "scale": 5},
            {"id": "choice", "label": "Choix", "type": "radio", "options": ["Oui", "Non"]},
            {"id": "consent", "label": "Ancien texte", "type": "consent"},
        ],
    }
    raw = legacy_to_html(state, {"name": "Atelier"})
    assert "#17231d" in raw and "border-radius:28.0px" in raw
    assert 'data-luna-id="title"' in raw and 'data-luna-id="field:rating.label"' in raw
    cleaned, manifest = prepare_page(raw, require_form=True)
    assert len(cleaned) > 1000
    assert [field["name"] for field in manifest] == ["email", "rating", "choice"]
    assert manifest[1]["type"] == "rating" and manifest[1]["scale"] == 5
    assert manifest[2]["options"] == ["Oui", "Non"]
    thanks, thanks_manifest = prepare_page(legacy_to_html({**state, "thank_you": {"title": "Merci"}}, {"name": "Atelier"}, role="thanks"), require_form=False)
    assert "Merci" in thanks and thanks_manifest == []

    personalized, _ = prepare_page(
        legacy_to_html({**state, "thank_you": {"title": "Merci {prenom} !"}}, {"name": "Atelier"}, role="thanks"),
        require_form=False,
    )
    assert "Merci {prenom} !" in personalized


def test_meta_discourse_reports_page_talking_about_itself():
    """Les deux formes observées en production : brief reformulé, choix justifiés."""
    page = (
        '<!doctype html><html lang="fr"><body>'
        '<p>Un formulaire opt-in clair, élégant et rassurant pour capter des prospects.</p>'
        '<aside>Le message met l’accent sur la transparence tarifaire, '
        'des éléments mis en avant publiquement par Smartduck.</aside>'
        + _form('<input name="email" type="email">')
        + '</body></html>'
    )
    fautifs = meta_discourse(page)
    assert len(fautifs) == 2
    assert any("opt-in" in phrase for phrase in fautifs)
    assert any("met l’accent" in phrase for phrase in fautifs)


def test_meta_discourse_accepts_a_page_written_for_visitors():
    """Aucun faux positif sur une vraie page, lien source et mentions compris."""
    page = (
        '<!doctype html><html lang="fr"><head>'
        '<title>Formulaire opt-in interne</title>'
        '<style>.cta{color:red}/* landing page */</style>'
        '</head><body>'
        '<h1>Retrouvez une peau nette durablement</h1>'
        '<p>Décrivez votre demande, nous revenons vers vous sous 24 heures.</p>'
        '<p>Nos tarifs sont publics : <a href="https://exemple.fr/tarifs">voir les tarifs</a>.</p>'
        + _form('<input name="email" type="email">')
        + '</body></html>'
    )
    assert meta_discourse(page) == []


def test_meta_discourse_ignores_style_and_handles_typographic_apostrophe():
    assert meta_discourse('<style>/* taux de conversion */</style><p>Bonjour</p>') == []
    droite = meta_discourse("<p>Le contenu s'appuie sur leur site.</p>")
    courbe = meta_discourse("<p>Le contenu s’appuie sur leur site.</p>")
    assert len(droite) == 1 and len(courbe) == 1


def test_markdown_leftovers_catches_what_the_visitor_should_never_read():
    """Le cas observe : un lien Markdown rendu en clair, utm compris."""
    page = ('<p>On vous aide. ([smartduck.fr](https://smartduck.fr/offre/?utm_source=openai))</p>'
            '<p>Voir https://smartduck.fr/nos-centres/</p><p>Un mot **important**.</p>')
    fautifs = markdown_leftovers(page)
    assert any(f.startswith("[smartduck.fr](") for f in fautifs)
    assert any(f == "**important**" for f in fautifs)
    assert any("nos-centres" in f for f in fautifs)


def test_markdown_leftovers_accepts_a_real_link():
    assert markdown_leftovers('<p>Voir le <a href="https://smartduck.fr/">site de smartduck</a>.</p>') == []
    assert markdown_leftovers('<style>a{color:red}</style><p>Bonjour</p>') == []


def test_strip_tracking_keeps_the_useful_parameters():
    assert strip_tracking("https://x.fr/a?utm_source=openai&id=7&fbclid=zz") == "https://x.fr/a?id=7"
    assert strip_tracking("https://x.fr/b") == "https://x.fr/b"
    assert strip_tracking("https://x.fr/c?page=2") == "https://x.fr/c?page=2"


def test_prepare_page_removes_tracking_from_stored_links():
    """Un utm_source=openai annoncerait aux prospects d'ou vient le texte."""
    source = _form('<a href="https://smartduck.fr/offre/?utm_source=openai&amp;id=3">Nos offres</a>'
                   '<input name="email" type="email">')
    document, _ = prepare_page(source, require_form=True)
    assert "utm_source" not in document
    assert "id=3" in document


def test_foreign_images_only_accepts_what_was_provided():
    autorisees = {"https://smartduck.fr/media/equipe.jpg"}
    page = ('<img src="https://smartduck.fr/media/equipe.jpg" alt="ok">'
            '<img src="https://ailleurs.test/vole.jpg" alt="non">'
            '<img src="data:image/gif;base64,R0lGOD" alt="ok">'
            '<style>.h{background:url(https://ailleurs.test/fond.jpg)}</style>')
    assert foreign_images(page, autorisees) == ["https://ailleurs.test/vole.jpg",
                                                "https://ailleurs.test/fond.jpg"]
    assert foreign_images('<img src="https://smartduck.fr/media/equipe.jpg">', autorisees) == []


def test_only_the_proxy_path_passes_as_a_relative_image():
    """Le relais est accepte, les autres chemins relatifs non."""
    def image(src: str) -> str:
        document, _ = prepare_page(_form(f'<img src="{src}" alt="x"><input name="email" type="email">'),
                                   require_form=True)
        return document

    assert '/media/brand?u=https%3A%2F%2Fx.fr%2Fa.png&amp;s=abc' in image("/media/brand?u=https%3A%2F%2Fx.fr%2Fa.png&amp;s=abc")
    assert "evil.test" not in image("//evil.test/x.png")
    assert "passwd" not in image("/etc/passwd")


def test_foreign_images_ignores_html_escaping_of_the_url():
    """Regression : &amp; dans le document contre & dans la liste des visuels.

    Sans cela, chaque image deja presente etait declaree intruse a la retouche
    suivante, et Luna supprimait les photos du client pour obeir.
    """
    autorisee = "/media/brand?u=https%3A%2F%2Fsmartduck.fr%2Fa.png&s=29b4b1e7"
    page = f'<img src="/media/brand?u=https%3A%2F%2Fsmartduck.fr%2Fa.png&amp;s=29b4b1e7" alt="x">'
    assert foreign_images(page, {autorisee}) == []
    # Une signature differente reste refusee.
    autre = '<img src="/media/brand?u=https%3A%2F%2Fsmartduck.fr%2Fa.png&amp;s=0000" alt="x">'
    assert len(foreign_images(autre, {autorisee})) == 1
