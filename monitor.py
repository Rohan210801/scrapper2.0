import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
from playwright.sync_api import sync_playwright, Playwright, TimeoutError
import requests 

# --- CONFIGURATION (FINAL PRODUCTION MODE - PLAYWRIGHT) ---

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

# 3. Target Details (FINAL PRODUCTION SEARCH TERMS)
TARGETS = [
    {
        "url": "https://www.livexscores.com/?p=4&sport=tennis", 
        "terms": ["- ret."], 
        "type": "Retirement (In Play)"
    },
    {
        "url": "https://www.livexscores.com/?p=3&sport=tennis", 
        # TEST TERM: Searching for the most reliable country code for testing detection logic
        "terms": ["(GBR)"], 
        "type": "Definitive Status (Finished GBR TEST)"
    }
]

# --- GLOBAL TIMEOUT CONSTANTS ---
BROWSER_LAUNCH_TIMEOUT = 60000 
NAVIGATION_TIMEOUT = 60000      
SCORE_TABLE_ROW_SELECTOR = ".tmava" # Element we wait for


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


# --- CORE MONITORING LOGIC (Playwright + Proxy) ---

def monitor_page(browser, target: dict):
    """
    Monitors a single page using the Playwright headless browser forced to use the proxy.
    Includes diagnostic text dump.
    """
    clean_url = target['url'].strip()
    
    # Masquerade headers (Playwright)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    context = browser.new_context(user_agent=headers['User-Agent'])
    page = context.new_page()

    try:
        print(f"BROWSER: Navigating to {target['type']} data from {clean_url} via proxy...")
        
        page.goto(clean_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
        
        # Wait for a reliable score element after JS has executed
        page.wait_for_selector(SCORE_TABLE_ROW_SELECTOR, timeout=20000) 
        print(f"BROWSER SUCCESS: Score table rendered.")

        # --- DIAGNOSTIC STEP: DUMP ALL RENDERED TEXT ---
        page_text = page.locator("body").inner_text()
        print("\n--- RAW RENDERED PAGE TEXT DUMP START ---")
        print(page_text)
        print("--- RAW RENDERED PAGE TEXT DUMP END ---")
        
        found_terms = []
        
        # --- DETECTION LOGIC ---
        for term in target['terms']:
            if term in page_text:
                
                # Get surrounding context lines (this is based on rendered text)
                context_lines = [line.strip() for line in page_text.split('\n') if term in line]

                found_terms.append({
                    "term": term,
                    "context": "\n".join(context_lines)
                })
        
        if found_terms:
            print(f"DETECTION SUCCESS: Found required term(s) in {target['type']} page.")
            
            email_body = ""
            subject_terms = []
            
            for item in found_terms:
                subject_terms.append(item['term'])
                email_body += (
                    f"--- Status Found: {item['term']} ---\n"
                    f"Contextual Line(s) from Page:\n"
                    f"{item['context']}\n\n"
                )

            subject = f"ALERT: {target['type']} - Status Detected: {', '.join(subject_terms)}"
            
            send_email_alert(subject, email_body)
            return True
        else:
            print(f"DETECTION FAILURE: No targets found in {target['type']} page.")
            return False

    except TimeoutError:
        print(f"BROWSER TIMEOUT ERROR: Scraper timed out waiting for content on {clean_url}.")
        return False
    except Exception as e:
        print(f"PROCESSING ERROR: during {target['type']} processing: {e}")
        return False
    finally:
        context.close()


def main():
    
    NUM_CHECKS = 1 # Only one check for debugging speed
    SLEEP_INTERVAL = 10 
    
    # --- PROXY CONFIGURATION FOR PLAYWRIGHT LAUNCH ---
    if PROXY_USER and PROXY_PASS:
        proxy_server = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"
    else:
        proxy_server = f"http://{PROXY_HOST}"
    
    proxy_config = {"server": proxy_server}
    
    # Ensure Playwright browser binaries are installed
    os.system("playwright install chromium")
    
    print(f"--- Starting DEBUG RUN (Playwright/Proxy): DUMPING RENDERED CONTENT ---")
    
    try:
        with sync_playwright() as playwright:
            
            # Launch browser ONCE, forcing it to use the authenticated proxy
            browser = playwright.chromium.launch(timeout=BROWSER_LAUNCH_TIMEOUT, proxy=proxy_config)
            print(f"--- Browser launched once via proxy: {PROXY_HOST} ---")
            
            # Run only one check for debug
            monitor_page(browser, TARGETS[1]) 

            browser.close()
            print(f"--- DEBUG RUN COMPLETED. Review the 'RAW RENDERED PAGE TEXT DUMP' above. ---")

    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
        print("HINT: Fatal error occurred during setup or teardown.")
