import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
import asyncio
from playwright.sync_api import sync_playwright, Playwright

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
        "url": "https://www.livexscores.com/?p=4&sport=tennis", # UPDATED URL: In Play
        "term": "- ret.",
        "type": "Retirement (In Play)"
    },
    {
        "url": "https://www.livexscores.com/?p=2&sport=tennis", # UPDATED URL: Not Started
        "term": "- wo.",
        "type": "Walkover (Not Started)"
    }
]

# --- EMAIL ALERT FUNCTION (Unchanged) ---

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
            <p style="font-weight: bold; color: red;">{body}</p>
            <p><strong>Action Required:</strong> Please check the website immediately for details.</p>
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

def monitor_page(playwright: Playwright, target: dict):
    # Use Chromium for the headless browser
    # NOTE on Cookies: Creating a new browser and context for every check 
    # ensures a fresh session with no accumulated cookies, preventing site crashes.
    browser = playwright.chromium.launch() 
    context = browser.new_context()
    page = context.new_page()

    try:
        # Navigate to the target URL
        page.goto(target['url'], wait_until="networkidle")
        
        # Wait a few extra seconds for dynamic JavaScript content to load
        # This 3-second delay is crucial for the content to appear
        page.wait_for_timeout(3000) 
        
        # Get the full text content of the page body
        page_text = page.locator('body').inner_text()
        
        search_term = target['term']
        
        if search_term in page_text:
            
            # Extract the surrounding lines for context
            context_lines = [line.strip() for line in page_text.split('\n') if search_term in line]
            
            # Prepare the alert message
            subject = f"ALERT: {target['type']} Detected!"
            body_content = (
                f"Event Type: {target['type']}\n"
                f"URL: {target['url']}\n"
                f"Term Found: '{search_term}'\n"
                f"--- Context (Line contains):\n"
                f"{' | '.join(context_lines) if context_lines else 'Could not retrieve line context.'}"
            )

            send_email_alert(subject, body_content)
            return True
        else:
            return False

    except Exception as e:
        print(f"ERROR during Playwright scrape of {target['url']}: {e}")
        return False
    finally:
        # Ensure the browser is closed to free up resources
        browser.close()


def main():
    # Number of checks to run within the 60-second window
    NUM_CHECKS = 6
    SLEEP_INTERVAL = 10 
    
    with sync_playwright() as playwright:
        
        print(f"--- Starting {NUM_CHECKS} checks with a {SLEEP_INTERVAL}-second interval. ---")
        
        for i in range(1, NUM_CHECKS + 1):
            start_time = time.time()
            print(f"\n--- RUN {i}/{NUM_CHECKS} ---")
            
            # Run checks on both pages
            for target in TARGETS:
                monitor_page(playwright, target)

            end_time = time.time()
            check_duration = end_time - start_time
            
            # Calculate the remaining time to sleep to hit the exact 10-second mark
            time_to_sleep = SLEEP_INTERVAL - check_duration
            
            if time_to_sleep > 0 and i < NUM_CHECKS:
                print(f"Check took {check_duration:.2f} seconds. Sleeping for {time_to_sleep:.2f} seconds...")
                time.sleep(time_to_sleep)
            elif i < NUM_CHECKS:
                 print(f"Check took {check_duration:.2f} seconds. No need to sleep.")

    print("\n--- Job finished. Waiting for next scheduled run. ---")


if __name__ == "__main__":
    # Wrap main in a try-except to catch high-level errors
    try:
        main()
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
