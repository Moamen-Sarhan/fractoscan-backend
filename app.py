from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from ml_model import model
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from waitress import serve
from schema import create_db

load_dotenv()

app = Flask(__name__)

# ====================== CORS ======================
CORS(app, resources={r"/*": {"origins": "*"}})

# ====================== Rate Limiter ======================
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

@app.errorhandler(429)
def ratelimit_error(e=None):
    return jsonify({
        "status": "error",
        "message": "Too many attempts, please try again later"
    }), 429

# ====================== Blueprints ======================
from routes.auth import auth_bp
from routes.profile import profile_bp
from routes.scans import scans_bp
from routes.notifications import notifications_bp

app.register_blueprint(auth_bp)
app.register_blueprint(profile_bp)
app.register_blueprint(scans_bp)
app.register_blueprint(notifications_bp)

# ====================== Apply rate limits to specific auth endpoints ======================
from routes.auth import register, login, verify_otp
limiter.limit("5 per minute")(register)
limiter.limit("5 per minute")(login)
limiter.limit("5 per minute")(verify_otp)

# ====================== Initialize Database ======================
# creates tables if they don't exist (using schema.py)
create_db()

# ====================== Run Server ======================
if __name__ == "__main__":
    # Use waitress for production (compatible with Hugging Face)
    serve(app, host="0.0.0.0", port=7860)