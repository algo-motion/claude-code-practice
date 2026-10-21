import functools
import time
import urllib.request

import jwt
from flask import current_app, g, jsonify, request

from ..models import User

_key_cache = {}


def _alb_public_key(kid, region):
    if kid not in _key_cache:
        url = f"https://public-keys.auth.elb.{region}.amazonaws.com/{kid}"
        with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310 - URL cố định của AWS
            _key_cache[kid] = r.read().decode()
    return _key_cache[kid]


def _parse_groups(raw):
    if isinstance(raw, str):
        raw = raw.strip("[]").replace('"', "").split(",")
    return [s.strip() for s in (raw or []) if s and s.strip()]


def _build_user(claims, cfg):
    groups = _parse_groups(claims.get(cfg.GROUPS_CLAIM) or claims.get("cognito:groups"))
    is_admin = cfg.ADMIN_GROUP in groups
    # Mọi nhân viên đều thuộc nhóm toàn công ty.
    groups = tuple(dict.fromkeys([cfg.ALL_STAFF_GROUP, *groups]))
    email = claims.get("email", "")
    return User(id=claims["sub"], email=email, name=claims.get("name") or email.split("@")[0],
                groups=groups, is_admin=is_admin)


def _from_alb(cfg):
    token = request.headers.get("x-amzn-oidc-data")
    if not token:
        return None
    # ALB để lại ký tự '=' đệm trong base64url, PyJWT không chấp nhận.
    token = ".".join(p.rstrip("=") for p in token.split("."))
    try:
        header = jwt.get_unverified_header(token)
        if cfg.ALB_ARN and header.get("signer") != cfg.ALB_ARN:
            return None
        key = _alb_public_key(header["kid"], cfg.AWS_REGION)
        claims = jwt.decode(token, key, algorithms=["ES256"])
    except Exception as e:  # noqa: BLE001 - mọi lỗi xác thực đều coi là chưa đăng nhập
        current_app.logger.warning("JWT từ ALB không hợp lệ: %s", e)
        return None
    return _build_user(claims, cfg)


def _from_dev(cfg):
    admin = request.headers.get("X-Dev-Role", "admin") == "admin"
    groups = ["Tài chính", cfg.ADMIN_GROUP] if admin else ["Tài chính"]
    return _build_user({"sub": "dev-user", "email": "minh.anh@congty.vn", "name": "Trần Minh Anh",
                        cfg.GROUPS_CLAIM: groups}, cfg)


def current_user():
    if "user" not in g:
        cfg = current_app.config["CFG"]
        g.user = _from_alb(cfg) if cfg.AUTH_MODE == "alb" else _from_dev(cfg)
    return g.user


def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*a, **kw):
        if current_user() is None:
            return jsonify(error="unauthenticated"), 401
        return fn(*a, **kw)
    return wrapper


def require_admin(fn):
    @functools.wraps(fn)
    @login_required
    def wrapper(*a, **kw):
        if not current_user().is_admin:
            return jsonify(error="forbidden"), 403
        return fn(*a, **kw)
    return wrapper


class RateLimiter:
    """Cửa sổ trượt theo user, giữ trong bộ nhớ từng container (đủ để chặn lạm dụng cơ bản)."""

    def __init__(self, limit, window=60):
        self.limit, self.window, self.hits = limit, window, {}

    def allow(self, key):
        now = time.monotonic()
        q = [t for t in self.hits.get(key, []) if now - t < self.window]
        if len(q) >= self.limit:
            self.hits[key] = q
            return False
        q.append(now)
        self.hits[key] = q
        return True
