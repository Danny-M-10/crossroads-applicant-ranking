"""Crossroads Professional Coaching — single source of truth for product copy and palette."""

# ── Organization & product ───────────────────────────────────
ORG_NAME = "Crossroads Professional Coaching"
ORG_SHORT_NAME = "Crossroads"
PRODUCT_NAME = "Applicant Ranking"
PRODUCT_NAME_FULL = "Applicant Ranking Tool"
TAGLINE = "Face crossroads. Make decisions. Move forward."
WEBSITE_URL = "https://crossroadcoach.com/"
WEBSITE_LABEL = "crossroadcoach.com"

# FastAPI / browser chrome
FASTAPI_TITLE = f"{ORG_SHORT_NAME} — {PRODUCT_NAME}"

# ── Web UI (Tailwind-compatible hex) ─────────────────────────
COLOR_NAV_BG = "#1a365d"
COLOR_NAV_TEXT = "#ffffff"
COLOR_NAV_LINK_HOVER = "#e2c76d"
COLOR_HEADER_MUTED = "#c8d6ea"
COLOR_ACCENT = "#2c5282"
COLOR_ACCENT_LIGHT = "#ebf4ff"
COLOR_BODY_BG = "#f8fafc"
COLOR_FLASH_BG = "#eff6ff"
COLOR_FLASH_BORDER = "#2c5282"
COLOR_FLASH_TEXT = "#1e3a8a"
COLOR_FOOTER_TEXT = "#64748b"
COLOR_NAV_BG_HOVER = "#142d4a"
COLOR_TEXT_ON_SOFT = "#1e3a8a"

# ── Report HTML/PDF (WeasyPrint template) ───────────────────
REPORT_COLOR_HEADER = COLOR_NAV_BG
REPORT_COLOR_HEADER_MUTED = COLOR_HEADER_MUTED
REPORT_COLOR_ACCENT = COLOR_ACCENT
REPORT_MATRIX_HEADER_BORDER = "#3d5a80"
REPORT_COLOR_PROFILE_TEXT = COLOR_NAV_BG
REPORT_TAG_BG = COLOR_NAV_BG
REPORT_TAG_TEXT = "#dbeafe"
REPORT_BADGE_TOP = "#1a4d6d"
COLOR_MATCH_STRONG = "#1e3a8a"

# ── DOCX (wordprocessingml hex without #) ───────────────────
DOCX_HEX_HEADER = "1A365D"
DOCX_HEX_ACCENT = "2C5282"
DOCX_HEX_HEADER_TEXT = "C8D6EA"
DOCX_HEX_MATRIX_BORDER = "3D5A80"

# RGB tuples for python-docx RGBColor(...)
COLOR_HEADER_RGB = (0x1A, 0x36, 0x5D)
COLOR_ACCENT_RGB = (0x2C, 0x52, 0x82)
COLOR_HEADER_MUTED_RGB = (0xC8, 0xD6, 0xEA)
COLOR_BODY_TEXT_RGB = (0x1A, 0x1A, 0x1A)

# ── AI / prompts ─────────────────────────────────────────────
ORG_CONTEXT_FOR_AI = (
    "Crossroads Professional Coaching, a Christian business coaching and consulting firm "
    "based in the Baton Rouge, Louisiana area. The firm helps small business owners with "
    "coaching, strategy, marketing, HR/recruiting, and related services. Candidates may "
    "be evaluated for Crossroads or for roles with its clients."
)


def template_globals() -> dict:
    """Inject into all Jinja2 templates via env.globals."""
    return {
        "org_name": ORG_NAME,
        "org_short_name": ORG_SHORT_NAME,
        "product_name": PRODUCT_NAME,
        "product_name_full": PRODUCT_NAME_FULL,
        "tagline": TAGLINE,
        "website_url": WEBSITE_URL,
        "website_label": WEBSITE_LABEL,
        "footer_ai_line": f"{ORG_NAME} — {PRODUCT_NAME_FULL} — Powered by Gemini AI",
        "color_nav_bg": COLOR_NAV_BG,
        "color_nav_text": COLOR_NAV_TEXT,
        "color_nav_link_hover": COLOR_NAV_LINK_HOVER,
        "color_header_muted": COLOR_HEADER_MUTED,
        "color_accent": COLOR_ACCENT,
        "color_body_bg": COLOR_BODY_BG,
        "color_flash_bg": COLOR_FLASH_BG,
        "color_flash_border": COLOR_FLASH_BORDER,
        "color_flash_text": COLOR_FLASH_TEXT,
        "color_footer_text": COLOR_FOOTER_TEXT,
        "color_nav_bg_hover": COLOR_NAV_BG_HOVER,
        "color_text_on_soft": COLOR_TEXT_ON_SOFT,
    }


def report_render_context() -> dict:
    """Merged into report HTML template context (plus session data)."""
    return {
        "org_name": ORG_NAME,
        "product_name_full": PRODUCT_NAME_FULL,
        "report_color_header": REPORT_COLOR_HEADER,
        "report_color_header_muted": REPORT_COLOR_HEADER_MUTED,
        "report_color_accent": REPORT_COLOR_ACCENT,
        "report_matrix_header_border": REPORT_MATRIX_HEADER_BORDER,
        "report_color_profile_text": REPORT_COLOR_PROFILE_TEXT,
        "report_tag_bg": REPORT_TAG_BG,
        "report_tag_text": REPORT_TAG_TEXT,
        "report_badge_top": REPORT_BADGE_TOP,
        "report_footer_line": f"{ORG_NAME} — {PRODUCT_NAME_FULL} — Powered by Gemini AI",
        "report_topbar_line": f"{ORG_SHORT_NAME} · {PRODUCT_NAME_FULL}",
    }


def docx_topbar_title() -> str:
    return f"{ORG_NAME.upper()}  ·  {PRODUCT_NAME_FULL.upper()}"
