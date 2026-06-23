import requests
import os

def send_otp_email(to_email, otp):
    print(f"========== SENDING EMAIL VIA API ==========")
    print(f"To: {to_email}")

    api_key = os.getenv("BREVO_API_KEY")  # هنضيفه في Secrets بعد شوية
    sender_email = os.getenv("EMAIL_USER")

    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    # HTML الجميل بتاعك (حافظ على شكله)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background-color: #f4f6f8; margin:0; padding:40px 0;">
        <table align="center" width="500" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:12px; padding:40px; box-shadow:0 10px 25px rgba(0,0,0,0.08);">
            <tr>
                <td align="center">
                    
                    <!-- الصورة هنا -->
                    <img src="https://i.postimg.cc/cJf1zGDF/Whats-App-Image-2026-02-13-at-5-49-27-PM.png" alt="FractoScan" width="120" style="margin-bottom:20px;">
                    
                    <h2 style="color:#2c3e50;">🔐 FractoScan Verification</h2>
                    <p style="color:#7f8c8d;">Use the code below to continue</p>
                    <div style="font-size:36px; font-weight:bold; letter-spacing:8px; background:linear-gradient(90deg,#3498db,#6c5ce7); color:#fff; padding:18px 30px; border-radius:10px; display:inline-block;">{otp}</div>
                    <p style="color:#555; margin-top:30px;">This code will expire in <b>5 minutes</b>.</p>
                    <hr style="border-top:1px solid #eee;">
                    <p style="font-size:12px; color:#95a5a6;">© 2026 FractoScan. All rights reserved.</p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    data = {
        "sender": {"email": sender_email, "name": "FractoScan"},
        "to": [{"email": to_email}],
        "subject": "Your FractoScan verification code",
        "htmlContent": html_content
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 201:
            print("✅ Email sent successfully")
            return True
        else:
            print(f"❌ API Error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False