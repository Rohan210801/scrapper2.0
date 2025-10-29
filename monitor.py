import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
from playwright.sync_api import sync_playwright, Playwright, TimeoutError # Import Playwright utilities

# --- DIAGNOSTIC MODE CONFIGURATION ---
# This configuration is designed to run once, print everything it scrapes, and take a screenshot.

# 1. Email Details (Kept for send_email_alert function, but we won't send an email in this test)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL") 

# 2. Target Details: We will only check the Finished page for a guaranteed term.
TARGETS = [
    {
        "url": "https://www.livexscores.com/?p=3&sport=tennis", # Finished page
        "terms": ["FINISHED", "Finished"], # Search for a guaranteed header text
        "type": "DIAGNOSTIC TEST"
    }
]

# --- GLOBAL TIMEOUT CONSTANTS ---
BROWSER_LAUNCH_TIMEOUT = 60000 
NAVIGATION_TIMEOUT = 60000      
SCORE_TABLE_SELECTOR = "table[width='100%']" 


# --- EMAIL ALERT FUNCTIONS (Unchanged, but not used in main execution) ---
def send_email_alert(subject, body):
    # ... (Email function omitted for brevity, it remains the same) ...
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("ERROR: Email credentials missing. Check GitHub Secrets.")
        return
    # ... (Actual email sending logic remains the same) ...
    # We will skip the implementation here as it is unchanged from your last copy.
    # [Rest of send_email_alert function remains the same]
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

def monitor_page(browser, target: dict, run_index: int):
    """
    DIAGNOSTIC MODE: Captures screenshots and page text for inspection.
    """
    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(target['url'], wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
        page.wait_for_selector(SCORE_TABLE_SELECTOR, timeout=15000)
        
        # 1. Take Screenshot (File will be saved to the runner's workspace)
        screenshot_path = f"screenshot_run_{run_index}.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"DIAGNOSTIC: Screenshot saved as {screenshot_path}. Check the workspace artifacts.")

        # 2. Extract and Print ALL Visible Page Text
        full_page_text = page.locator("body").inner_text()
        print("\n--- DIAGNOSTIC: START OF FULL PAGE TEXT DUMP ---")
        print(full_page_text)
        print("--- DIAGNOSTIC: END OF FULL PAGE TEXT DUMP ---\n")
        
        # 3. Perform standard search for the guaranteed term
        term_found = False
        for term in target['terms']:
            locator = page.locator(f"//*[contains(text(), '{term}')]")
            if locator.count() > 0:
                print(f"DIAGNOSTIC SUCCESS: Guaranteed term '{term}' was found.")
                term_found = True
                break
        
        if not term_found:
             print("DIAGNOSTIC WARNING: Guaranteed search term was NOT found. This suggests a major structural change to the site.")
        
        # IMPORTANT: We are NOT sending an email in this diagnostic test.

    except TimeoutError:
        print(f"ERROR: Scraper timed out waiting for scores table on {target['url']}.")
    except Exception as e:
        print(f"ERROR during Playwright scrape of {target['url']}: {e}")
    finally:
        context.close()


def main(playwright: Playwright):
    
    # We only run ONE CHECK in diagnostic mode
    NUM_CHECKS = 1
    
    # Launch browser ONCE per job
    browser = playwright.chromium.launch(timeout=BROWSER_LAUNCH_TIMEOUT)
    print(f"--- Browser launched once for the job. ---")
    
    # Only run the first check
    monitor_page(browser, TARGETS[0], 1)

    browser.close()
    print(f"--- DIAGNOSTIC RUN COMPLETED. Please check logs and artifacts. ---")


if __name__ == "__main__":
    
    os.system("playwright install chromium")
    
    try:
        with sync_playwright() as playwright:
            main(playwright)
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
