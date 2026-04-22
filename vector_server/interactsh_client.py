"""Async client for polling Interactsh /events endpoint.

Interactsh encrypts callbacks with AES-CFB using a per-session key derived
from the client's RSA public key.  Flow:
  1. Client generates RSA-2048 keypair.
  2. POST /register with base64(public_key) + correlation_id + secret_key.
  3. GET  /poll?id=<correlation_id>&secret=<secret_key> returns AES-encrypted
     interaction records.  AES key = RSA-decrypt(encrypted_aes_key).
  4. POST /deregister to clean up.

We simplify: one long-lived session for the lifetime of the process.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import secrets
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

logger = logging.getLogger(__name__)

# Interactsh v1.3.1 uses OAEP + SHA256 for RSA, AES-256-CTR for payload encryption.
_RSA_KEY_SIZE = 2048
_AES_KEY_BYTES = 32


def _generate_keypair() -> tuple[rsa.RSAPrivateKey, str]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=_RSA_KEY_SIZE)
    pub_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private, base64.b64encode(pub_pem).decode()


def _rsa_decrypt(private_key: rsa.RSAPrivateKey, ciphertext_b64: str) -> bytes:
    ct = base64.b64decode(ciphertext_b64)
    return private_key.decrypt(ct, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))


def _aes_decrypt(key: bytes, data_b64: str) -> bytes:
    raw = base64.b64decode(data_b64)
    iv, ct = raw[:16], raw[16:]
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    dec = cipher.decryptor()
    return dec.update(ct) + dec.finalize()


class InteractshClient:
    def __init__(self, server_url: str, token: str):
        self._server = server_url.rstrip("/")
        self._token = token
        self._private_key, self._pub_b64 = _generate_keypair()
        self._correlation_id = secrets.token_hex(10)  # 20 chars — matches interactsh default
        self._nonce = secrets.token_hex(7)  # 14 chars — subdomain needs >= 33 (20 + 13 nonce)
        self._secret_key = secrets.token_hex(16)
        self._aes_key: bytes | None = None
        self._registered = False
        self._http = httpx.AsyncClient(timeout=30)

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    @property
    def nonce(self) -> str:
        return self._nonce

    async def register(self) -> None:
        payload = {
            "public-key": self._pub_b64,
            "secret-key": self._secret_key,
            "correlation-id": self._correlation_id,
        }
        headers = {"Authorization": self._token}
        resp = await self._http.post(f"{self._server}/register", json=payload, headers=headers)
        resp.raise_for_status()
        self._registered = True
        logger.info("Registered with Interactsh as %s", self._correlation_id)

    async def poll(self) -> list[dict[str, Any]]:
        if not self._registered:
            await self.register()

        headers = {"Authorization": self._token}
        resp = await self._http.get(
            f"{self._server}/poll",
            params={"id": self._correlation_id, "secret": self._secret_key},
            headers=headers,
        )
        resp.raise_for_status()
        body = resp.json()

        aes_key_enc = body.get("aes_key", "")
        if aes_key_enc and self._aes_key is None:
            self._aes_key = _rsa_decrypt(self._private_key, aes_key_enc)

        results: list[dict[str, Any]] = []
        for entry in body.get("data", []) or []:
            if self._aes_key is None:
                logger.warning("No AES key yet; skipping encrypted entry")
                continue
            try:
                plain = _aes_decrypt(self._aes_key, entry)
                results.append(json.loads(plain))
            except Exception:
                logger.exception("Failed to decrypt Interactsh entry")
        return results

    async def deregister(self) -> None:
        if not self._registered:
            return
        headers = {"Authorization": self._token}
        payload = {"correlation-id": self._correlation_id, "secret-key": self._secret_key}
        try:
            resp = await self._http.post(f"{self._server}/deregister", json=payload, headers=headers)
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to deregister from Interactsh")
        self._registered = False

    async def close(self) -> None:
        await self.deregister()
        await self._http.aclose()
