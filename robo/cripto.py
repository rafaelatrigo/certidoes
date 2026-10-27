"""Criptografia compatível com o navegador (WebCrypto): PBKDF2-SHA256 + AES-256-GCM.

Tudo que vai para a pasta docs/ (publicada no GitHub Pages) sai daqui criptografado
com a senha do painel. Sem a senha, os arquivos no repositório são ilegíveis.
"""
import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERACOES = 250_000


def _chave(senha: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERACOES)
    return kdf.derive(senha.encode("utf-8"))


def cifrar(dados: bytes, senha: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_chave(senha, salt)).encrypt(iv, dados, None)
    b64 = lambda b: base64.b64encode(b).decode()
    return json.dumps({"v": 1, "it": ITERACOES, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)})


def decifrar(pacote: str, senha: str) -> bytes:
    p = json.loads(pacote)
    d = lambda k: base64.b64decode(p[k])
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=d("salt"), iterations=p.get("it", ITERACOES))
    return AESGCM(kdf.derive(senha.encode("utf-8"))).decrypt(d("iv"), d("ct"), None)
