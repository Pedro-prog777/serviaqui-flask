from __future__ import annotations

import hashlib
import os
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from services.assistant_ai import ai_provider_status, build_reply, improve_announcement

from flask import Flask, jsonify, redirect, render_template, request, session, url_for, flash
load_dotenv()

try:
    import cloudinary
    import cloudinary.uploader
except Exception:  # pragma: no cover
    cloudinary = None

ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = ROOT / "uploads" / "announcements"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_dt(value: Optional[datetime]) -> str:
    normalized = ensure_utc(value)
    if not normalized:
        return ""
    return normalized.strftime("%d/%m/%Y %H:%M UTC")


def normalize_database_url(value: str) -> str:
    if not value:
        return f"sqlite:///{ROOT / 'instance' / 'serviaqui.db'}"
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql://", 1)
    return value


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "troque-esta-chave-em-producao")
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.getenv("DATABASE_URL", ""))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH_MB", "8")) * 1024 * 1024
    APP_ENV = os.getenv("APP_ENV", "development").strip().lower() or "development"
    BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", "8000"))
    DEFAULT_ADMIN_EMAIL = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@serviaqui.local").strip().lower()
    DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123456")
    RESET_TOKEN_MINUTES = int(os.getenv("RESET_TOKEN_MINUTES", "60"))
    SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
    SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "noreply@serviaqui.local").strip()
    SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "ServiAqui").strip()
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() != "false"
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", SMTP_FROM_EMAIL).strip()
    SUPPORT_NAME = os.getenv("SUPPORT_NAME", "Equipe ServiAqui").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = BASE_URL.startswith("https://") or APP_ENV == "production"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "").strip()
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "").strip()


app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))
app.config.from_object(Config)
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(180), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class Contact(db.Model):
    __tablename__ = "contacts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    channel = db.Column(db.String(80), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="novo")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(120), nullable=False)
    neighborhood = db.Column(db.String(120), nullable=True)
    price = db.Column(db.String(120), nullable=True)
    contact = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    accessibility = db.Column(db.Text, nullable=True)
    image_path = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="pendente", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class ChatLog(db.Model):
    __tablename__ = "chat_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    message = db.Column(db.Text, nullable=False)
    reply = db.Column(db.Text, nullable=False)
    provider = db.Column(db.String(60), nullable=False)
    page_context = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class PasswordResetRequest(db.Model):
    __tablename__ = "password_reset_requests"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=True)
    note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(40), nullable=False, default="recebido")
    delivery_status = db.Column(db.String(40), nullable=False, default="aguardando")
    delivery_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    email = db.Column(db.String(180), nullable=False, index=True)
    token_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


if cloudinary and all([
    app.config["CLOUDINARY_CLOUD_NAME"],
    app.config["CLOUDINARY_API_KEY"],
    app.config["CLOUDINARY_API_SECRET"],
]):
    cloudinary.config(
        cloud_name=app.config["CLOUDINARY_CLOUD_NAME"],
        api_key=app.config["CLOUDINARY_API_KEY"],
        api_secret=app.config["CLOUDINARY_API_SECRET"],
        secure=True,
    )


def is_valid_email(value: str) -> bool:
    value = value.strip().lower()
    return bool(value and "@" in value and "." in value.split("@")[-1])


def is_allowed_image(filename: str) -> bool:
    return bool(filename and "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_IMAGE_EXTENSIONS)


def image_url_from_path(path: Optional[str]) -> str:
    if not path:
        return ""
    path = str(path)
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("uploads/"):
        return f"/{path}"
    return path


def save_uploaded_image(file_storage) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not is_allowed_image(filename):
        raise ValueError("Envie uma imagem em PNG, JPG, JPEG ou WEBP.")
    if cloudinary and app.config["CLOUDINARY_CLOUD_NAME"]:
        result = cloudinary.uploader.upload(
            file_storage,
            folder="serviaqui/anuncios",
            resource_type="image",
            overwrite=False,
        )
        return str(result.get("secure_url") or result.get("url") or "")
    extension = filename.rsplit(".", 1)[-1].lower()
    safe_name = f"{uuid.uuid4().hex}.{extension}"
    destination = UPLOAD_DIR / safe_name
    file_storage.save(destination)
    return f"uploads/announcements/{safe_name}"


def email_ready() -> bool:
    return bool(app.config["SMTP_HOST"] and app.config["SMTP_FROM_EMAIL"])


def send_email(subject: str, text_body: str, html_body: str, recipients: list[str]) -> Tuple[bool, str]:
    if not recipients:
        return False, "Sem destinatários configurados."
    if not email_ready():
        return False, "SMTP ainda não configurado neste ambiente."

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{app.config['SMTP_FROM_NAME']} <{app.config['SMTP_FROM_EMAIL']}>"
    message["To"] = ", ".join(recipients)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(app.config["SMTP_HOST"], app.config["SMTP_PORT"], timeout=20) as server:
            server.ehlo()
            if app.config["SMTP_USE_TLS"]:
                server.starttls()
                server.ehlo()
            if app.config["SMTP_USERNAME"]:
                server.login(app.config["SMTP_USERNAME"], app.config["SMTP_PASSWORD"])
            server.send_message(message)
        return True, "E-mail enviado com sucesso."
    except Exception as exc:  # pragma: no cover
        return False, f"Falha no envio do e-mail: {exc}"



def get_current_user() -> Optional[User]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, int(user_id))


def user_to_dict(user: Optional[User]) -> Optional[Dict[str, Any]]:
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "created_at": format_dt(user.created_at),
    }


def announcement_to_dict(item: Announcement) -> Dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "neighborhood": item.neighborhood or "",
        "price": item.price or "",
        "contact": item.contact,
        "description": item.description,
        "accessibility": item.accessibility or "",
        "status": item.status,
        "created_at": format_dt(item.created_at),
        "image_url": image_url_from_path(item.image_path),
    }


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            return jsonify({"error": "Faça login para continuar."}), 401
        return fn(*args, **kwargs)

    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user or user.role != "admin":
            return jsonify({"error": "Acesso restrito à administração."}), 403
        return fn(*args, **kwargs)

    return wrapped



def hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def build_reset_link(raw_token: str) -> str:
    return f"{app.config['BASE_URL']}/redefinir-senha?token={raw_token}"


def create_reset_token(user: User) -> str:
    raw_token = secrets.token_urlsafe(32)
    db.session.add(
        PasswordResetToken(
            user_id=user.id,
            email=user.email,
            token_hash=hash_reset_token(raw_token),
            expires_at=utc_now() + timedelta(minutes=app.config["RESET_TOKEN_MINUTES"]),
        )
    )
    db.session.flush()
    return raw_token


def find_valid_reset_token(raw_token: str) -> Optional[PasswordResetToken]:
    token_hash = hash_reset_token(raw_token)
    token = PasswordResetToken.query.filter_by(token_hash=token_hash).first()
    if not token or token.used_at is not None:
        return None
    expires = ensure_utc(token.expires_at)
    if not expires or expires < utc_now():
        return None
    return token



def ensure_database() -> None:
    with app.app_context():
        db.create_all()
        admin = User.query.filter_by(email=app.config["DEFAULT_ADMIN_EMAIL"]).first()
        if not admin:
            db.session.add(
                User(
                    name="Administrador ServiAqui",
                    email=app.config["DEFAULT_ADMIN_EMAIL"],
                    password_hash=generate_password_hash(app.config["DEFAULT_ADMIN_PASSWORD"]),
                    role="admin",
                )
            )
            db.session.commit()



@app.get("/api/health")
def api_health():
    db_ok = True
    try:
        db.session.query(User.id).count()
    except Exception:
        db_ok = False

    return jsonify(
        {
            "status": "ok" if db_ok else "degraded",
            "service": "ServiAqui",
            "environment": app.config["APP_ENV"],
            "ai": ai_provider_status(),
            "database": {
                "ok": db_ok,
                "engine": "postgresql" if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql") else "sqlite",
            },
            "storage": "cloudinary" if (cloudinary and app.config["CLOUDINARY_CLOUD_NAME"]) else "local",
            "email": "smtp" if email_ready() else "não configurado",
        }
    )


@app.get("/api/config")
def api_config():
    return jsonify(
        {
            "project": "ServiAqui",
            "auth": {"has_session": bool(session.get("user_id"))},
            "platform": {
                "storage": "cloudinary" if (cloudinary and app.config["CLOUDINARY_CLOUD_NAME"]) else "local",
                "email": "smtp" if email_ready() else "não configurado",
                "database": "postgresql" if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql") else "sqlite",
                "base_url": app.config["BASE_URL"],
            },
            "ai": ai_provider_status(),
        }
    )


@app.get("/api/me")
def api_me():
    return jsonify({"user": user_to_dict(get_current_user())})


@app.post("/api/register")
def api_register():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if len(name) < 3:
        return jsonify({"error": "Informe um nome com pelo menos 3 caracteres."}), 400
    if not is_valid_email(email):
        return jsonify({"error": "Informe um e-mail válido."}), 400
    if len(password) < 6:
        return jsonify({"error": "A senha precisa ter pelo menos 6 caracteres."}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Já existe uma conta com este e-mail."}), 409

    user = User(name=name, email=email, password_hash=generate_password_hash(password), role="user")
    db.session.add(user)
    db.session.commit()

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"ok": True, "message": "Conta criada com sucesso.", "user": user_to_dict(user)})


@app.post("/api/login")
def api_login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "E-mail ou senha inválidos."}), 401

    session.permanent = True
    session["user_id"] = user.id
    return jsonify({"ok": True, "message": "Login realizado com sucesso.", "user": user_to_dict(user)})


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify({"ok": True, "message": "Sessão encerrada."})


@app.post("/api/contact")
def api_contact():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    subject = str(payload.get("subject", "")).strip()
    channel = str(payload.get("channel", "")).strip()
    message = str(payload.get("message", "")).strip()

    if not all([name, email, subject, channel, message]):
        return jsonify({"error": "Preencha todos os campos do contato."}), 400
    if not is_valid_email(email):
        return jsonify({"error": "Informe um e-mail válido para retorno."}), 400

    user = get_current_user()
    row = Contact(
        user_id=user.id if user else None,
        name=name,
        email=email,
        subject=subject,
        channel=channel,
        message=message,
    )
    db.session.add(row)
    db.session.commit()

    if app.config["SUPPORT_EMAIL"] and email_ready():
        send_email(
            subject=f"Novo contato pelo site: {subject}",
            text_body=f"Nome: {name}\nE-mail: {email}\nCanal: {channel}\n\nMensagem:\n{message}",
            html_body=(
                f"<p><strong>Nome:</strong> {name}</p>"
                f"<p><strong>E-mail:</strong> {email}</p>"
                f"<p><strong>Canal:</strong> {channel}</p>"
                f"<p><strong>Mensagem:</strong><br>{message}</p>"
            ),
            recipients=[app.config["SUPPORT_EMAIL"]],
        )

    return jsonify({"ok": True, "message": "Mensagem enviada com sucesso.", "id": row.id})


@app.get("/api/announcements")
def api_announcements_list():
    status = str(request.args.get("status", "aprovado")).strip().lower() or "aprovado"
    query = str(request.args.get("q", "")).strip().lower()
    category = str(request.args.get("category", "")).strip().lower()
    limit = min(max(int(request.args.get("limit", "12")), 1), 48)

    statement = Announcement.query.filter_by(status=status)
    if query:
        like = f"%{query}%"
        statement = statement.filter(
            or_(
                func.lower(Announcement.name).like(like),
                func.lower(Announcement.category).like(like),
                func.lower(func.coalesce(Announcement.neighborhood, "")).like(like),
                func.lower(Announcement.description).like(like),
                func.lower(Announcement.contact).like(like),
                func.lower(func.coalesce(Announcement.accessibility, "")).like(like),
            )
        )
    if category and category != "todos":
        statement = statement.filter(func.lower(Announcement.category).like(f"%{category}%"))

    rows = statement.order_by(Announcement.id.desc()).limit(limit).all()
    return jsonify({"items": [announcement_to_dict(row) for row in rows]})


@app.post("/api/announcements")
def api_announcements_create():
    is_form = (request.content_type or "").startswith("multipart/form-data")
    payload = request.form if is_form else (request.get_json(silent=True) or {})

    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "")).strip()
    neighborhood = str(payload.get("neighborhood", "")).strip()
    price = str(payload.get("price", "")).strip()
    contact = str(payload.get("contact", "")).strip()
    description = str(payload.get("description", "")).strip()
    accessibility = str(payload.get("accessibility", "")).strip()

    if len(name) < 3 or not category or not contact or len(description) < 20:
        return jsonify({"error": "Revise o anúncio. Nome, categoria, contato e descrição detalhada são obrigatórios."}), 400

    image_path = ""
    if is_form and "image" in request.files and request.files["image"].filename:
        try:
            image_path = save_uploaded_image(request.files["image"])
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover
            return jsonify({"error": f"Não foi possível processar a imagem agora: {exc}"}), 400

    user = get_current_user()
    announcement = Announcement(
        user_id=user.id if user else None,
        name=name,
        category=category,
        neighborhood=neighborhood or None,
        price=price or None,
        contact=contact,
        description=description,
        accessibility=accessibility or None,
        image_path=image_path or None,
        status="pendente",
    )
    db.session.add(announcement)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "message": "Anúncio recebido e enviado para moderação.",
            "id": announcement.id,
            "status": announcement.status,
            "image_url": image_url_from_path(announcement.image_path),
        }
    )


@app.post("/api/assistente")
def api_assistente():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    page = str(payload.get("page", "")).strip()

    if len(message) < 3:
        return jsonify({"error": "Escreva uma mensagem com mais detalhes."}), 400

    history = session.get("assistant_history", [])

    live_services = []
    rows = (
        Announcement.query
        .filter_by(status="aprovado")
        .order_by(Announcement.created_at.desc())
        .limit(6)
        .all()
    )
    live_services = [
        {
            "name": row.name,
            "category": row.category,
            "neighborhood": row.neighborhood,
            "description": row.description,
        }
        for row in rows
    ]

    data = build_reply(message, page, history, live_services)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": data.get("reply", "")})
    session["assistant_history"] = history[-8:]

    user = get_current_user()
    db.session.add(
        ChatLog(
            user_id=user.id if user else None,
            message=message,
            reply=data.get("reply", ""),
            provider=data.get("provider", "local"),
            page_context=page or None,
        )
    )
    db.session.commit()
    return jsonify(data)


@app.post("/api/anuncio")
def api_anuncio_melhorar():
    payload = request.get_json(silent=True) or {}
    return jsonify(improve_announcement(payload))


@app.post("/api/password-reset-request")
def api_password_reset_request():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    name = str(payload.get("name", "")).strip()
    note = str(payload.get("note", "")).strip()

    if not is_valid_email(email):
        return jsonify({"error": "Informe um e-mail válido para continuar."}), 400

    user = User.query.filter_by(email=email).first()
    debug_link = ""
    delivery_status = "sem_envio"
    delivery_message = "Conta não localizada."

    if user:
        raw_token = create_reset_token(user)
        reset_link = build_reset_link(raw_token)
        subject = "Redefinição de senha - ServiAqui"
        text_body = (
            f"Olá, {user.name}.\n\n"
            f"Use este link para redefinir sua senha:\n{reset_link}\n\n"
            f"O link expira em {app.config['RESET_TOKEN_MINUTES']} minutos."
        )
        html_body = (
            f"<p>Olá, <strong>{user.name}</strong>.</p>"
            f"<p>Use o link abaixo para redefinir sua senha no ServiAqui.</p>"
            f"<p><a href='{reset_link}' style='display:inline-block;padding:12px 18px;background:#1b4d8f;color:#fff;text-decoration:none;border-radius:10px;'>Redefinir senha</a></p>"
            f"<p>Se preferir, copie este link:<br>{reset_link}</p>"
        )
        sent, result_message = send_email(subject, text_body, html_body, [user.email])
        if sent:
            delivery_status, delivery_message = "email_enviado", result_message
        else:
            delivery_status, delivery_message = "pendente_manual", result_message
            if app.config["APP_ENV"] != "production":
                debug_link = reset_link

    db.session.add(
        PasswordResetRequest(
            email=email,
            name=name or None,
            note=note or None,
            status="recebido",
            delivery_status=delivery_status,
            delivery_message=delivery_message,
        )
    )
    db.session.commit()

    response = {
        "ok": True,
        "message": "Se o e-mail estiver cadastrado, você receberá instruções para redefinir a senha.",
    }
    if debug_link:
        response["debug_reset_link"] = debug_link
    return jsonify(response)


@app.get("/api/password-reset/validate")
def api_password_reset_validate():
    raw_token = str(request.args.get("token", "")).strip()
    token = find_valid_reset_token(raw_token)
    if not token:
        return jsonify({"valid": False, "error": "O link de redefinição está inválido ou expirou."}), 400
    return jsonify({"valid": True, "email": token.email, "expires_at": format_dt(token.expires_at)})


@app.post("/api/password-reset/confirm")
def api_password_reset_confirm():
    payload = request.get_json(silent=True) or {}
    raw_token = str(payload.get("token", "")).strip()
    password = str(payload.get("password", "")).strip()

    if len(password) < 6:
        return jsonify({"error": "A nova senha precisa ter pelo menos 6 caracteres."}), 400

    token = find_valid_reset_token(raw_token)
    if not token:
        return jsonify({"error": "O link de redefinição está inválido ou expirou."}), 400

    user = db.session.get(User, token.user_id)
    if not user:
        return jsonify({"error": "Conta não localizada."}), 404

    user.password_hash = generate_password_hash(password)
    token.used_at = utc_now()
    db.session.commit()
    return jsonify({"ok": True, "message": "Senha atualizada com sucesso. Faça login para continuar."})



@app.get("/api/dashboard")
@login_required
def api_dashboard():
    user = get_current_user()
    assert user is not None

    return jsonify(
        {
            "user": user_to_dict(user),
            "stats": {
                "announcements": Announcement.query.filter_by(user_id=user.id).count(),
                "contacts": Contact.query.filter_by(user_id=user.id).count(),
                "chats": ChatLog.query.filter_by(user_id=user.id).count(),
            },
            "latest_announcements": [
                announcement_to_dict(item)
                for item in Announcement.query.filter_by(user_id=user.id).order_by(Announcement.id.desc()).limit(5).all()
            ],
            "latest_contacts": [
                {
                    "id": item.id,
                    "subject": item.subject,
                    "channel": item.channel,
                    "status": item.status,
                    "created_at": format_dt(item.created_at),
                }
                for item in Contact.query.filter_by(user_id=user.id).order_by(Contact.id.desc()).limit(5).all()
            ],
            "latest_chats": [
                {
                    "id": item.id,
                    "message": item.message,
                    "provider": item.provider,
                    "created_at": format_dt(item.created_at),
                }
                for item in ChatLog.query.filter_by(user_id=user.id).order_by(ChatLog.id.desc()).limit(5).all()
            ],
        }
    )


@app.get("/api/admin/overview")
@admin_required
def api_admin_overview():
    return jsonify(
        {
            "counts": {
                "users": User.query.count(),
                "announcements": Announcement.query.count(),
                "contacts": Contact.query.count(),
                "chats": ChatLog.query.count(),
                "pending_announcements": Announcement.query.filter_by(status="pendente").count(),
                "password_resets": PasswordResetRequest.query.count(),
            },
            "recent_users": [user_to_dict(item) for item in User.query.order_by(User.id.desc()).limit(8).all()],
            "recent_contacts": [
                {
                    "id": item.id,
                    "name": item.name,
                    "email": item.email,
                    "subject": item.subject,
                    "channel": item.channel,
                    "status": item.status,
                    "created_at": format_dt(item.created_at),
                }
                for item in Contact.query.order_by(Contact.id.desc()).limit(8).all()
            ],
            "recent_announcements": [announcement_to_dict(item) for item in Announcement.query.order_by(Announcement.id.desc()).limit(8).all()],
            "recent_chats": [
                {
                    "id": item.id,
                    "message": item.message,
                    "provider": item.provider,
                    "page_context": item.page_context or "",
                    "created_at": format_dt(item.created_at),
                }
                for item in ChatLog.query.order_by(ChatLog.id.desc()).limit(8).all()
            ],
            "recent_password_resets": [
                {
                    "id": item.id,
                    "email": item.email,
                    "name": item.name or "",
                    "note": item.note or "",
                    "status": item.status,
                    "delivery_status": item.delivery_status,
                    "delivery_message": item.delivery_message or "",
                    "created_at": format_dt(item.created_at),
                }
                for item in PasswordResetRequest.query.order_by(PasswordResetRequest.id.desc()).limit(8).all()
            ],
            "admin_login_hint": {
                "email": app.config["DEFAULT_ADMIN_EMAIL"],
                "password": app.config["DEFAULT_ADMIN_PASSWORD"],
            },
        }
    )


@app.post("/api/admin/announcements/<int:announcement_id>/status")
@admin_required
def api_admin_announcement_status(announcement_id: int):
    payload = request.get_json(silent=True) or {}
    status = str(payload.get("status", "")).strip().lower()
    if status not in {"aprovado", "rejeitado", "pendente"}:
        return jsonify({"error": "Status inválido."}), 400

    announcement = db.session.get(Announcement, announcement_id)
    if not announcement:
        return jsonify({"error": "Anúncio não encontrado."}), 404

    announcement.status = status
    db.session.commit()
    return jsonify({"ok": True, "message": f"Anúncio atualizado para {status}."})


@app.get("/uploads/announcements/<path:filename>")
def uploaded_announcement_image(filename: str):
    return send_from_directory(UPLOAD_DIR, filename)



PAGE_META = {
    "home": {
        "template": "index.html",
        "title": "ServiAqui | Serviços locais com presença digital profissional",
        "description": "Plataforma para encontrar, publicar e gerir serviços locais com padrão premium, IA assistida e operação real.",
    },
    "services": {
        "template": "services.html",
        "title": "Serviços | ServiAqui",
        "description": "Catálogo premium com filtros, busca rápida e anúncios aprovados.",
    },
    "advertise": {
        "template": "advertise.html",
        "title": "Anunciar serviço | ServiAqui",
        "description": "Publique seu serviço com copy assistida por IA, preview e fluxo de moderação.",
    },
    "assistant": {
        "template": "assistant.html",
        "title": "Assistente IA | ServiAqui",
        "description": "Assistente para orientar navegação, melhorar anúncios e apoiar o atendimento.",
    },
    "about": {
        "template": "about.html",
        "title": "Sobre | ServiAqui",
        "description": "Visão de produto, posicionamento e operação do ServiAqui.",
    },
    "contact": {
        "template": "contact.html",
        "title": "Contato | ServiAqui",
        "description": "Fale com a equipe comercial ou de suporte.",
    },
    "accessibility": {
        "template": "accessibility.html",
        "title": "Acessibilidade | ServiAqui",
        "description": "Estrutura acessível, responsiva e confortável em qualquer dispositivo.",
    },
    "login": {
        "template": "login.html",
        "title": "Entrar | ServiAqui",
        "description": "Acesse sua conta, cadastre-se e acompanhe seus anúncios.",
    },
    "dashboard": {
        "template": "dashboard.html",
        "title": "Painel | ServiAqui",
        "description": "Resumo operacional do seu uso da plataforma.",
    },
    "admin": {
        "template": "admin.html",
        "title": "Admin | ServiAqui",
        "description": "Visão administrativa de usuários, contatos, anúncios e chats.",
    },
    "help": {
        "template": "help.html",
        "title": "Central de ajuda | ServiAqui",
        "description": "Dúvidas rápidas sobre a operação da plataforma.",
    },
    "privacy": {
        "template": "privacy.html",
        "title": "Privacidade | ServiAqui",
        "description": "Política de privacidade da aplicação.",
    },
    "security": {
        "template": "security.html",
        "title": "Segurança | ServiAqui",
        "description": "Boas práticas de segurança do projeto.",
    },
    "terms": {
        "template": "terms.html",
        "title": "Termos | ServiAqui",
        "description": "Termos de uso da plataforma.",
    },
    "password-request": {
        "template": "password_request.html",
        "title": "Recuperar senha | ServiAqui",
        "description": "Solicite um link para redefinir a senha.",
    },
    "password-reset": {
        "template": "password_reset.html",
        "title": "Redefinir senha | ServiAqui",
        "description": "Defina sua nova senha de acesso.",
    },
}


LEGAL_COPY = {
    "company_name": "ServiAqui",
    "tagline": "Serviços locais com confiança, agilidade e presença digital profissional.",
    "support_email": app.config["SUPPORT_EMAIL"],
    "support_name": app.config["SUPPORT_NAME"],
}


@app.context_processor
def inject_globals():
    return {"brand": LEGAL_COPY}


@app.template_filter("currency_label")
def currency_label(value: str) -> str:
    return value or "A combinar"


def render_page(page_key: str):
    page = PAGE_META[page_key]
    return render_template(
        page["template"],
        title=page["title"],
        page_key=page_key,
        meta_title=page["title"],
        meta_description=page["description"],
    )


@app.get("/")
def page_home():
    return render_page("home")


@app.get("/servicos")
def page_services():
    return render_page("services")


@app.get("/anunciar")
def page_advertise():
    return render_page("advertise")


@app.get("/assistente")
def page_assistant():
    return render_page("assistant")


@app.get("/sobre")
def page_about():
    return render_page("about")


@app.get("/contato")
def page_contact():
    return render_page("contact")


@app.get("/acessibilidade")
def page_accessibility():
    return render_page("accessibility")


@app.get("/login")
def page_login():
    return render_page("login")


@app.get("/painel")
def page_dashboard():
    return render_page("dashboard")


@app.get("/admin")
def page_admin():
    return render_page("admin")


@app.get("/ajuda")
def page_help():
    return render_page("help")


@app.get("/privacidade")
def page_privacy():
    return render_page("privacy")


@app.get("/seguranca")
def page_security():
    return render_page("security")


@app.get("/termos")
def page_terms():
    return render_page("terms")


@app.get("/recuperar-senha")
def page_password_request():
    return render_page("password-request")


@app.get("/redefinir-senha")
def page_password_reset():
    return render_page("password-reset")


LEGACY_ROUTES = {
    "index.html": "/",
    "servicos.html": "/servicos",
    "anunciar.html": "/anunciar",
    "assistente.html": "/assistente",
    "acessibilidade.html": "/acessibilidade",
    "sobre.html": "/sobre",
    "contato.html": "/contato",
    "login.html": "/login",
    "painel.html": "/painel",
    "admin.html": "/admin",
    "central-ajuda.html": "/ajuda",
    "privacidade.html": "/privacidade",
    "seguranca.html": "/seguranca",
    "termos.html": "/termos",
    "recuperar-senha.html": "/recuperar-senha",
    "redefinir-senha.html": "/redefinir-senha",
}

PUBLIC_ROOT_FILES = {"robots.txt", "sitemap.xml", "site.webmanifest"}
PROTECTED_PREFIXES = (
    "templates/",
    "services/",
    "__pycache__/",
    ".git/",
    ".venv/",
    "venv/",
)


def redirect_response(target: str):
    query = request.query_string.decode("utf-8")
    suffix = f"?{query}" if query else ""
    return "", 302, {"Location": f"{target}{suffix}"}


@app.errorhandler(404)
def not_found(_error):
    return (
        render_template(
            "error.html",
            title="Página não encontrada | ServiAqui",
            page_key="error",
            meta_title="Página não encontrada | ServiAqui",
            meta_description="A página solicitada não foi encontrada.",
            error_code="404",
            error_title="Página não encontrada",
            error_message="O endereço informado não existe ou foi alterado.",
            error_action_url="/",
            error_action_label="Voltar ao início",
        ),
        404,
    )


@app.errorhandler(500)
def server_error(_error):
    return (
        render_template(
            "error.html",
            title="Indisponibilidade momentânea | ServiAqui",
            page_key="error",
            meta_title="Indisponibilidade momentânea | ServiAqui",
            meta_description="Ocorreu uma indisponibilidade momentânea.",
            error_code="500",
            error_title="Indisponibilidade momentânea",
            error_message="Houve uma falha temporária. Tente novamente em instantes.",
            error_action_url="/",
            error_action_label="Ir para o início",
        ),
        500,
    )


@app.get("/<path:filename>")
def legacy_static_pages(filename: str):
    normalized = filename.strip().lstrip("/")
    basename = Path(normalized).name

    target = LEGACY_ROUTES.get(normalized) or LEGACY_ROUTES.get(basename)
    if target:
        return redirect_response(target)

    if normalized.startswith(PROTECTED_PREFIXES):
        return not_found(None)

    if basename in LEGACY_ROUTES and normalized.startswith("templates/"):
        return redirect_response(LEGACY_ROUTES[basename])

    target_file = (ROOT / normalized).resolve()
    if ROOT not in target_file.parents and target_file != ROOT:
        return jsonify({"error": "Acesso negado."}), 403

    if basename in PUBLIC_ROOT_FILES and target_file.is_file() and target_file.parent == ROOT:
        return send_from_directory(ROOT, basename)

    return not_found(None)


ensure_database()


if __name__ == "__main__":
    print(f"ServiAqui rodando em {app.config['BASE_URL']}")
    print(f"Banco: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"Armazenamento: {'Cloudinary' if (cloudinary and app.config['CLOUDINARY_CLOUD_NAME']) else 'Local'}")
    print(f"E-mail: {'SMTP configurado' if email_ready() else 'SMTP não configurado'}")
    print(f"Login admin padrão: {app.config['DEFAULT_ADMIN_EMAIL']} / {app.config['DEFAULT_ADMIN_PASSWORD']}")
    app.run(host=app.config['HOST'], port=app.config['PORT'], debug=False)

    
if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)