"""Jinja2 template engine for parameterizable vector content.

Loads templates from the templates/ directory and renders them with
vector-specific context. Used by both direct vector generation and
POC bundle creation.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(enabled_extensions=("html", "xml"), default=False),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render(template_name: str, **kwargs: object) -> str:
    """Render a template by name with the given context variables."""
    tmpl = _env.get_template(template_name)
    return tmpl.render(**kwargs)


def list_templates() -> list[str]:
    """Return available template names."""
    return sorted(_env.list_templates())
