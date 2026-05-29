"""Rendu de graphes Graphviz zoomables/déplaçables dans l'UI Streamlit.

Le DOT (issu des fonctions ``distribution/*`` via ``.to_dot()``) est rendu en SVG
**dans le navigateur** par viz-standalone (@viz-js/viz, wasm inclus), puis rendu
zoomable/déplaçable par svg-pan-zoom. Libs vendorisées dans ``static/vendor`` :
- ``viz-standalone.js`` : lourde, servie via le static file serving de Streamlit
  (mise en cache par le navigateur, partagée entre composants) ;
- ``svg-pan-zoom.min.js`` : légère, inlinée dans le HTML du composant.

Aucune dépendance réseau au runtime, aucun binaire ``dot`` requis.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

_VENDOR_DIR = Path(__file__).parent / "static" / "vendor"
# URL servie par Streamlit (enableStaticServing) ; même origine que l'iframe srcdoc.
_VIZ_STATIC_URL = "app/static/vendor/viz-standalone.js"


@functools.cache
def _read_vendor(name: str) -> str:
    """Contenu d'un fichier vendorisé de ``static/vendor`` (mis en cache)."""
    return (_VENDOR_DIR / name).read_text(encoding="utf-8")


def build_graph_html(dot: str, height: int = 540) -> str:
    """HTML autonome rendant ``dot`` en SVG zoomable/déplaçable.

    Fonction pure (n'importe pas ``streamlit``) -> testable sans serveur.
    """
    svg_pan_zoom = _read_vendor("svg-pan-zoom.min.js")
    dot_js = json.dumps(dot)  # échappe guillemets / sauts de ligne
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  html,body {{ margin:0; padding:0; }}
  #wrap {{ width:100%; height:{height}px; border:1px solid #ddd;
           border-radius:6px; overflow:hidden; background:#fff; }}
  #graph, #graph svg {{ width:100%; height:100%; }}
  #err {{ color:#b00; font:13px sans-serif; padding:8px; }}
</style></head>
<body>
  <div id="wrap"><div id="graph"></div></div>
  <div id="err"></div>
  <script src="{_VIZ_STATIC_URL}"></script>
  <script>{svg_pan_zoom}</script>
  <script>
    var DOT = {dot_js};
    function fail(m) {{ document.getElementById('err').textContent =
      'Graphe non rendu : ' + m + ' (static serving activé ?)'; }}
    if (typeof Viz === 'undefined') {{
      fail('viz-standalone.js introuvable');
    }} else {{
      Viz.instance().then(function(viz) {{
        var svg = viz.renderSVGElement(DOT);
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', '100%');
        document.getElementById('graph').appendChild(svg);
        var pz = svgPanZoom(svg, {{ controlIconsEnabled:true, fit:true,
                                    center:true, minZoom:0.1, maxZoom:20 }});
        // Dans un st.expander replié, l'iframe se monte en taille 0x0 : le fit
        // ci-dessus tombe sur du vide (SVG invisible). On re-fit dès que le
        // conteneur prend une taille réelle, et à chaque redimensionnement.
        var wrap = document.getElementById('wrap');
        new ResizeObserver(function() {{
          if (wrap.clientWidth > 0 && wrap.clientHeight > 0) {{
            pz.resize(); pz.fit(); pz.center();
          }}
        }}).observe(wrap);
      }}).catch(function(e) {{ fail(String(e)); }});
    }}
  </script>
</body></html>"""


def render_dot(dot: str, *, height: int = 540) -> None:
    """Affiche ``dot`` comme graphe zoomable/déplaçable dans Streamlit."""
    import streamlit.components.v1 as components

    # +12 px pour la bordure/marge interne du conteneur.
    components.html(build_graph_html(dot, height), height=height + 12, scrolling=False)
