from flask import Blueprint, request, jsonify
import re
from database import get_db
from utils.auth import check_password, hash_password, login_required

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/get-profile", methods=["GET"])
@login_required
def get_profile(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()

    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    return jsonify({
        "status": "success",
        "user": {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"],
            "institution": user["institution"],
            "auth_provider": user["auth_provider"],
            "language": user["language"],
            "created_at": user["created_at"]
        }
    }), 200


@profile_bp.route("/update-profile", methods=["PUT"])
@login_required
def update_profile(user_id):
    data = request.get_json()
    name = data.get("name")
    email = data.get("email")
    phone = data.get("phone")
    institution = data.get("institution")

    if not name or not email:
        return jsonify({"status": "error", "message": "Name and email required"}), 400

    db = get_db()
    cur = db.cursor()

    existing = cur.execute("SELECT * FROM users WHERE email = ? AND user_id != ?", (email, user_id)).fetchone()
    if existing:
        return jsonify({"status": "error", "message": "Email already used"}), 409

    cur.execute("""
        UPDATE users SET name = ?, email = ?, phone = ?, institution = ?
        WHERE user_id = ?
    """, (name, email, phone, institution, user_id))
    db.commit()

    return jsonify({"status": "success", "message": "Profile updated successfully"}), 200

@profile_bp.route("/change-password", methods=["POST"])
@login_required
def change_password(user_id):
    data = request.get_json()
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return jsonify({"status": "error", "message": "Current and new password required"}), 400

    if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#])[A-Za-z\d@$!%*?&#]{8,}$', new_password):
        return jsonify({"status": "error", "message": "Password must be 8+ chars, include uppercase, lowercase, number and special character (@$!%*?&)"}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cur.fetchone()

    if not check_password(current_password, user["password_hash"]):
        return jsonify({"status": "error", "message": "Current password is incorrect"}), 401

    cur.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (hash_password(new_password), user_id))
    db.commit()

    return jsonify({"status": "success", "message": "Password changed successfully"}), 200


@profile_bp.route("/update-language", methods=["POST"])
@login_required
def update_language(user_id):
    data = request.get_json()
    language = data.get("language")

    if language not in ["en", "ar"]:
        return jsonify({"status": "error", "message": "Language must be en or ar"}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET language = ? WHERE user_id = ?", (language, user_id))
    db.commit()

    return jsonify({"status": "success", "message": "Language updated successfully"}), 200