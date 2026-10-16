"""ProConnect sign-in request built by the patched OpenID Connect Authenticator (KTD9; R15).

ProConnect's /authorize requires state and nonce, each at least 32 characters
(partenaires.proconnect.gouv.fr/docs/fournisseur-service/implementation_technique).
"""

from urllib.parse import parse_qs, urlsplit

import requests


def authorize_request(base_url: str) -> dict[str, str]:
    r = requests.get(f"{base_url.rstrip('/')}/bin/view/Main/", allow_redirects=False)
    assert r.status_code in (301, 302, 303), r.status_code
    location = r.headers["Location"]
    assert urlsplit(location).path.endswith("/authorize"), location.split("?")[0]
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


def test_guest_is_sent_to_proconnect_with_a_code_flow_request(base_url):
    query = authorize_request(base_url)
    assert query["response_type"] == "code"
    assert query["redirect_uri"].endswith("/oidc/authenticator/callback")
    assert set(query["scope"].split()) >= {"openid", "email", "given_name", "usual_name"}


def test_authorize_request_carries_a_fresh_nonce_and_state_of_32_characters(base_url):
    first, second = authorize_request(base_url), authorize_request(base_url)
    for key in ("nonce", "state"):
        assert len(first[key]) >= 32, key
        assert first[key] != second[key], key
