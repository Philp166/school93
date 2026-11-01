"""Подтверждение входа одноразовым кодом из приложения на телефоне (TOTP, RFC 6238).
Подходит любое приложение-«ключ»: Яндекс Ключ, Google Authenticator, Microsoft Authenticator.
Никаких телефонов, почт и SMS: сайт не хранит и не передаёт персональные данные,
а код считается прямо в телефоне по общему секрету и текущему времени."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

ISSUER = "Школа 93"


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return str((struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % 1_000_000).zfill(6)


def now_code(secret, at=None):
    return _code(secret, int((at or time.time()) // 30))


def verify(secret, code, last_step=0, at=None):
    """Возвращает шаг времени, если код верный (±30 секунд на разницу часов), иначе None.
    Код, уже использованный для входа, второй раз не принимается."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6 or not secret:
        return None
    step = int((at or time.time()) // 30)
    for s in (step, step - 1, step + 1):
        if s > (last_step or 0) and hmac.compare_digest(_code(secret, s), code):
            return s
    return None


def uri(secret, login):
    label = quote(f"{ISSUER}:{login}")
    return f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}&digits=6&period=30"


def qr_svg(text):
    try:
        import qrcode
        import qrcode.image.svg
        img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
        return img.to_string(encoding="unicode")
    except Exception:  # noqa: BLE001
        return ""


def new_recovery():
    """8 резервных кодов на случай потери телефона: каждый срабатывает один раз."""
    return ["-".join(secrets.token_hex(2) for _ in range(2)) for _ in range(8)]


def hash_code(c):
    return hashlib.sha256(c.replace("-", "").strip().lower().encode()).hexdigest()
