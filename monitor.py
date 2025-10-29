import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
import requests # Lightweight library replaces Playwright

# --- CONFIGURATION (Production Mode) ---

# 1. Email Details (Read securely from GitHub Secrets)
SMTP_SERVER = "smtp.gmail.com"  
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL") 

# 2. Target Details: Use the simplest possible URLs for raw fetching
TARGETS = [
    {
        # In Play page (Simplified URL)
        "url": "https://www.livexscores.com/?p=4&sport=tennis", 
        "terms": ["- ret."], 
        "type": "Retirement (In Play)"
    },
    {
        # Finished page (Simplified URL)
        "url": "https://www.livexscores.com/?p=3&sport=tennis", 
        "terms": ["- ret.", "- wo."], 
        "type": "Definitive Status (Finished)"
    }
]


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


# --- CORE MONITORING LOGIC (Using simple requests) ---

def monitor_page(target: dict):
    """
    Monitors a single page by fetching the raw HTML and searching the text.
    No headless browser needed, eliminating timeouts.
    """
    clean_url = target['url'].strip()
    
    try:
        # Use a real browser User-Agent to avoid simple blocking
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        # Fetch the raw content of the page
        response = requests.get(clean_url, headers=headers, timeout=10) # 10s timeout on request
        response.raise_for_status() # Raise an error for bad status codes (4xx or 5xx)
        
        # NOTE: This only fetches the HTML before JavaScript executes. 
        # Since JavaScript renders the scores from free.js, we assume the raw HTML contains 
        # a structure we can search OR the data itself is included before rendering.
        page_text = response.text
        
        found_terms = []
        
        # Check for each target term in the raw text
        for term in target['terms']:
            if term in page_text:
                # If found, grab the surrounding text context for the email body
                
                # NOTE: This method is less accurate than Playwright's JS context but is fast and stable.
                context_lines = [line.strip() for line in page_text.split('\n') if term in line]

                found_terms.append({
                    "term": term,
                    "context": "\n".join(context_lines)
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

    except requests.exceptions.RequestException as e:
        # Catch network or timeout errors cleanly
        print(f"ERROR during raw scrape of {clean_url}: {e}")
        return False
    except Exception as e:
        print(f"ERROR during processing of {clean_url}: {e}")
        return False


def main():
    
    # We revert to the 1-minute schedule now that the job is lightweight
    NUM_CHECKS = 6
    SLEEP_INTERVAL = 10 
    
    print(f"--- Starting {NUM_CHECKS} checks with a {SLEEP_INTERVAL}-second target interval using lightweight Requests. ---")
    
    for i in range(1, NUM_CHECKS + 1):
        start_time = time.time()
        print(f"\n--- RUN {i}/{NUM_CHECKS} ---")
        
        for target in TARGETS:
            monitor_page(target) # No browser object needed

        end_time = time.time()
        check_duration = end_time - start_time
        
        time_to_sleep = SLEEP_INTERVAL - check_duration
        
        if time_to_sleep > 0 and i < NUM_CHECKS:
            print(f"Check took {check_duration:.2f} seconds. Sleeping for {time_to_sleep:.2f} seconds...")
            time.sleep(time_to_sleep)
        elif i < NUM_CHECKS:
             print(f"Check took {check_duration:.2f} seconds. No need to sleep.")

    print(f"--- All {NUM_CHECKS} runs completed. ---")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
