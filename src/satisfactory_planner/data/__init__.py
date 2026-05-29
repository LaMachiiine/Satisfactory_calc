"""Couche données : parsing du Docs.json et constantes de jeu."""

from . import game_constants
from .docs_parser import ParsedDocs, parse_docs

__all__ = ["ParsedDocs", "parse_docs", "game_constants"]
