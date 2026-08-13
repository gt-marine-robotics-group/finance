"""
auth.py - Authentication routes and login decorator.
"""

import os
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash

auth_bp = Blueprint("auth", __name__)

LOGIN_PASSWORD = os.environ.get("LOGIN_PASSWORD", "boats0519")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()
        if password == LOGIN_PASSWORD:
            session["logged_in"] = True
            session["user_name"] = name
            session.permanent = True
            return redirect(url_for("dashboard.dashboard"))
        else:
            flash("Wrong password", "error")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
