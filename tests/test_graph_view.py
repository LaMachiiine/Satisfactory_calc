import json

from satisfactory_planner.ui.graph_view import _read_vendor, build_graph_html

DOT = "digraph {\n a -> b;\n}"


def test_build_graph_html_embeds_dot_json_encoded():
    # Le DOT est injecté en JSON (guillemets et sauts de ligne échappés).
    html = build_graph_html(DOT, height=400)
    assert json.dumps(DOT) in html


def test_build_graph_html_references_viz_static_and_inits_panzoom():
    html = build_graph_html(DOT)
    assert "app/static/vendor/viz-standalone.js" in html  # lib lourde servie en statique
    assert "Viz.instance()" in html                       # rendu DOT -> SVG
    assert "svgPanZoom(" in html                          # zoom/pan initialisé


def test_build_graph_html_respects_height():
    assert "height:400px" in build_graph_html(DOT, height=400)


def test_build_graph_html_inlines_svg_pan_zoom():
    # La lib légère est inlinée (pas servie séparément).
    html = build_graph_html(DOT)
    assert _read_vendor("svg-pan-zoom.min.js")[:60] in html


def test_build_graph_html_refits_when_container_becomes_visible():
    # Régression : dans un st.expander replié, l'iframe se monte en taille 0x0 et
    # svg-pan-zoom « fit » sur du vide (SVG invisible). Le HTML doit re-fit via un
    # ResizeObserver quand le conteneur prend une taille réelle.
    html = build_graph_html(DOT)
    assert "ResizeObserver" in html
    assert ".fit()" in html
    assert ".resize()" in html


def test_vendored_files_present_and_nontrivial():
    assert len(_read_vendor("svg-pan-zoom.min.js")) > 10_000
    assert len(_read_vendor("viz-standalone.js")) > 1_000_000


def test_render_dot_passes_html_and_height_to_components(monkeypatch):
    import streamlit.components.v1 as components

    captured = {}

    def fake_html(html, **kwargs):
        captured["html"] = html
        captured["kwargs"] = kwargs

    monkeypatch.setattr(components, "html", fake_html)

    from satisfactory_planner.ui.graph_view import render_dot

    render_dot("digraph { a -> b; }", height=300)
    assert "svgPanZoom(" in captured["html"]
    assert "a -> b" in captured["html"]
    assert captured["kwargs"]["height"] == 312  # height + 12 px (bordure)
