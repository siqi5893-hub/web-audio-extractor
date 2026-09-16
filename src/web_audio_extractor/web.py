import hmac
import os
import subprocess
import threading

from flask import Flask, Response, render_template, request, send_file

from .core import AudioExtractor, extractor_from_env


def create_app(extractor: AudioExtractor | None = None, app_token: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024
    engine = extractor or extractor_from_env()
    token = app_token if app_token is not None else os.getenv("APP_TOKEN", "")
    lock = threading.Lock()

    @app.after_request
    def headers(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return render_template("index.html", token_required=bool(token))

    @app.post("/extract")
    def extract():
        if token and not hmac.compare_digest(request.form.get("token", ""), token):
            return render_template("error.html", message="访问令牌不正确"), 401
        if not lock.acquire(blocking=False):
            return render_template("error.html", message="已有任务正在运行"), 429
        try:
            result = engine.extract(request.form.get("url", ""))
            return send_file(result, as_attachment=True, download_name=result.name)
        except ValueError as exc:
            return render_template("error.html", message=str(exc)), 400
        except (RuntimeError, OSError, subprocess.SubprocessError):
            return render_template("error.html", message="提取失败，请检查链接、网络或 Cookie"), 502
        finally:
            lock.release()

    return app


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"} and not os.getenv("APP_TOKEN"):
        raise SystemExit("公开监听前必须设置 APP_TOKEN")
    create_app().run(host=host, port=int(os.getenv("PORT", "8081")), debug=False)


if __name__ == "__main__":
    main()
