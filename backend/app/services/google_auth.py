"""Google sign-in: verify the ID token Google Identity Services hands the browser.

The frontend sends us ``credential`` (a signed JWT). We check the signature against Google's published
certificates, that it was issued for OUR client id (audience), that it is not expired, and that Google says
the email is verified. Verification is blocking network I/O, so it runs in a worker thread.
Tests replace ``verify_credential`` with a stand-in, so they never contact Google.
"""

import asyncio
from typing import Any

from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import get_settings
from app.core.errors import AppError, unauthorized


def is_configured() -> bool:
    return bool(get_settings().google_client_id)


async def verify_credential(credential: str) -> dict[str, Any]:
    client_id = get_settings().google_client_id
    if not client_id:
        raise AppError(503, "google_not_configured", "Google sign-in is not set up on this server")

    def _verify() -> dict[str, Any]:
        # Checks signature, expiry, issuer (accounts.google.com) and that the audience is our client id.
        return id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)

    try:
        claims = await asyncio.to_thread(_verify)
    except google_exceptions.TransportError:
        raise AppError(503, "google_unreachable", "Could not reach Google to verify the sign-in") from None
    except ValueError:  # bad signature, wrong audience, expired, malformed
        raise unauthorized("Google sign-in failed. Please try again.") from None
    if not claims.get("email_verified") or not claims.get("email") or not claims.get("sub"):
        raise unauthorized("Your Google account's email address is not verified.")
    return claims
