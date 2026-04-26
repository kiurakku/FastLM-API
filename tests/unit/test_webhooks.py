import hashlib
import hmac

from app.services.webhooks import sign_webhook_body


def test_webhook_signature_matches_hmac() -> None:
    secret = "whsec-test"
    body = b'{"event":"request.completed","payload":{"x":1}}'
    sig = sign_webhook_body(secret, body)
    assert sig.startswith("sha256=")
    hexpart = sig[7:]
    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    assert hexpart == expected
