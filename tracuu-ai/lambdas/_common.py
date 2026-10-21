from functools import lru_cache

from app.config import Config
from app.services import build_services


@lru_cache(maxsize=1)
def services():
    cfg = Config()
    cfg.BACKEND = "aws"
    return build_services(cfg)
