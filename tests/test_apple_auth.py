import time
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from server_v2.apple_auth import AppleAuthError, verify_apple_identity_token

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUB = _KEY.public_key()
AUD = "com.example.aicaddie"
ISS = "https://appleid.apple.com"


def _token(**overrides):
    claims = {"iss": ISS, "aud": AUD, "sub": "000123.abc.456",
              "email": "x@privaterelay.appleid.com",
              "iat": int(time.time()), "exp": int(time.time()) + 600}
    claims.update(overrides)
    return jwt.encode(claims, _KEY, algorithm="RS256")


class AppleAuthTests(unittest.TestCase):
    def _resolver(self, _token):
        return _PUB

    def test_valid_token_returns_identity(self):
        ident = verify_apple_identity_token(_token(), audience=AUD, signing_key_resolver=self._resolver)
        self.assertEqual(ident.subject, "000123.abc.456")
        self.assertEqual(ident.email, "x@privaterelay.appleid.com")

    def test_wrong_audience_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(aud="com.attacker.app"), audience=AUD, signing_key_resolver=self._resolver)

    def test_audience_list_accepts_any_member(self):
        # A web Sign-in-with-Apple token's aud is the Services ID; passing a list lets it verify
        # alongside the iOS bundle id (multi-audience support for one app + one web client).
        for aud in ("com.example.aicaddie", "com.example.web"):
            ident = verify_apple_identity_token(
                _token(aud=aud), audience=["com.example.aicaddie", "com.example.web"],
                signing_key_resolver=self._resolver)
            self.assertEqual(ident.subject, "000123.abc.456")

    def test_audience_list_rejects_outsider(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(
                _token(aud="com.attacker.app"), audience=["com.example.aicaddie", "com.example.web"],
                signing_key_resolver=self._resolver)

    def test_wrong_issuer_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(iss="https://evil.example"), audience=AUD, signing_key_resolver=self._resolver)

    def test_expired_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(exp=int(time.time()) - 5), audience=AUD, signing_key_resolver=self._resolver)

    def test_missing_sub_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(sub=""), audience=AUD, signing_key_resolver=self._resolver)

    def test_wrong_signing_key_rejected(self):
        attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        bad = jwt.encode({"iss": ISS, "aud": AUD, "sub": "x", "exp": int(time.time()) + 600},
                         attacker_key, algorithm="RS256")
        with self.assertRaises(AppleAuthError):  # resolver returns the legit key → signature mismatch
            verify_apple_identity_token(bad, audience=AUD, signing_key_resolver=self._resolver)

    def test_empty_audience_rejected(self):
        with self.assertRaises(AppleAuthError):
            verify_apple_identity_token(_token(), audience="", signing_key_resolver=self._resolver)
