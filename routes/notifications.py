from flask import Blueprint, request, jsonify
from database import get_db
from utils.auth import login_required

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/notifications", methods=["GET"])
@login_required
def get_notifications(user_id):
    db = get_db()
    cur = db.cursor()

    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    offset = (page - 1) * limit

    total = cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ?", (user_id,)).fetchone()[0]

    notifications = cur.execute("""
        SELECT * FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?""", (user_id, limit, offset)).fetchall()

    unread_count = cur.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_id = ? AND is_read = 0""", (user_id,)).fetchone()[0]

    cur.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    db.commit()

    return jsonify({
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": -(-total // limit),
        "unread_count": unread_count,
        "notifications": [dict(n) for n in notifications]
    }), 200


@notifications_bp.route("/dashboard-stats", methods=["GET"])
@login_required
def dashboard_stats(user_id):
    db = get_db()
    cur = db.cursor()

    total_scans = cur.execute("SELECT COUNT(*) FROM scans WHERE user_id = ?", (user_id,)).fetchone()[0]

    total_fractures = cur.execute("""
        SELECT COUNT(*) FROM reports r
        JOIN scans s ON r.scan_id = s.scan_id
        WHERE s.user_id = ? AND r.fracture_detected = 1""", (user_id,)).fetchone()[0]

    total_normal = cur.execute("""
        SELECT COUNT(*) FROM reports r
        JOIN scans s ON r.scan_id = s.scan_id
        WHERE s.user_id = ? AND r.fracture_detected = 0""", (user_id,)).fetchone()[0]

    recent_scans = cur.execute("""
        SELECT s.scan_id, s.patient_name, s.patient_age,
        s.anatomical_region, s.status, s.created_at,
        r.fracture_detected, r.confidence
        FROM scans s
        LEFT JOIN reports r ON s.scan_id = r.scan_id
        WHERE s.user_id = ?
        ORDER BY s.created_at DESC LIMIT 3""", (user_id,)).fetchall()

    return jsonify({
        "status": "success",
        "stats": {
            "total_scans": total_scans,
            "total_fractures": total_fractures,
            "total_normal": total_normal
        },
        "recent_scans": [
            {**dict(scan), "confidence": round((scan["confidence"] or 0) * 100, 2)}
            for scan in recent_scans
        ]
    }), 200