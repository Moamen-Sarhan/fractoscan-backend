import jwt
import bcrypt
from functools import wraps
from flask import request, jsonify
import os

SECRET_KEY = os.getenv("SECRET_KEY")

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def verify_token(request):
    token = request.headers.get("Authorization")
    
    if not token:
        return None, "no_token"
    
    try:
        token = token.replace("Bearer ", "")
        data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return data["user_id"], None
    except jwt.ExpiredSignatureError:
        return None, "expired"
    except jwt.InvalidTokenError:
        return None, "invalid"

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id, error = verify_token(request)
        if not user_id:
            message = "Session expired, please login again" if error == "expired" else "Unauthorized"
            return jsonify({
                "status": "error",
                "message": message
            }), 401
        return f(user_id, *args, **kwargs)
    return decorated