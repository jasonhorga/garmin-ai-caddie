import unittest


class JwtDepImportableTests(unittest.TestCase):
    def test_pyjwt_with_crypto_imports(self):
        import jwt  # noqa: F401
        from jwt import PyJWKClient  # noqa: F401
        from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: F401 (the [crypto] extra)
