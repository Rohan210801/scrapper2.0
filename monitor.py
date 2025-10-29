import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
import requests 
from requests_toolbelt import sessions
from bs4 import BeautifulSoup # Used for robust HTML parsing

# --- CONFIGURATION (PRODUCTION SEARCH TERM TEST) ---

# 1. Email Details (Read securely from GitHub Secrets)
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL") 

# 2. Proxy Details (Read securely from GitHub Secrets)
PROXY_HOST = os.environ.get("PROXY_HOST")
PROXY_USER = os.environ.get("PROXY_USER")
PROXY_PASS = os.environ.get("PROXY_PASS")

# 3. Target Details (TESTING MINIMAL PRODUCTION TERM)
TARGETS = [
    {
        "url": "https://www.livexscores.com/?p=4&sport=tennis", 
        "terms": ["- ret."], # Standard monitoring term
        "type": "Retirement (In Play)"
    },
    {
        "url": "https://www.livexscores.com/?p=3&sport=tennis", 
        "terms": ["- ret."], # <--- FINAL TEST: Searching for bare minimum retirement flag
        "type": "Definitive Status (Finished - RET Test)"
    }
]


# --- EMAIL ALERT FUNCTIONS (Unchanged) ---

def send_email_alert(subject, body):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("ERROR: Email credentials missing. Check GitHub Secrets.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = subject
        
        # HTML body for a nice-looking email alert
        html_body = f"""
        <html>
          <body>
            <h2>🚨 LIVE SCORE ALERT: Tennis Event Detected! 🚨</h2>
            <p style="font-size: 16px;">The automated monitoring script has found a matching event:</p>
            <p style="white-space: pre-wrap; font-weight: bold; color: red; background-color: #f7f7f7; padding: 10px; border-radius: 5px;">{body}</p>
            <p><strong>Action Required:</strong> Please check the website immediately for details.</p>
            <a href="{TARGETS[0]['url']}" style="display: inline-block; padding: 10px 20px; color: white; background-color: #007bff; text-decoration: none; border-radius: 5px;">View Live Scores (In Play)</a>
            <hr>
            <p style="font-size: 10px; color: #999;">This alert was generated automatically.</p>
          </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))
        
        print(f"SMTP: Attempting connection to send email...")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            print(f"SMTP SUCCESS: Email queued for delivery for subject: {subject}")
            return True

    except smtplib.SMTPAuthenticationError:
        print("CRITICAL ERROR: SMTP Authentication Failed. (Bad App Password)")
        return False
    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")
        return False


# --- CORE MONITORING LOGIC (Using Proxy + BeautifulSoup) ---

def create_proxied_session():
    """Creates a requests session configured with the proxy credentials."""
    if not all([PROXY_HOST, PROXY_USER, PROXY_PASS]):
        print("CRITICAL PROXY ERROR: Proxy credentials missing. Cannot start proxied session. Falling back to direct connection.")
        return requests.Session() 

    # Construct the authenticated proxy URL
    if PROXY_USER and PROXY_PASS:
        proxy_auth = f"{PROXY_USER}:{PROXY_PASS}@"
    else:
        proxy_auth = ""
        
    proxy_url = f"http://{proxy_auth}{PROXY_HOST}"
    
    # Create a session and set the proxy
    session = requests.Session()
    session.proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }
    return session


def monitor_page(session, target: dict):
    """
    Monitors a single page by fetching the raw HTML and searching using BeautifulSoup.
    """
    clean_url = target['url'].strip()
    
    # Masquerade headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
    }
