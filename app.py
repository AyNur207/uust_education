"""Каталог знаний. Run with: python app.py."""
from __future__ import annotations

import functools
import math
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import (Flask, abort, current_app, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from seed import seed_database

ROOT = Path(__file__).resolve().parent
SUBJECTS = {"Математика": "∑", "Информатика": "01", "Английский язык": "Aa",
            "История": "§", "Основы ИТ": "⌘", "Программирование": "</>"}
KINDS = {"Конспект": "notes", "Презентация": "slides", "Шпаргалка": "cheat",
         "Задания": "tasks", "Полезная ссылка": "link"}
ALLOWED = {"pdf", "pptx", "docx", "png", "jpg", "jpeg"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, group_name TEXT NOT NULL DEFAULT '',
 course INTEGER NOT NULL DEFAULT 1, bio TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS materials (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 subject TEXT NOT NULL, course INTEGER NOT NULL, semester INTEGER NOT NULL,
 kind TEXT NOT NULL, topic TEXT NOT NULL DEFAULT '', author_id INTEGER NOT NULL REFERENCES users(id),
 filename TEXT, original_filename TEXT, external_url TEXT, format_label TEXT NOT NULL DEFAULT '',
 rating REAL NOT NULL DEFAULT 0, downloads INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0,
 content TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS favorites (
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
 PRIMARY KEY(user_id, material_id)
);
CREATE TABLE IF NOT EXISTS collections (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 demo INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS collection_items (
 collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
 material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
 PRIMARY KEY(collection_id, material_id)
);
CREATE TABLE IF NOT EXISTS reviews (
 id INTEGER PRIMARY KEY, material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
 user_id INTEGER NOT NULL REFERENCES users(id), rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
 body TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(material_id, user_id)
);
CREATE TABLE IF NOT EXISTS reports (
 id INTEGER PRIMARY KEY, material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
 user_id INTEGER NOT NULL REFERENCES users(id), reason TEXT NOT NULL, body TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS materials_subject ON materials(subject);
CREATE INDEX IF NOT EXISTS materials_created ON materials(created_at);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.create_function("casefold", 1, lambda value: (value or "").casefold())
    return g.db


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Войди в аккаунт, чтобы продолжить.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def local_next(value, fallback):
    # Only local paths: neither protocol-relative URLs nor backslashes.
    return value if value and value.startswith("/") and not value.startswith("//") and "\\" not in value and not any(ord(c) < 32 for c in value) else fallback


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(exist_ok=True)
    secret_file = Path(app.instance_path) / "session-secret"
    if not test_config and not secret_file.exists():
        secret_file.write_text(secrets.token_hex(32), encoding="utf-8")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or ("test-key" if test_config else secret_file.read_text().strip()),
        DATABASE=str(Path(app.instance_path) / "catalog.sqlite3"),
        UPLOAD_FOLDER=str(Path(app.instance_path) / "uploads"),
        MAX_CONTENT_LENGTH=21 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        PER_PAGE=12,
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    @app.teardown_appcontext
    def close_db(error=None):
        if (db := g.pop("db", None)) is not None:
            db.close()

    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        seed_database(db)
        db.commit()

    @app.before_request
    def prepare_request():
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (session.get("user_id"),)).fetchone()
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(24)
        if request.method == "POST":
            supplied = request.form.get("csrf_token", request.headers.get("X-CSRF-Token", ""))
            if not secrets.compare_digest(supplied.encode("utf-8"), session["csrf_token"].encode("utf-8")):
                abort(400, "Форма устарела. Обнови страницу и попробуй ещё раз.")

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @app.context_processor
    def template_context():
        saved = set()
        if g.get("user"):
            saved = {row[0] for row in get_db().execute("SELECT material_id FROM favorites WHERE user_id = ?", (g.user["id"],))}

        def page_url(page):
            args = request.args.to_dict(flat=False)
            args["page"] = page
            return url_for(request.endpoint, **args)

        return dict(subjects=SUBJECTS, kinds=KINDS, saved=saved, page_url=page_url,
                    csrf_token=lambda: session["csrf_token"])

    @app.template_filter("date_ru")
    def date_ru(value):
        months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        date = datetime.fromisoformat(value)
        return f"{date.day} {months[date.month-1]} {date.year}"

    @app.template_filter("rating")
    def rating(value):
        return f"{value:.1f}".replace(".", ",") if value else "—"

    @app.template_filter("material_count")
    def material_count(value):
        value = int(value)
        word = "материалов" if value % 100 in range(11,15) else ("материал" if value % 10 == 1 else "материала" if value % 10 in range(2,5) else "материалов")
        return f"{value} {word}"

    def material_or_404(material_id):
        row = get_db().execute("SELECT m.*, u.name AS author, u.group_name FROM materials m JOIN users u ON u.id=m.author_id WHERE m.id=?", (material_id,)).fetchone()
        if row is None:
            abort(404)
        return row

    def discard_upload(filename):
        try:
            (Path(app.config["UPLOAD_FOLDER"]) / filename).unlink(missing_ok=True)
        except OSError:
            # Windows can hold an active download open. The database update remains valid.
            app.logger.warning("An obsolete upload is still open: %s", filename)

    def material_rows(where="1=1", params=(), order="m.id", limit=None):
        sql = f"SELECT m.*,u.name AS author FROM materials m JOIN users u ON u.id=m.author_id WHERE {where} ORDER BY {order}"
        if limit:
            sql += " LIMIT ?"
            params = (*params, limit)
        return get_db().execute(sql, params).fetchall()

    def collection_rows(where="1=1", params=()):
        return get_db().execute(f"""SELECT c.*,u.name AS author,
          (SELECT count(*) FROM collection_items ci WHERE ci.collection_id=c.id) AS count
          FROM collections c JOIN users u ON u.id=c.user_id WHERE {where} ORDER BY c.id""", params).fetchall()

    @app.route("/")
    def home():
        counts = dict(get_db().execute("SELECT subject,count(*) FROM materials GROUP BY subject").fetchall())
        recent = material_rows(order="m.created_at DESC, m.id ASC", limit=3)
        return render_template("home.html", counts=counts, materials=recent, collections=collection_rows("c.demo=1"))

    @app.route("/catalog")
    def catalog():
        q = request.args.get("q", "").strip()[:200]
        subject = request.args.get("subject", "")
        course = request.args.get("course", "", type=str)
        semester = request.args.get("semester", "", type=str)
        selected_kinds = [k for k in request.args.getlist("kind") if k in KINDS]
        sort = request.args.get("sort", "new")
        clauses, params = ["1=1"], []
        if q:
            escaped = q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("casefold(m.title || ' ' || m.description || ' ' || m.topic || ' ' || m.subject) LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped}%")
        for field, value in [("subject", subject), ("course", course), ("semester", semester)]:
            if value:
                clauses.append(f"m.{field}=?")
                params.append(value)
        if selected_kinds:
            clauses.append("m.kind IN (" + ",".join("?" for _ in selected_kinds) + ")")
            params.extend(selected_kinds)
        where = " AND ".join(clauses)
        count = get_db().execute(f"SELECT count(*) FROM materials m WHERE {where}", params).fetchone()[0]
        pages = max(1, math.ceil(count / app.config["PER_PAGE"]))
        page = max(1, min(request.args.get("page", 1, type=int), pages))
        order = {"new": "m.created_at DESC, m.id ASC", "rating": "m.rating DESC, m.id", "popular": "m.downloads DESC, m.id", "title": "m.title COLLATE NOCASE"}.get(sort, "m.created_at DESC, m.id ASC")
        materials = get_db().execute(f"SELECT m.*,u.name AS author FROM materials m JOIN users u ON u.id=m.author_id WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?", (*params, app.config["PER_PAGE"], (page-1)*app.config["PER_PAGE"])).fetchall()
        return render_template("catalog.html", materials=materials, count=count, page=page, pages=pages, q=q,
                               subject=subject, course=course, semester=semester, selected_kinds=selected_kinds, sort=sort)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if g.user:
            return redirect(url_for("profile"))
        errors = {}
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().casefold()
            password = request.form.get("password", "")
            group_name = request.form.get("group_name", "").strip()
            course = request.form.get("course", 1, type=int)
            if not 2 <= len(name) <= 60: errors["name"] = "Введи имя: от 2 до 60 символов."
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254: errors["email"] = "Введи корректную почту."
            if not 8 <= len(password) <= 128: errors["password"] = "Пароль должен содержать от 8 до 128 символов."
            if password != request.form.get("password_confirm"): errors["password_confirm"] = "Пароли не совпадают."
            if course not in range(1, 5): errors["course"] = "Выбери курс от 1 до 4."
            if len(group_name) > 30: errors["group_name"] = "Не больше 30 символов."
            if get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone(): errors["email"] = "Эта почта уже зарегистрирована. Войди в аккаунт."
            if not errors:
                try:
                    cursor = get_db().execute("INSERT INTO users(name,email,password_hash,group_name,course) VALUES(?,?,?,?,?)", (name, email, generate_password_hash(password), group_name, course))
                    get_db().commit()
                except sqlite3.IntegrityError:
                    errors["email"] = "Эта почта уже зарегистрирована."
                else:
                    session.clear()
                    session["user_id"] = cursor.lastrowid
                    flash("Добро пожаловать! Твой аккаунт создан.", "success")
                    return redirect(url_for("profile"))
        return render_template("auth.html", mode="register", errors=errors), (400 if errors else 200)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("profile"))
        errors = {}
        if request.method == "POST":
            email = request.form.get("email", "").strip().casefold()
            password = request.form.get("password", "")
            user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not user or not user["password_hash"] or len(password) > 128 or not check_password_hash(user["password_hash"], password):
                errors["form"] = "Неверная почта или пароль."
            else:
                session.clear()
                session["user_id"] = user["id"]
                return redirect(local_next(request.args.get("next"), url_for("profile")))
        return render_template("auth.html", mode="login", errors=errors), (400 if errors else 200)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("home"))

    @app.route("/materials/<int:material_id>")
    def material(material_id):
        item = material_or_404(material_id)
        reviews = get_db().execute("SELECT r.*,u.name FROM reviews r JOIN users u ON u.id=r.user_id WHERE material_id=? ORDER BY r.id DESC", (material_id,)).fetchall()
        collections = collection_rows("c.user_id=?", (g.user["id"],)) if g.user else []
        memberships = {r[0] for r in get_db().execute("SELECT collection_id FROM collection_items WHERE material_id=?", (material_id,))}
        related = material_rows("m.id != ? AND (m.subject=? OR m.id IN (4,6,7))", (material_id,item["subject"]), limit=3)
        return render_template("material.html", item=item, reviews=reviews, collections=collections, memberships=memberships, related=related)

    @app.get("/materials/<int:material_id>/file")
    def material_file(material_id):
        item = material_or_404(material_id)
        if item["external_url"]:
            response = redirect(item["external_url"])
        elif item["filename"]:
            path = Path(app.config["UPLOAD_FOLDER"]) / item["filename"]
            if not path.is_file(): abort(404)
            response = send_file(path, as_attachment=request.args.get("download") == "1", download_name=item["original_filename"])
        elif item["demo"]:
            path = ROOT / "static" / "demo" / f"{item['id']}.pdf"
            if not path.is_file(): abort(404)
            response = send_file(path, as_attachment=request.args.get("download") == "1", download_name=f"Материал-{material_id}-пример.pdf")
        else:
            abort(404)
        if request.method == "GET" and request.args.get("download") == "1":
            get_db().execute("UPDATE materials SET downloads=downloads+1 WHERE id=?", (material_id,))
            get_db().commit()
        return response

    @app.post("/materials/<int:material_id>/favorite")
    @login_required
    def favorite(material_id):
        material_or_404(material_id)
        db = get_db()
        existing = db.execute("SELECT 1 FROM favorites WHERE user_id=? AND material_id=?", (g.user["id"], material_id)).fetchone()
        if existing:
            db.execute("DELETE FROM favorites WHERE user_id=? AND material_id=?", (g.user["id"],material_id))
        else:
            db.execute("INSERT INTO favorites VALUES(?,?)", (g.user["id"],material_id))
        db.commit()
        if request.headers.get("Accept") == "application/json":
            return jsonify(saved=not bool(existing))
        return redirect(local_next(request.form.get("next"), url_for("material", material_id=material_id)))

    @app.post("/materials/<int:material_id>/review")
    @login_required
    def review(material_id):
        material_or_404(material_id)
        score = request.form.get("rating", 0, type=int)
        body = request.form.get("body", "").strip()
        if score not in range(1,6) or not 3 <= len(body) <= 2000:
            flash("Выбери оценку и напиши отзыв от 3 до 2000 символов.", "error")
        else:
            db = get_db()
            db.execute("INSERT INTO reviews(material_id,user_id,rating,body,created_at) VALUES(?,?,?,?,?) ON CONFLICT(material_id,user_id) DO UPDATE SET rating=excluded.rating,body=excluded.body,created_at=excluded.created_at", (material_id,g.user["id"],score,body,datetime.now().isoformat()))
            db.execute("UPDATE materials SET rating=(SELECT AVG(rating) FROM reviews WHERE material_id=?) WHERE id=?", (material_id,material_id))
            db.commit()
            flash("Спасибо! Твой отзыв сохранён.", "success")
        return redirect(url_for("material", material_id=material_id, _anchor="reviews"))

    @app.route("/upload", methods=["GET","POST"])
    @app.route("/materials/<int:material_id>/edit", methods=["GET","POST"])
    @login_required
    def upload(material_id=None):
        item = material_or_404(material_id) if material_id else None
        if item and item["author_id"] != g.user["id"]: abort(403)
        errors = {}
        values = dict(item) if item else {}
        if request.method == "POST":
            values.update(request.form.to_dict())
            title = request.form.get("title", "").strip()
            subject = request.form.get("subject", "")
            course = request.form.get("course", type=int)
            semester = request.form.get("semester", type=int)
            kind = request.form.get("kind", "")
            topic = request.form.get("topic", "").strip()
            description = request.form.get("description", "").strip()
            mode = request.form.get("source_mode", "file")
            external_url = request.form.get("external_url", "").strip() if mode == "link" else ""
            if not 3 <= len(title) <= 150: errors["title"] = "Введи название от 3 до 150 символов."
            if subject not in SUBJECTS: errors["subject"] = "Выбери дисциплину."
            if course not in range(1,5): errors["course"] = "Выбери курс."
            if semester not in range(1,9): errors["semester"] = "Выбери семестр."
            if kind not in KINDS: errors["kind"] = "Выбери тип материала."
            if len(topic) > 120: errors["topic"] = "Не больше 120 символов."
            if len(description) > 5000: errors["description"] = "Не больше 5000 символов."
            if not request.form.get("rights"): errors["rights"] = "Подтверди право делиться материалом."
            file = request.files.get("file")
            filename = original_filename = None
            format_label = ""
            if mode == "link":
                try:
                    parsed = urlsplit(external_url)
                except ValueError:
                    parsed = urlsplit("")
                if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or len(external_url)>2000:
                    errors["source"] = "Добавь ссылку, начинающуюся с https:// или http://."
                else:
                    format_label = f"{parsed.hostname} · Внешний ресурс"
            elif mode != "file":
                errors["source"] = "Выбери файл или ссылку."
            elif file and file.filename:
                extension = file.filename.rsplit(".", 1)[-1].lower()
                file.seek(0,2)
                size = file.tell()
                file.seek(0)
                signature = file.read(8)
                file.seek(0)
                valid_signature = ((extension == "pdf" and signature.startswith(b"%PDF-")) or
                                   (extension in {"pptx","docx"} and signature.startswith(b"PK\x03\x04")) or
                                   (extension == "png" and signature.startswith(b"\x89PNG\r\n\x1a\n")) or
                                   (extension in {"jpg","jpeg"} and signature.startswith(b"\xff\xd8\xff")))
                if extension not in ALLOWED or not valid_signature:
                    errors["source"] = "Выбери корректный PDF, PPTX, DOCX, PNG или JPG."
                elif size > 20*1024*1024 or size == 0:
                    errors["source"] = "Нужен непустой файл размером до 20 МБ."
                else:
                    filename = f"{uuid.uuid4().hex}.{extension}"
                    original_filename = Path(file.filename.replace("\\", "/")).name[:200]
                    format_label = f"{extension.upper()} · {size/1024/1024:.2f} МБ".replace(".", ",")
            elif item and item["filename"] and not item["demo"]:
                filename, original_filename, format_label = item["filename"], item["original_filename"], item["format_label"]
            else:
                errors["source"] = "Загрузи файл или добавь полезную ссылку."
            if not errors:
                if file and file.filename and filename:
                    file.save(Path(app.config["UPLOAD_FOLDER"]) / filename)
                fields = (title,description,subject,course,semester,kind,topic,filename,original_filename,external_url or None,format_label)
                db = get_db()
                if item:
                    db.execute("UPDATE materials SET title=?,description=?,subject=?,course=?,semester=?,kind=?,topic=?,filename=?,original_filename=?,external_url=?,format_label=?,demo=0 WHERE id=?", (*fields,material_id))
                else:
                    cursor = db.execute("INSERT INTO materials(title,description,subject,course,semester,kind,topic,filename,original_filename,external_url,format_label,author_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (*fields,g.user["id"],datetime.now().isoformat()))
                    material_id = cursor.lastrowid
                db.commit()
                if item and item["filename"] and item["filename"] != filename:
                    discard_upload(item["filename"])
                flash("Изменения сохранены." if item else "Материал опубликован. Спасибо, что делишься знаниями!", "success")
                return redirect(url_for("material", material_id=material_id))
        return render_template("upload.html", item=item, values=values, errors=errors), (400 if errors else 200)

    @app.post("/materials/<int:material_id>/delete")
    @login_required
    def delete_material(material_id):
        item = material_or_404(material_id)
        if item["author_id"] != g.user["id"]: abort(403)
        get_db().execute("DELETE FROM materials WHERE id=?", (material_id,))
        get_db().commit()
        if item["filename"]:
            discard_upload(item["filename"])
        flash("Материал удалён из каталога.", "success")
        return redirect(url_for("profile"))

    @app.route("/profile")
    @login_required
    def profile():
        tab = request.args.get("tab", "materials")
        if tab not in {"materials", "favorites", "collections"}:
            tab = "materials"
        q = request.args.get("q", "").strip()[:200]
        user_id = g.user["id"]
        where = "m.author_id=?" if tab != "favorites" else "m.id IN (SELECT material_id FROM favorites WHERE user_id=?)"
        materials = material_rows(where, (user_id,), order="m.created_at DESC")
        if q: materials = [m for m in materials if q.casefold() in (m["title"]+m["description"]).casefold()]
        stats = [get_db().execute(sql, (user_id,)).fetchone()[0] for sql in ["SELECT count(*) FROM materials WHERE author_id=?", "SELECT count(*) FROM favorites WHERE user_id=?", "SELECT count(*) FROM collections WHERE user_id=?"]]
        return render_template("profile.html", tab=tab, q=q, materials=materials, stats=stats, collections=collection_rows("c.user_id=?", (user_id,)))

    @app.post("/profile/edit")
    @login_required
    def edit_profile():
        name, group_name, bio = (request.form.get(k, "").strip() for k in ("name","group_name","bio"))
        course = request.form.get("course", 1, type=int)
        if not 2 <= len(name) <=60 or len(group_name)>30 or len(bio)>200 or course not in range(1,5):
            flash("Проверь имя, группу и курс. Описание должно быть не длиннее 200 символов.", "error")
        else:
            get_db().execute("UPDATE users SET name=?,group_name=?,bio=?,course=? WHERE id=?", (name,group_name,bio,course,g.user["id"]))
            get_db().commit()
            flash("Профиль обновлён.", "success")
        return redirect(url_for("profile"))

    @app.get("/collections")
    def collections():
        mine = request.args.get("mine") == "1"
        if mine and not g.user:
            return redirect(url_for("login", next=url_for("collections", mine=1)))
        rows = collection_rows("c.user_id=?", (g.user["id"],)) if mine and g.user else collection_rows("c.demo=1" + (" OR c.user_id=?" if g.user else ""), (g.user["id"],) if g.user else ())
        return render_template("collections.html", collections=rows, mine=mine)

    @app.post("/collections/create")
    @login_required
    def create_collection():
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        if not 3<=len(title)<=120 or len(description)>1000:
            flash("Название: от 3 до 120 символов; описание: до 1000.", "error")
            return redirect(url_for("collections"))
        cursor = get_db().execute("INSERT INTO collections(title,description,user_id,created_at) VALUES(?,?,?,?)", (title,description,g.user["id"],datetime.now().isoformat()))
        get_db().commit()
        return redirect(url_for("collection", collection_id=cursor.lastrowid))

    def collection_or_404(collection_id):
        rows = collection_rows("c.id=?", (collection_id,))
        if not rows: abort(404)
        row = rows[0]
        if not row["demo"] and (not g.user or row["user_id"] != g.user["id"]): abort(403)
        return row

    @app.get("/collections/<int:collection_id>")
    def collection(collection_id):
        row = collection_or_404(collection_id)
        return render_template("collection.html", collection=row, materials=material_rows("m.id IN (SELECT material_id FROM collection_items WHERE collection_id=?)", (collection_id,)))

    @app.post("/collections/<int:collection_id>/items/<int:material_id>")
    @login_required
    def collection_item(collection_id, material_id):
        row = collection_or_404(collection_id)
        if row["user_id"] != g.user["id"]: abort(403)
        material_or_404(material_id)
        if request.form.get("action") == "remove":
            get_db().execute("DELETE FROM collection_items WHERE collection_id=? AND material_id=?", (collection_id,material_id))
            target = url_for("collection", collection_id=collection_id)
        else:
            get_db().execute("INSERT OR IGNORE INTO collection_items VALUES(?,?)", (collection_id,material_id))
            target = url_for("material", material_id=material_id)
            flash("Материал добавлен в подборку.", "success")
        get_db().commit()
        return redirect(target)

    @app.post("/materials/<int:material_id>/report")
    @login_required
    def report(material_id):
        material_or_404(material_id)
        reason = request.form.get("reason", "Файл не открывается")[:100]
        body = request.form.get("body", "").strip()[:2000]
        get_db().execute("INSERT INTO reports(material_id,user_id,reason,body,created_at) VALUES(?,?,?,?,?)", (material_id,g.user["id"],reason,body,datetime.now().isoformat()))
        get_db().commit()
        flash("Сообщение об ошибке сохранено. Спасибо!", "success")
        return redirect(url_for("material", material_id=material_id))

    @app.errorhandler(413)
    def too_large(error):
        return render_template("error.html", code=413, message="Файл больше 20 МБ. Выбери файл поменьше."), 413

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def show_error(error):
        messages = {400: "Обнови страницу и попробуй ещё раз.", 403: "Эта страница доступна только владельцу.", 404: "Кажется, эта полка пока пуста. Такой страницы нет."}
        return render_template("error.html", code=error.code, message=messages.get(error.code)), error.code

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
