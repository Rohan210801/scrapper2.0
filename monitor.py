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


# --- EMAIL ALERT FUNCTIONS ---

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


def send_test_email():
    """Forces a test email to be sent using the configured SMTP details."""
    test_subject = "SUCCESS: Monitoring Email Test"
    test_body = (
        f"This is a test run to confirm your email configuration (App Password, SMTP) is working.\n"
        f"URL 1 (In Play): {TARGETS[0]['url']} is being checked for '{TARGETS[0]['term']}'\n"
        f"URL 2 (Not Started): {TARGETS[1]['url']} is being checked for '{TARGETS[1]['term']}'\n"
        f"\nIf you received this, your email setup is correct. DELETE the call to this function immediately after verifying!"
    )
    send_email_alert(test_subject, test_body)


# --- CORE MONITORING LOGIC ---

def monitor_page(browser, target: dict):
    """
    Monitors a single page for a specific search term.
    Uses an isolated context (no cookies) for reliability.
    """
    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(target['url'], wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
        
        search_term = target['term']
        
        # Optimized search: Looks for any element containing the text
        locator = page.locator(f"//*[contains(text(), '{search_term}')]")

        if locator.count() > 0:
            
            # Extract surrounding text to give context in the email
            context_text = page.evaluate(f"document.body.innerText.split('\\n').filter(line => line.includes('{search_term}')).join('\\n')")
            
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
        context.close()


def main():
    NUM_CHECKS = 6
    SLEEP_INTERVAL = 10 
    
    os.system("playwright install chromium")
    
    with sync_playwright() as playwright:
        
        # Launch browser ONCE per job
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
            
            time_to_sleep = SLEEP_INTERVAL - check_duration
            
            if time_to_sleep > 0 and i < NUM_CHECKS:
                print(f"Check took {check_duration:.2f} seconds. Sleeping for {time_to_sleep:.2f} seconds...")
                time.sleep(time_to_sleep)
            elif i < NUM_CHECKS:
                 print(f"Check took {check_duration:.2f} seconds. No need to sleep.")

        # Close the browser when all checks are done
        browser.close()
        print(f"--- Browser closed. All {NUM_CHECKS} runs completed. ---")


if __name__ == "__main__":
    
    # TEMPORARY TEST: Run this function to verify email sending. 
    # REMOVE this line after testing is successful.
    send_test_email() 
    
    # Run the main monitoring job
    try:
        main()
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
