import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

def send_telegram_alert(company, title, job_url, docx_path=None):
    """
    Sends an email alert directly to your inbox with the generated 
    tailored Word resume (.docx) attached.
    """
    sender_email = os.getenv("ALERT_EMAIL_FROM")
    sender_password = os.getenv("ALERT_EMAIL_PASS")
    receiver_email = os.getenv("ALERT_EMAIL_TO")

    if not sender_email or not sender_password or not receiver_email:
        print("⚠️ Email credentials missing in .env (Skipping Email Alert)")
        return False

    # Create Email Message
    msg = EmailMessage()
    msg['Subject'] = f"🤖 AI Job Agent: Applied for {title} at {company}"
    msg['From'] = sender_email
    msg['To'] = receiver_email
    
    body_content = (
        f"Hello Ammar,\n\n"
        f"Your AI Job Agent has processed a new vacancy:\n\n"
        f"📌 Job Title: {title}\n"
        f"🏢 Company: {company}\n"
        f"🔗 Job Link: {job_url}\n\n"
        f"Your tailored resume has been generated and auto-filled. "
        f"Find the attached .docx file for your records."
    )
    msg.set_content(body_content)

    # Attach Tailored .docx Resume File
    if docx_path and os.path.exists(docx_path):
        try:
            with open(docx_path, 'rb') as f:
                file_data = f.read()
                file_name = os.path.basename(docx_path)
                
            msg.add_attachment(
                file_data,
                maintype='application',
                subtype='vnd.openxmlformats-officedocument.wordprocessingml.document',
                filename=file_name
            )
        except Exception as e:
            print(f"⚠️ Could not attach file: {e}")

    # Send Email via Gmail SMTP Server
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"✉️ Email receipt sent to {receiver_email} with CV attached!")
        return True
    except Exception as e:
        print(f"❌ Failed to send email alert: {e}")
        return False

if __name__ == "__main__":
    send_telegram_alert("Test Company", "Data Engineer", "https://example.com", None)