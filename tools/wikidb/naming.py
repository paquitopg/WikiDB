"""Names shared between the wiki configuration and the tooling.

The user page name must match the OpenID Connect Authenticator settings in
xwiki/config/xwiki.properties.overrides: lowercased email, every character outside
[a-z0-9] replaced by "-".
"""

import re

_FORBIDDEN = re.compile(r"[^a-z0-9]")

GROUP_DIRECTION = "GroupeDirection"
GROUP_SYNTHESE = "GroupeSynthese"


def user_name(email: str) -> str:
    """XWiki user page name the authenticator creates for this ProConnect email."""
    return _FORBIDDEN.sub("-", email.strip().lower())


def user_reference(email: str) -> str:
    return f"XWiki.{user_name(email)}"


def bureau_group(code: str) -> str:
    return f"Groupe{code}"


def group_reference(group: str) -> str:
    return f"XWiki.{group}"
