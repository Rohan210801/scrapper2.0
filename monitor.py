import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from requests_html import HTMLSession
import time
import os # New import to access environment variables (secrets)

# --- CONFIGURATION ---

# 1. Email Details (Read securely from GitHub Secrets)
# NOTE: GitHub Actions will inject these values automatically
SMTP_SERVER = "smtp.gmail.com"  # Change to "smtp-mail.outlook.com" if using Outlook/Microsoft
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL") 

# 2. Target Details
URL_TO_MONITOR = "https://www.livexscores.com/free-livescore"
SEARCH_TERMS = ["- wo.", "- ret."]

# Function to send the alert via Email
def send_email_alert(subject, body):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("ERROR: Email credentials missing. Check GitHub Secrets.")
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = subject
        
        html_body = f"""
        <html>
          <body>
            <h2>🚨 LIVE SCORE ALERT: Walkover/Retirement Found! 🚨</h2>
            <p style="font-size: 16px;">The automated monitoring script has detected one of your target phrases on the live scores page.</p>
            <p style="font-weight: bold; color: red;">Detected Message: {body}</p>
            <p><strong>Action Required:</strong> Please check the website immediately for details:</p>
            <p><a href="{URL_TO_MONITOR}">CLICK HERE TO VIEW LIVE SCORES</a></p>
            <hr>
            <p style="font-size: 10px; color: #999;">This alert was generated automatically.</p>
          </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            print("Email alert sent successfully.")

    except smtplib.SMTPAuthenticationError:
        print("ERROR: SMTP Authentication Failed. Check App Password.")
    except Exception as e:
        print(f"An error occurred during email sending: {e}")


# Core logic to scrape and check the page once
def run_single_check():
    try:
        session = HTMLSession()
        r = session.get(URL_TO_MONITOR)
        
        # NOTE: This wait time is crucial for scores to load dynamically.
        r.html.render(timeout=20, sleep=5) 

        page_text = r.html.text
        found_matches = []
        
        for term in SEARCH_TERMS:
            # We are checking if the entire phrase is present anywhere in the page text
            if term in page_text:
                found_matches.append(term)
        
        if found_matches:
            body_content = ", ".join(found_matches)
            subject = f"ALERT: Walkover/Retirement Found ({body_content})"
            send_email_alert(subject, body_content)
            return True # Indicates an alert was sent
        else:
            return False # No alert sent

    except Exception as e:
        print(f"An error occurred during monitoring: {e}")
        return False


if __name__ == "__main__":
    
    # Check 1: Runs immediately when the Action starts
    alert_sent_1 = run_single_check()
    print(f"--- Check 1 finished. Alert sent: {alert_sent_1} ---")
    
    # DELAY: Wait 30 seconds to hit the 30-second target interval
    time.sleep(30)
    
    # Check 2: Runs 30 seconds later
    alert_sent_2 = run_single_check()
    print(f"--- Check 2 finished. Alert sent: {alert_sent_2} ---")
    
    # The job finishes, and the next scheduled run starts in ~30 seconds later.
