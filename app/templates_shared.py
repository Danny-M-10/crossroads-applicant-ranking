"""Shared Jinja2 environment with Crossroads branding globals."""

from fastapi.templating import Jinja2Templates

from app.branding import template_globals

templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update(template_globals())
