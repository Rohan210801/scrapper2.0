import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
from playwright.sync_api import sync_playwright, Playwright, TimeoutError
import requests # Still needed for header utility only, but will be bypassed

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
        # FINAL TEST TERM (Forcing test on GBR to confirm detection logic)
        "terms": ["(GBR)"], 
        "type": "Definitive Status (Finished GBR TEST)"
    }
]

# --- GLOBAL TIMEOUT CONSTANTS ---
BROWSER_LAUNCH_TIMEOUT = 60000 
NAVIGATION_TIMEOUT = 60000      
SCORE_TABLE_ROW_SELECTOR = ".tmava" # We'll try to wait for this element


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
    """
    clean_url = target['url'].strip()
    
    # Masquerade headers (Playwright does not automatically send all of these)
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

        # --- Mimic CTRL+F: Read all visible text ---
        page_text = page.locator("body").inner_text()
        found_terms = []
        
        for term in target['terms']:
            if term in page_text:
                
                # Get surrounding context lines (this is now based on rendered text, not raw HTML)
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
    
    NUM_CHECKS = 6
    SLEEP_INTERVAL = 10 
    
    # --- PROXY CONFIGURATION FOR PLAYWRIGHT LAUNCH ---
    if PROXY_USER and PROXY_PASS:
        proxy_server = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"
    else:
        proxy_server = f"http://{PROXY_HOST}"
    
    proxy_config = {"server": proxy_server}
    
    # Ensure Playwright browser binaries are installed
    os.system("playwright install chromium")
    
    print(f"--- Starting FINAL TEST RUN (Playwright/Proxy): {NUM_CHECKS} checks ---")
    
    try:
        with sync_playwright() as playwright:
            
            # Launch browser ONCE, forcing it to use the authenticated proxy
            browser = playwright.chromium.launch(timeout=BROWSER_LAUNCH_TIMEOUT, proxy=proxy_config)
            print(f"--- Browser launched once via proxy: {PROXY_HOST} ---")
            
            for i in range(1, NUM_CHECKS + 1):
                start_time = time.time()
                print(f"\n--- RUN {i}/{NUM_CHECKS} ---")
                
                # We only run the Finished Test page check in this mode
                monitor_page(browser, TARGETS[1]) 

                end_time = time.time()
                check_duration = end_time - start_time
                
                time_to_sleep = SLEEP_INTERVAL - check_duration
                
                if time_to_sleep > 0 and i < NUM_CHECKS:
                    print(f"CYCLE INFO: Sleeping for {time_to_sleep:.2f} seconds...")
                    time.sleep(time_to_sleep)
                elif i < NUM_CHECKS:
                     print(f"CYCLE INFO: Check took {check_duration:.2f}s. No need to sleep.")

            browser.close()
            print(f"--- FINAL TEST RUN COMPLETED. ---")

    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
        print("HINT: If this is a Playwright/Chromium error, ensure you ran 'playwright install chromium'.")
