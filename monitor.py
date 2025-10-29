import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
from playwright.sync_api import sync_playwright, Playwright, TimeoutError # Import Playwright utilities

# --- CONFIGURATION (Production Mode) ---

# 1. Email Details (Read securely from GitHub Secrets)
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL") 

# 2. Target Details: URL and the specific term(s) to look for on that URL
# FINAL FIX: Use the stable, direct iframe source URLs instead of the dynamic parent page.
TARGETS = [
    {
        # Direct URL for In Play (p=4 in old link, likely default_site=4 here)
        "url": "https://www.livexscores.com/free.php?sport=tennis&default_site=4&iframe_width=1200&iframe_height=1000", 
        "terms": ["- ret."], 
        "type": "Retirement (In Play)"
    },
    {
        # Direct URL for Finished (p=3 in old link, likely default_site=3 here)
        "url": "https://www.livexscores.com/free.php?sport=tennis&default_site=3&iframe_width=1200&iframe_height=1000", 
        "terms": ["- ret.", "- wo."], 
        "type": "Definitive Status (Finished)"
    }
]

# --- GLOBAL TIMEOUT CONSTANTS ---
BROWSER_LAUNCH_TIMEOUT = 60000 
NAVIGATION_TIMEOUT = 60000      
# NEW: Wait for the simplest common element class to confirm data presence
SCORE_TABLE_ROW_SELECTOR = ".tmava" 


# --- EMAIL ALERT FUNCTIONS (Unchanged) ---
def send_email_alert(subject, body):
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("ERROR: Email credentials missing. Check GitHub Secrets.")
        return

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
        
        # Connect to the SMTP server and send
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            print(f"Email alert sent successfully for: {subject}")

    except smtplib.SMTPAuthenticationError:
        print("CRITICAL ERROR: SMTP Authentication Failed. Check App Password/Sender Email.")
    except Exception as e:
        print(f"An error occurred during email sending: {e}")


# --- CORE MONITORING LOGIC ---

def monitor_page(browser, target: dict):
    """
    Monitors a single page for a list of specific search terms.
    Uses direct scrape of the iframe source URL for stability.
    """
    context = browser.new_context()
    page = context.new_page()

    try:
        # Clean the URL string before navigation
        clean_url = target['url'].strip()
        
        # We expect a much faster load time here as this is likely just the iframe HTML
        page.goto(clean_url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
        print(f"Attempting to load direct source URL: {clean_url}")
        
        # Wait for a reliable element *inside* the iframe source (the dark row class)
        page.wait_for_selector(SCORE_TABLE_ROW_SELECTOR, timeout=20000) 
        print(f"Loaded and verified score rows for {target['type']}.")
        
        found_terms = []
        
        # Check for each target term using optimized XPath search
        for term in target['terms']:
            
            # XPath locator finds any visible element containing the search text
            locator = page.locator(f"//*[contains(text(), '{term}')]")

            if locator.count() > 0:
                # If found, grab the surrounding text context for the email body
                
                context_text = page.evaluate(f"""
                    document.body.innerText
                        .split('\\n')
                        .filter(line => line.includes('{term}'))
                        .join('\\n')
                """)
                
                found_terms.append({
                    "term": term,
                    "context": context_text.strip()
                })
        
        if found_terms:
            # Consolidate all found terms into a single email
            
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
            return False

    except TimeoutError:
        print(f"ERROR: Scraper timed out waiting for score rows on {clean_url}. (Wait time > 20s)")
        return False
    except Exception as e:
        print(f"ERROR during Playwright scrape of {clean_url}: {e}")
        return False
    finally:
        context.close()


def main(playwright: Playwright):
    
    NUM_CHECKS = 30
    SLEEP_INTERVAL = 10 
    
    
    browser = playwright.chromium.launch(timeout=BROWSER_LAUNCH_TIMEOUT)
    print(f"--- Browser launched once for the job. ---")
    
    print(f"--- Starting {NUM_CHECKS} checks with a {SLEEP_INTERVAL}-second target interval. ---")
    
    for i in range(1, NUM_CHECKS + 1):
        start_time = time.time()
        print(f"\n--- RUN {i}/{NUM_CHECKS} ---")
        
        for target in TARGETS:
            monitor_page(browser, target)

        end_time = time.time()
        check_duration = end_time - start_time
        
        time_to_sleep = SLEEP_INTERVAL - check_duration
        
        if time_to_sleep > 0 and i < NUM_CHECKS:
            print(f"Check took {check_duration:.2f} seconds. Sleeping for {time_to_sleep:.2f} seconds...")
            time.sleep(time_to_sleep)
        elif i < NUM_CHECKS:
             print(f"Check took {check_duration:.2f} seconds. No need to sleep.")

    browser.close()
    print(f"--- Browser closed. All {NUM_CHECKS} runs completed. ---")


if __name__ == "__main__":
    
    os.system("playwright install chromium")
    
    try:
        with sync_playwright() as playwright:
            main(playwright)
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
