from flask import Blueprint, request, jsonify
import jwt
from datetime import datetime, timedelta, timezone
import hashlib
import random
import time
import re
import os
from database import get_db
from models.user import get_user_by_email, create_user
from utils.auth import hash_password, check_password, login_required
from utils.email import send_otp_email

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json()

    required = ["name", "email", "password"]
    if not all(field in data for field in required):
        return jsonify({"status": "error", "message": "All fields required"}), 400

    if get_user_by_email(data["email"]):
        return jsonify({"status": "error", "message": "Email already exists"}), 409

    if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$', data["password"]):
        return jsonify({"status": "error", "message": "Password must be 8+ chars, include uppercase, lowercase, number and special character (@$!%*?&)"}), 400

    password_hash = hash_password(data["password"])
    create_user(data["name"], data["email"], password_hash)

    return jsonify({"status": "success", "message": "User registered successfully"}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json()

    if "email" not in data or "password" not in data:
        return jsonify({"status": "error", "message": "Email & password required"}), 400

    user = get_user_by_email(data["email"])

    if not user or not check_password(data["password"], user["password_hash"]):
        return jsonify({"status": "error", "message": "Invalid email or password"}), 401

    token = jwt.encode({"user_id": user["user_id"], "exp": datetime.now(timezone.utc) + timedelta(days=7)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    refresh_token = jwt.encode({"user_id": user["user_id"], "exp": datetime.now(timezone.utc) + timedelta(days=30)}, os.getenv("SECRET_KEY"), algorithm="HS256")

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET refresh_token = ? WHERE user_id = ?", (refresh_token, user["user_id"]))
    db.commit()

    return jsonify({"status": "success", "message": "Login successful", "token": token, "refresh_token": refresh_token, "user": {"user_id": user["user_id"], "name": user["name"], "email": user["email"]}}), 200


@auth_bp.route("/social-login", methods=["POST"])
def social_login():
    data = request.get_json()
    email = data.get("email")
    name = data.get("name")
    provider = data.get("provider")
    provider_id = data.get("provider_id")

    if not email or not provider or not provider_id:
        return jsonify({"status": "error", "message": "Missing fields"}), 400

    db = get_db()
    cur = db.cursor()
    user = cur.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user:
        token = jwt.encode({"user_id": user["user_id"], "exp": datetime.now(timezone.utc) + timedelta(days=7)}, os.getenv("SECRET_KEY"), algorithm="HS256")
        refresh_token = jwt.encode({"user_id": user["user_id"], "exp": datetime.now(timezone.utc) + timedelta(days=30)}, os.getenv("SECRET_KEY"), algorithm="HS256")
        cur.execute("UPDATE users SET refresh_token = ? WHERE user_id = ?", (refresh_token, user["user_id"]))
        db.commit()
        return jsonify({"status": "success", "message": "Login successful", "token": token, "refresh_token": refresh_token, "user": {"user_id": user["user_id"], "name": user["name"], "email": user["email"], "auth_provider": user["auth_provider"], "language": user["language"], "created_at": user["created_at"]}}), 200

    password_generated = hash_password(provider_id)
    cur.execute("INSERT INTO users (name, email, password_hash, auth_provider) VALUES (?, ?, ?, ?)", (name, email, password_generated, provider))
    db.commit()

    new_user = cur.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    new_token = jwt.encode({"user_id": new_user["user_id"], "exp": datetime.now(timezone.utc) + timedelta(days=7)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    new_refresh_token = jwt.encode({"user_id": new_user["user_id"], "exp": datetime.now(timezone.utc) + timedelta(days=30)}, os.getenv("SECRET_KEY"), algorithm="HS256")
    cur.execute("UPDATE users SET refresh_token = ? WHERE user_id = ?", (new_refresh_token, new_user["user_id"]))
    db.commit()

    return jsonify({"status": "success", "message": "New user registered", "token": new_token, "refresh_token": new_refresh_token, "user": {"user_id": new_user["user_id"], "name": new_user["name"], "email": new_user["email"], "auth_provider": new_user["auth_provider"], "language": new_user["language"], "created_at": new_user["created_at"]}}), 201


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"status": "error", "message": "Email required"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"status": "error", "message": "Email not found"}), 404

    if user["otp_last_sent"]:
        time_passed = int(time.time()) - user["otp_last_sent"]
        if time_passed < 60:
            remaining = 60 - time_passed
            return jsonify({"status": "error", "message": f"Please wait {remaining} seconds before requesting a new code"}), 429

    otp = str(random.randint(100000, 999999))
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    expire_time = int(time.time()) + 300

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET otp = ?, otp_expire = ?, otp_last_sent = ? WHERE email = ?", (otp_hash, expire_time, int(time.time()), email))
    db.commit()

    if not send_otp_email(email, otp):
        return jsonify({"status": "error", "message": "Failed to send OTP email"}), 500

    return jsonify({"status": "success", "message": "OTP sent to email"}), 200


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json()
    email = data.get("email")
    otp = data.get("otp")

    if not email or not otp:
        return jsonify({"status": "error", "message": "Email and OTP required"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    if user["otp"] != otp_hash:
        return jsonify({"status": "error", "message": "Invalid OTP"}), 401

    if not user["otp_expire"] or int(time.time()) > user["otp_expire"]:
        return jsonify({"status": "error", "message": "OTP expired"}), 401

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET otp_verified = 1 WHERE email = ?", (email,))
    db.commit()

    return jsonify({"status": "success", "message": "OTP verified"}), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data.get("email")
    new_password = data.get("new_password")

    if not email or not new_password:
        return jsonify({"status": "error", "message": "Email and new password required"}), 400

    if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$', new_password):
        return jsonify({"status": "error", "message": "Password must be 8+ chars, include uppercase, lowercase, number and special character (@$!%*?&)"}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    if not user["otp_verified"]:
        return jsonify({"status": "error", "message": "OTP verification required"}), 401

    password_hash = hash_password(new_password)
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET password_hash = ?, otp = NULL, otp_expire = NULL, otp_verified = 0 WHERE email = ?", (password_hash, email))
    db.commit()

    return jsonify({"status": "success", "message": "Password reset successful"}), 200


@auth_bp.route("/refresh-token", methods=["POST"])
def refresh_token():
    data = request.get_json()
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return jsonify({"status": "error", "message": "Refresh token required"}), 400

    try:
        decoded = jwt.decode(refresh_token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
        user_id = decoded["user_id"]

        db = get_db()
        cur = db.cursor()
        user = cur.execute("SELECT * FROM users WHERE user_id = ? AND refresh_token = ?", (user_id, refresh_token)).fetchone()

        if not user:
            return jsonify({"status": "error", "message": "Invalid refresh token"}), 401

        new_token = jwt.encode({"user_id": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7)}, os.getenv("SECRET_KEY"), algorithm="HS256")
        new_refresh_token = jwt.encode({"user_id": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=30)}, os.getenv("SECRET_KEY"), algorithm="HS256")

        cur.execute("UPDATE users SET refresh_token = ? WHERE user_id = ?", (new_refresh_token, user_id))
        db.commit()

        return jsonify({"status": "success", "token": new_token, "refresh_token": new_refresh_token}), 200

    except jwt.ExpiredSignatureError:
        return jsonify({"status": "error", "message": "Refresh token expired, please login again"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"status": "error", "message": "Invalid refresh token"}), 401
    

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout(user_id) :
    db = get_db()
    cur =db.cursor()
    cur.execute("UPDATE users SET refresh_token = NULL WHERE user_id = ?", (user_id,))
    db.commit()

    return jsonify({
        "status": "success",
        "message":"Logged out successfully"
    }), 200