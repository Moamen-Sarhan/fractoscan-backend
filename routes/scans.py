from flask import Blueprint, request, jsonify, send_file
import cv2
import numpy as np
import threading
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from database import get_db
from utils.auth import login_required
import requests as req
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename
import shutil


scans_bp = Blueprint("scans", __name__)

from ml_model import model

# تكوين رفع الملفات المؤقتة
UPLOAD_FOLDER = 'temp_uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

# إنشاء المجلد لو مش موجود
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def draw_box_on_image(image_path, location, confidence_percent):
    """
    ترسم مربع على الصورة مع تحويل الإحداثيات من (640, 640) للحجم الأصلي.
    """
    img = cv2.imread(image_path)
    if img is None:
        return None

    try:
        coords = location.split(',')
        if len(coords) == 4:
            x1_model, y1_model, x2_model, y2_model = [float(c) for c in coords]
            h_orig, w_orig = img.shape[:2]
            MODEL_SIZE = 640
            x1 = int(x1_model * w_orig / MODEL_SIZE)
            y1 = int(y1_model * h_orig / MODEL_SIZE)
            x2 = int(x2_model * w_orig / MODEL_SIZE)
            y2 = int(y2_model * h_orig / MODEL_SIZE)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
            label = f"Fracture {confidence_percent}%"
            cv2.putText(img, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            success, encoded_img = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if success:
                return io.BytesIO(encoded_img)
    except Exception as e:
        print(f"Error drawing box: {e}")
    return None

def run_analysis(scan_id, user_id, patient_name, image_path):
    db = get_db()
    cur = db.cursor()
    active = cur.execute("SELECT * FROM active_analysis WHERE scan_id = ?", (scan_id,)).fetchone()
    if not active:
        print(f"❌ Scan {scan_id} was cancelled before analysis started")
        cur.execute("UPDATE scans SET status = 'cancelled' WHERE scan_id = ?", (scan_id,))
        db.commit()
        return
    try:
        img = cv2.imread(image_path)
        if img is None:
            raise Exception("Could not read image file")
        img_resized = cv2.resize(img, (640, 640))
        active = cur.execute("SELECT * FROM active_analysis WHERE scan_id = ?", (scan_id,)).fetchone()
        if not active:
            print(f"❌ Scan {scan_id} was cancelled during analysis")
            cur.execute("UPDATE scans SET status = 'cancelled' WHERE scan_id = ?", (scan_id,))
            db.commit()
            return
        results = model.predict(
            source=img_resized,
            conf=0.20,
            iou=0.45,
            imgsz=640,
            verbose=False
        )
        result = results[0]
        fracture_detected = 0
        confidence = 0.0
        fracture_type = None
        location = None
        if len(result.boxes) > 0:
            best_box = max(result.boxes, key=lambda b: float(b.conf))
            class_idx = int(best_box.cls)
            confidence = float(best_box.conf)
            box = best_box.xyxy[0].tolist()
            location = f"{box[0]:.1f},{box[1]:.1f},{box[2]:.1f},{box[3]:.1f}"
            from ml_model import FRACTURE_CLASSES
            if class_idx < len(FRACTURE_CLASSES):
                fracture_type = FRACTURE_CLASSES[class_idx]
            else:
                fracture_type = f"Unknown_Class_{class_idx}"
            if fracture_type != "Healthy":
                fracture_detected = 1
        else:
            fracture_type = "Healthy"
            confidence = 1.0
        cur.execute("""
            INSERT INTO reports (scan_id, fracture_detected, confidence, fracture_type, location)
            VALUES (?, ?, ?, ?, ?)
        """, (scan_id, fracture_detected, confidence, fracture_type, location))
        # حفظ الصورة في مجلد خاص بالمستخدم
        user_folder = f"/data/images/user_{user_id}"
        os.makedirs(user_folder, exist_ok=True)
        image_filename = f"scan_{scan_id}.jpg"
        image_path_in_bucket = f"{user_folder}/{image_filename}"
        shutil.copyfile(image_path, image_path_in_bucket)
        cur.execute("UPDATE scans SET image_url = ? WHERE scan_id = ?", (image_path_in_bucket, scan_id))
        cur.execute("UPDATE scans SET status = 'done' WHERE scan_id = ?", (scan_id,))
        cur.execute("""
            INSERT INTO notifications (user_id, title, message)
            VALUES (?, ?, ?)
        """, (user_id, "Analysis Complete",
                f"Scan for {patient_name} is done - {'Fracture Detected' if fracture_detected else 'Normal'}"))
        db.commit()
    except Exception as e:
        print(f"Error in analysis: {e}")
        cur.execute("UPDATE scans SET status = 'failed' WHERE scan_id = ?", (scan_id,))
        db.commit()
    finally:
        cur.execute("DELETE FROM active_analysis WHERE scan_id = ?", (scan_id,))
        db.commit()
        if os.path.exists(image_path):
            os.remove(image_path)


@scans_bp.route("/analyze-scan", methods=["POST"])
@login_required
def analyze_scan(user_id):
    patient_name = request.form.get('patient_name')
    patient_age = request.form.get('patient_age')
    gender = request.form.get('gender', 'male').lower()
    if gender not in ['male', 'female']:
        gender = 'male'
    anatomical_region = request.form.get('anatomical_region')
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No image file provided"}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
    if not allowed_file(file.filename):
        return jsonify({"status": "error", "message": "File type not allowed"}), 400
    original_filename = secure_filename(file.filename)
    unique_filename = f"{user_id}_{datetime.now().timestamp()}_{original_filename}"
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        INSERT INTO scans (user_id, patient_name, patient_age, gender, anatomical_region, status)
        VALUES (?, ?, ?, ?, ?, 'analyzing')
    """, (user_id, patient_name, patient_age, gender, anatomical_region))
    db.commit()
    scan_id = cur.lastrowid
    cur.execute("""
        INSERT INTO active_analysis (scan_id, user_id, thread_id)
        VALUES (?, ?, ?)
    """, (scan_id, user_id, f"thread_{scan_id}"))
    db.commit()
    # بدء التحليل في thread
    thread = threading.Thread(
        target=run_analysis,
        args=(scan_id, user_id, patient_name, filepath)
    )
    thread.start()
    # محاولة جلب image_url إذا كان موجوداً (في العادة null لأن التحليل لم ينته)
    cur.execute("SELECT image_url FROM scans WHERE scan_id = ?", (scan_id,))
    row = cur.fetchone()
    image_url = row['image_url'] if row else None
    return jsonify({
        "status": "success",
        "message": "Analysis started",
        "scan_id": scan_id,
        "image_url": image_url
    }), 200


@scans_bp.route("/serve-image/<int:scan_id>", methods=["GET"])
@login_required
def serve_image(user_id, scan_id):
    db = get_db()
    cur = db.cursor()
    result = cur.execute("SELECT image_url FROM scans WHERE scan_id = ? AND user_id = ?", (scan_id, user_id)).fetchone()
    if not result or not result['image_url']:
        return jsonify({"status": "error", "message": "Image not found"}), 404
    image_path = result['image_url']
    if os.path.exists(image_path):
        return send_file(image_path, mimetype='image/jpeg')
    return jsonify({"status": "error", "message": "File not found"}), 404


@scans_bp.route("/report-details/<int:scan_id>", methods=["GET"])
@login_required
def report_details(user_id, scan_id):
    db = get_db()
    cur = db.cursor()
    result = cur.execute("""
        SELECT s.scan_id, s.patient_name, s.patient_age,
        s.gender, s.anatomical_region, s.status, s.created_at,
        r.report_id, r.fracture_detected, r.confidence,
        r.fracture_type, r.location, r.report_pdf_url,
        s.image_url
        FROM scans s
        LEFT JOIN reports r ON s.scan_id = r.scan_id
        WHERE s.scan_id = ? AND s.user_id = ?
    """, (scan_id, user_id)).fetchone()
    
    if not result:
        return jsonify({"status": "error", "message": "Report not found"}), 404
    
    report = dict(result)
    
    # ✅ إضافة أبعاد نموذج YOLO (640×640) عشان الفلاتر يحول الإحداثيات صح
    report["model_width"] = 640
    report["model_height"] = 640
    
    return jsonify({"status": "success", "report": report}), 200


@scans_bp.route("/user-reports", methods=["GET"])
@login_required
def user_reports(user_id):
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 10))
    offset = (page - 1) * limit
    db = get_db()
    cur = db.cursor()
    total = cur.execute("SELECT COUNT(*) FROM scans WHERE user_id = ?", (user_id,)).fetchone()[0]
    reports = cur.execute("""
        SELECT s.scan_id, s.patient_name, s.patient_age,
        s.gender, s.anatomical_region, s.status, s.created_at,
        r.report_id, r.fracture_detected, r.confidence,
        r.fracture_type, r.location
        FROM scans s
        LEFT JOIN reports r ON s.scan_id = r.scan_id
        WHERE s.user_id = ?
        ORDER BY s.created_at DESC
        LIMIT ? OFFSET ?
    """, (user_id, limit, offset)).fetchall()
    return jsonify({
        "status": "success",
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": -(-total // limit),
        "reports": [dict(r) for r in reports]
    }), 200


@scans_bp.route("/export-report/<int:scan_id>", methods=["GET"])
@login_required
def export_report(user_id, scan_id):
    db = get_db()
    cur = db.cursor()
    result = cur.execute("""
        SELECT s.scan_id, s.patient_name, s.patient_age,
        s.gender, s.anatomical_region, s.created_at, s.image_url,
        r.fracture_detected, r.confidence, r.fracture_type, r.location
        FROM scans s
        LEFT JOIN reports r ON s.scan_id = r.scan_id
        WHERE s.scan_id = ? AND s.user_id = ?
    """, (scan_id, user_id)).fetchone()
    if not result:
        return jsonify({"status": "error", "message": "Report not found"}), 404

    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24,
                                 textColor=colors.HexColor('#1a5f7a'), alignment=TA_CENTER, spaceAfter=30)
    story.append(Paragraph("FractoScan Medical Report", title_style))

    story.append(Paragraph("Patient Information", styles['Heading2']))
    patient_data = [
        ["Patient Name:", result['patient_name']],
        ["Age / Gender:", f"{result['patient_age']} / {result['gender']}"],
        ["Exam Type:", result['anatomical_region'] or "X-Ray"],
        ["Scan Date:", result['created_at']],
    ]
    patient_table = Table(patient_data, colWidths=[60*mm, 80*mm])
    patient_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8f4f8')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#1a5f7a')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))
    story.append(patient_table)
    story.append(Spacer(1, 15))

    confidence_percent = round((result['confidence'] or 0) * 100, 2)
    img_buffer = None
    if result['image_url']:
        image_path = result['image_url']
        if image_path.startswith('/data/'):
            image_path = image_path
        if os.path.exists(image_path) and result['location']:
            img_buffer = draw_box_on_image(image_path, result['location'], confidence_percent)
    if img_buffer:
        pil_img = Image(img_buffer, width=120*mm, height=100*mm)
        story.append(pil_img)
        story.append(Spacer(1, 10))
    story.append(Spacer(1, 10))

    story.append(Paragraph("AI Analysis Results", styles['Heading2']))
    if result['fracture_detected']:
        result_style = ParagraphStyle('ResultStyle', parent=styles['Normal'], fontSize=14,
                                      textColor=colors.HexColor('#d32f2f'), alignment=TA_LEFT, spaceAfter=10)
        story.append(Paragraph("<b>Result: Fracture Detected</b>", result_style))
        story.append(Paragraph(f"Confidence: {confidence_percent}%", styles['Normal']))
        from reportlab.graphics.shapes import Drawing, Rect
        d = Drawing(120*mm, 10)
        d.add(Rect(0, 0, int(120*mm * confidence_percent / 100), 10,
                   fillColor=colors.HexColor('#d32f2f'), strokeColor=None))
        d.add(Rect(0, 0, 120*mm, 10, fillColor=None,
                   strokeColor=colors.HexColor('#cccccc'), strokeWidth=1))
        story.append(d)
        story.append(Spacer(1, 5))
        if result['fracture_type']:
            story.append(Paragraph(f"<b>Fracture Type:</b> {result['fracture_type']}", styles['Normal']))
        story.append(Paragraph("<b>Recommendation:</b> Orthopedic consult required", styles['Normal']))
    else:
        story.append(Paragraph("<b>Result: No Fracture Detected</b>", styles['Normal']))
        story.append(Paragraph(f"Confidence: {confidence_percent}%", styles['Normal']))
        story.append(Paragraph("<b>Recommendation:</b> No action needed", styles['Normal']))
    story.append(Spacer(1, 20))

    disclaimer_style = ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=8,
                                      textColor=colors.HexColor('#666666'), alignment=TA_CENTER)
    story.append(Paragraph("FractoScan AI - For medical use only. Final diagnosis must be confirmed by a licensed professional.", disclaimer_style))

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"fractoscan_report_{scan_id}.pdf", mimetype="application/pdf")


@scans_bp.route("/cancel-scan/<int:scan_id>", methods=["POST"])
@login_required
def cancel_scan(user_id, scan_id):
    db = get_db()
    cur = db.cursor()
    active = cur.execute("SELECT * FROM active_analysis WHERE scan_id = ? AND user_id = ?", (scan_id, user_id)).fetchone()
    if not active:
        return jsonify({"status": "error", "message": "No active analysis found or already completed"}), 404
    cur.execute("DELETE FROM active_analysis WHERE scan_id = ?", (scan_id,))
    cur.execute("UPDATE scans SET status = 'cancelled' WHERE scan_id = ?", (scan_id,))
    db.commit()
    return jsonify({"status": "success", "message": "Analysis cancelled successfully"}), 200


@scans_bp.route("/delete-history", methods=["DELETE"])
@login_required
def delete_history(user_id):
    db = get_db()
    cur = db.cursor()
    scans = cur.execute("SELECT scan_id FROM scans WHERE user_id = ?", (user_id,)).fetchall()
    user_folder = f"/data/images/user_{user_id}"
    for scan in scans:
        scan_id = scan['scan_id']
        image_path = f"{user_folder}/scan_{scan_id}.jpg"
        if os.path.exists(image_path):
            os.remove(image_path)
            print(f"🗑️ Deleted image: {image_path}")
    if os.path.exists(user_folder) and not os.listdir(user_folder):
        os.rmdir(user_folder)
        print(f"🗑️ Deleted empty folder: {user_folder}")
    cur.execute("DELETE FROM reports WHERE scan_id IN (SELECT scan_id FROM scans WHERE user_id = ?)", (user_id,))
    cur.execute("DELETE FROM scans WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    db.commit()
    return jsonify({"status": "success", "message": "History deleted successfully"}), 200