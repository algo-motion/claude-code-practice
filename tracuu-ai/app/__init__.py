"""Gói `app` được dùng cả bởi Flask lẫn Lambda (lambdas/*.py import app.services).

Lambda runtime không có Flask, nên mọi import Flask nằm trong create_app() để `import app.services` luôn nhẹ.
"""
import os


def create_app(cfg=None, services=None):
    from flask import Flask, jsonify, redirect, request, send_from_directory

    from .auth import RateLimiter
    from .config import Config
    from .services import build_services

    cfg = cfg or Config()
    if cfg.AUTH_MODE == "dev" and cfg.BACKEND == "aws":
        # Xác thực dev coi mọi request là quản trị viên: tuyệt đối không chạy cùng dữ liệu thật.
        raise RuntimeError("AUTH_MODE=dev không được dùng với BACKEND=aws; đặt AUTH_MODE=alb")
    static = os.path.abspath(cfg.STATIC_DIR)
    app = Flask(__name__, static_folder=None)
    app.config["CFG"] = cfg
    app.extensions["svc"] = services or build_services(cfg)
    app.extensions["limiter"] = RateLimiter(cfg.RATE_LIMIT_PER_MIN)

    from .admin.routes import bp as admin_bp
    from .library.routes import bp as library_bp, register_local_upload
    from .search.routes import bp as search_bp
    for bp in (search_bp, library_bp, admin_bp):
        app.register_blueprint(bp)
    if cfg.BACKEND == "local":
        register_local_upload(app)

    @app.get("/healthz")
    def healthz():  # ALB target group health check, không cần đăng nhập
        return "ok"

    @app.get("/auth/login")
    def login():
        # ALB đã bắt buộc xác thực OIDC với Cognito trước khi request tới đây.
        return redirect("/")

    @app.get("/auth/logout")
    def logout():
        resp = redirect(cfg.LOGOUT_URL)
        for name in request.cookies:
            if name.startswith("AWSELBAuthSessionCookie"):
                resp.delete_cookie(name)
        return resp

    @app.errorhandler(404)
    def not_found(_):
        return jsonify(error="not_found"), 404

    @app.errorhandler(500)
    def server_error(_):
        return jsonify(error="server_error"), 500

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path):
        if path.startswith(("api/", "auth/")):
            return jsonify(error="not_found"), 404
        if path and os.path.isfile(os.path.join(static, path)):
            return send_from_directory(static, path)
        if os.path.isfile(os.path.join(static, "index.html")):
            return send_from_directory(static, "index.html")
        return jsonify(error="Chưa build frontend (npm run build)"), 404

    return app
