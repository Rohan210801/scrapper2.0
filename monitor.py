import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
# Removed: requests_html (now using Playwright)
from playwright.sync_api import sync_playwright # Use sync for simpler GitHub Actions script
import time
import os 

# --- CONFIGURATION ---

# 1. Email Details (Read securely from GitHub Secrets)
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


# Core logic to scrape and check the page once (NOW USES PLAYWRIGHT)
def run_single_check():
    try:
        # 1. Setup Playwright (guaranteed clean startup/shutdown)
        with sync_playwright() as p:
            # 2. Launch headless Chromium
            browser = p.chromium.launch()
            page = browser.new_page()
            
            # 3. Navigate to the page
            page.goto(URL_TO_MONITOR)
            
            # 4. WAIT for dynamic content (We wait for 5 seconds for safety)
            # The previous r.html.render() functionality is now replaced by this wait.
            time.sleep(5) 
            
            # 5. Extract the entire visible text content of the body
            page_text = page.inner_text('body') 

            browser.close() # Close browser instance

            found_matches = []
            
            for term in SEARCH_TERMS:
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
        # Note: If Playwright itself fails to install, this won't catch it, 
        # but the exit code 100 should now be fixed by the schedule.yml change.
        print(f"An error occurred during monitoring (Playwright): {e}")
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
