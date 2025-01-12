import datetime
import hashlib

# Task4: Implement Logging
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# Task1: Rate limiting the login page to 5 requests per minute.
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Task2+3: Content Security Policy + Secure Headers (HSTS, X-Frame-Options)
from flask_talisman import Talisman
from werkzeug.utils import secure_filename

# Configure the logger
handler = RotatingFileHandler("app.log", maxBytes=10000, backupCount=3)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)


from database import (
    add_user,
    delete_image_from_db,
    delete_note_from_db,
    delete_user_from_db,
    image_upload_record,
    list_images_for_user,
    list_users,
    match_user_id_with_image_uid,
    match_user_id_with_note_id,
    read_note_from_db,
    verify,
    write_note_into_db,
)

app = Flask(__name__)
app.config.from_object("config")

# Task2+3: Content Security Policy + Secure Headers (HSTS, X-Frame-Options)
talisman = Talisman(app=app)
csp = {
    "default-src": [
        "'self'",
        "https://stackpath.bootstrapcdn.com",
        "https://code.jquery.com",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://fonts.googleapis.com",
        "https://fonts.gstatic.com",
        "https://cdn.jsdelivr.net",
        "https://cdn.datatables.net",
    ],
    "style-src-elem":[
        "'self'",
        "https://stackpath.bootstrapcdn.com",
        "https://cdn.jsdelivr.net",
        "https://fonts.googleapis.com",
        "https://cdn.datatables.net",
    ]
}

hsts = {"max_age": 31536000, "include_subdomains": True}
# Enforce HTTPS and other headers
talisman.force_https = True
talisman.force_file_save = True
talisman.x_xss_protection = True
talisman.session_cookie_secure = True
talisman.session_cookie_samesite = "Lax"
talisman.frame_options_allow_from = "https://www.google.com"

# Add the headers to Talisman
talisman.content_security_policy = csp
talisman.strict_transport_security = hsts

# Task1: Rate limiting the login page to 5 requests per minute.
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=["5 per minute"])

# Task4: Implement Logging
app.logger.addHandler(handler)


@app.errorhandler(401)
def FUN_401(error):
    return render_template("page_401.html"), 401


@app.errorhandler(403)
def FUN_403(error):
    return render_template("page_403.html"), 403


@app.errorhandler(404)
def FUN_404(error):
    return render_template("page_404.html"), 404


@app.errorhandler(405)
def FUN_405(error):
    return render_template("page_405.html"), 405


@app.errorhandler(413)
def FUN_413(error):
    return render_template("page_413.html"), 413


@app.errorhandler(429)
def ratelimit_error(error):
    app.logger.warning(f"Rate limit exceeded: {request.remote_addr}")
    return "Rate limit exceeded. Please try again later.", 429


@app.route("/")
def FUN_root():
    return render_template("index.html")


@app.route("/public/")
def FUN_public():
    return render_template("public_page.html")


@app.route("/private/")
def FUN_private():
    if "current_user" in session.keys():
        notes_list = read_note_from_db(session["current_user"])
        notes_table = zip(
            [x[0] for x in notes_list],
            [x[1] for x in notes_list],
            [x[2] for x in notes_list],
            ["/delete_note/" + x[0] for x in notes_list],
        )

        images_list = list_images_for_user(session["current_user"])
        images_table = zip(
            [x[0] for x in images_list],
            [x[1] for x in images_list],
            [x[2] for x in images_list],
            ["/delete_image/" + x[0] for x in images_list],
        )

        return render_template(
            "private_page.html", notes=notes_table, images=images_table
        )
    else:
        return abort(401)


@app.route("/admin/")
def FUN_admin():
    if session.get("current_user", None) == "ADMIN":
        user_list = list_users()
        user_table = zip(
            range(1, len(user_list) + 1),
            user_list,
            [x + y for x, y in zip(["/delete_user/"] * len(user_list), user_list)],
        )
        return render_template("admin.html", users=user_table)
    else:
        return abort(401)


@app.route("/write_note", methods=["POST"])
def FUN_write_note():
    text_to_write = request.form.get("text_note_to_take")
    write_note_into_db(session["current_user"], text_to_write)

    return redirect(url_for("FUN_private"))


@app.route("/delete_note/<note_id>", methods=["GET"])
def FUN_delete_note(note_id):
    if session.get("current_user", None) == match_user_id_with_note_id(
        note_id
    ):  # Ensure the current user is NOT operating on other users' note.
        delete_note_from_db(note_id)
    else:
        return abort(401)
    return redirect(url_for("FUN_private"))


# Reference: http://flask.pocoo.org/docs/0.12/patterns/fileuploads/
ALLOWED_EXTENSIONS = set(["png", "jpg", "jpeg", "gif"])


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/upload_image", methods=["POST"])
def FUN_upload_image():
    if request.method == "POST":
        # check if the post request has the file part
        if "file" not in request.files:
            flash("No file part", category="danger")
            return redirect(url_for("FUN_private"))
        file = request.files["file"]
        # if user does not select file, browser also submit a empty part without filename
        if file.filename == "":
            flash("No selected file", category="danger")
            return redirect(url_for("FUN_private"))
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_time = str(datetime.datetime.now())
            image_uid = hashlib.sha1((upload_time + filename).encode()).hexdigest()
            # Save the image into UPLOAD_FOLDER
            file.save(
                os.path.join(app.config["UPLOAD_FOLDER"], image_uid + "-" + filename)
            )
            # Record this uploading in database
            image_upload_record(
                image_uid, session["current_user"], filename, upload_time
            )
            return redirect(url_for("FUN_private"))

    return redirect(url_for("FUN_private"))


@app.route("/delete_image/<image_uid>", methods=["GET"])
def FUN_delete_image(image_uid):
    if session.get("current_user", None) == match_user_id_with_image_uid(
        image_uid
    ):  # Ensure the current user is NOT operating on other users' note.
        # delete the corresponding record in database
        delete_image_from_db(image_uid)
        # delete the corresponding image file from image pool
        image_to_delete_from_pool = [
            y
            for y in [x for x in os.listdir(app.config["UPLOAD_FOLDER"])]
            if y.split("-", 1)[0] == image_uid
        ][0]
        os.remove(os.path.join(app.config["UPLOAD_FOLDER"], image_to_delete_from_pool))
    else:
        return abort(401)
    return redirect(url_for("FUN_private"))


# Task1: Rate limiting the login page to 5 requests per minute.
@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def FUN_login():
    id_submitted = request.form.get("id").upper()

    # Log the login attempt
    app.logger.info(f"Login attempt by user: {id_submitted}")

    if id_submitted in list_users() and verify(id_submitted, request.form.get("pw")):
        session["current_user"] = id_submitted
        app.logger.info(f"Successful login for user: {id_submitted}")
    else:
        app.logger.warning(f"Failed login attempt for user: {id_submitted}")

    # Ensure log is written before redirecting
    app.logger.handlers[0].flush()

    return redirect(url_for("FUN_root"))


@app.route("/logout/")
def FUN_logout():
    session.pop("current_user", None)
    return redirect(url_for("FUN_root"))


@app.route("/delete_user/<id>/", methods=["GET"])
def FUN_delete_user(id):
    if session.get("current_user", None) == "ADMIN":
        if id == "ADMIN":  # ADMIN account can't be deleted.
            return abort(403)

        # [1] Delete this user's images in image pool
        images_to_remove = [x[0] for x in list_images_for_user(id)]
        for f in images_to_remove:
            image_to_delete_from_pool = [
                y
                for y in [x for x in os.listdir(app.config["UPLOAD_FOLDER"])]
                if y.split("-", 1)[0] == f
            ][0]
            os.remove(
                os.path.join(app.config["UPLOAD_FOLDER"], image_to_delete_from_pool)
            )
        # [2] Delele the records in database files
        delete_user_from_db(id)
        return redirect(url_for("FUN_admin"))
    else:
        return abort(401)


@app.route("/add_user", methods=["POST"])
def FUN_add_user():
    if (
        session.get("current_user", None) == "ADMIN"
    ):  # only Admin should be able to add user.
        # before we add the user, we need to ensure this is doesn't exsit in database. We also need to ensure the id is valid.
        if request.form.get("id").upper() in list_users():
            user_list = list_users()
            user_table = zip(
                range(1, len(user_list) + 1),
                user_list,
                [x + y for x, y in zip(["/delete_user/"] * len(user_list), user_list)],
            )
            return render_template(
                "admin.html", id_to_add_is_duplicated=True, users=user_table
            )
        if " " in request.form.get("id") or "'" in request.form.get("id"):
            user_list = list_users()
            user_table = zip(
                range(1, len(user_list) + 1),
                user_list,
                [x + y for x, y in zip(["/delete_user/"] * len(user_list), user_list)],
            )
            return render_template(
                "admin.html", id_to_add_is_invalid=True, users=user_table
            )
        else:
            add_user(request.form.get("id"), request.form.get("pw"))
            return redirect(url_for("FUN_admin"))
    else:
        return abort(401)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", ssl_context="adhoc")

