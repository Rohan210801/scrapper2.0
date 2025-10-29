import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
from playwright.sync_api import sync_playwright, Playwright, TimeoutError # Import TimeoutError

# --- CONFIGURATION ---

# 1. Email Details (Read securely from GitHub Secrets)
SMTP_SERVER = "smtp.gmail.com"  # Change to "smtp-mail.outlook.com" if needed
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL") 

# 2. Target Details: URL and the specific term to look for on that URL
TARGETS = [
    {
        "url": "https://www.livexscores.com/?p=4&sport=tennis", # In Play page
        "term": "- ret.",
        "type": "Retirement (In Play)"
    },
    {
        "url": "https://www.livexscores.com/?p=2&sport=tennis", # Not Started page
        "term": "- wo.",
        "type": "Walkover (Not Started)"
    }
]

# --- GLOBAL TIMEOUT CONSTANTS (Increased for stability on GitHub Actions) ---
BROWSER_LAUNCH_TIMEOUT = 60000  # 60 seconds to launch the browser
NAVIGATION_TIMEOUT = 60000      # 60 seconds to navigate to a page


# --- EMAIL ALERT FUNCTION ---

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
    Monitors a single page for a specific search term.
    Uses an isolated context (no cookies) for reliability.
    """
    # Create a new, isolated context for every check (acts like a fresh Incognito tab)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Navigate and wait for content (using the increased timeout)
        # We wait until 'domcontentloaded' which is faster than 'networkidle'
        page.goto(target['url'], wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
        
        search_term = target['term']
        
        # --- CRITICAL OPTIMIZATION: Direct DOM Search (CTRL+F Analogy) ---
        # Instead of scraping the whole page, we use a Playwright locator to search the DOM
        # for an element containing the specific text. This is much faster.
        # The locator waits up to 30s (default Playwright wait) for the element to exist.
        
        # We look for ANY element that contains the target search term.
        locator = page.locator(f"//*[contains(text(), '{search_term}')]")

        # Check if the locator finds at least one visible element containing the text.
        if locator.count() > 0:
            
            # Found the term, now try to extract the specific line/text for context.
            # Using evaluate to run JavaScript to get text content is usually faster than inner_text()
            context_text = page.evaluate(f"document.body.innerText.split('\\n').filter(line => line.includes('{search_term}')).join('\\n')")
            
            # Prepare the alert message
            subject = f"ALERT: {target['type']} Detected!"
            body_content = (
                f"Event Type: {target['type']}\n"
                f"URL: {target['url']}\n"
                f"Term Found: '{search_term}'\n"
                f"--- Contextual Line(s) ---\n"
                f"{context_text.strip()}"
            )

            send_email_alert(subject, body_content)
            return True
        else:
            return False

    except TimeoutError:
        print(f"ERROR: Timeout exceeded while loading {target['url']}. (Wait time > {NAVIGATION_TIMEOUT}ms)")
        return False
    except Exception as e:
        print(f"ERROR during Playwright scrape of {target['url']}: {e}")
        return False
    finally:
        # Close the context/page, but keep the main browser open
        context.close()


def main():
    # Loop 6 times to hit a 10-second check frequency (6 * 10s = 60s/minute)
    NUM_CHECKS = 6
    SLEEP_INTERVAL = 10 
    
    # Ensures the necessary browser is installed before starting the loop
    os.system("playwright install chromium")
    
    with sync_playwright() as playwright:
        
        # --- OPTIMIZATION FIX: Launch browser ONCE per job ---
        # We launch the browser with the increased launch timeout.
        browser = playwright.chromium.launch(timeout=BROWSER_LAUNCH_TIMEOUT)
        print(f"--- Browser launched once for the job. ---")
        
        print(f"--- Starting {NUM_CHECKS} checks with a {SLEEP_INTERVAL}-second interval. ---")
        
        for i in range(1, NUM_CHECKS + 1):
            start_time = time.time()
            print(f"\n--- RUN {i}/{NUM_CHECKS} ---")
            
            # Run checks on both target pages in this run window
            for target in TARGETS:
                monitor_page(browser, target)

            end_time = time.time()
            check_duration = end_time - start_time
            
            # Calculate the remaining time to sleep to hit the exact 10-second mark
            time_to_sleep = SLEEP_INTERVAL - check_duration
            
            if time_to_sleep > 0 and i < NUM_CHECKS:
                print(f"Check took {check_duration:.2f} seconds. Sleeping for {time_to_sleep:.2f} seconds...")
                time.sleep(time_to_sleep)
            elif i < NUM_CHECKS:
                 print(f"Check took {check_duration:.2f} seconds. No need to sleep.")

        # --- Close the browser when all checks are done ---
        browser.close()
        print(f"--- Browser closed. All {NUM_CHECKS} runs completed. ---")


if __name__ == "__main__":
    # Wrap main in a try-except to catch high-level errors
    try:
        main()
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
