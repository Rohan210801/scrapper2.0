import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
import requests 
from requests_toolbelt import sessions
from bs4 import BeautifulSoup 

# --- CONFIGURATION (FINAL VALIDATION TEST - DIRECT ACCESS) ---

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

# 3. Target Details (VALIDATION TERMS)
TARGETS = [
    {
        # Direct Live In-Play data source URL (p=4)
        "url": "https://www.livexscores.com/paid.php?p=4&sport=tennis-lsh&style=xxeee,x425d3a,x000,xaaa,xc00,x425d3a,xfff,xddd,xc00,verdana,11,xeee,xfff,xeee,NaN,xc00&timezone=+0", 
        "terms": ["- ret."], 
        "type": "Retirement (In Play)"
    },
    {
        # Direct Finished data source URL (p=3)
        "url": "https://www.livexscores.com/paid.php?p=3&sport=tennis-lsh&style=xxeee,x425d3a,x000,xaaa,xc00,x425d3a,xfff,xddd,xc00,verdana,11,xeee,xfff,xeee,NaN,xc00&timezone=+0", 
        # FINAL TEST: Search for a guaranteed country code (GBR)
        "terms": ["GBR"], 
        "type": "Definitive Status (Finished GBR TEST)"
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
            <a href="{TARGETS[0]['url']}" style="display: inline-block; padding: 10px 20px; color: white; background-color: #007bff; text-decoration: none; border-radius: 5px;">View Live Scores</a>
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
    Fetches the content from the stable data source URL directly and searches using BS4.
    """
    # The URL is pulled directly from the target dictionary now
    clean_url = target['url'].strip() 
    
    # Masquerade headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
    }
    
    try:
        # --- Fetch the Raw Content of the IFRAME URL Directly ---
        print(f"NETWORK: Fetching {target['type']} data from {clean_url}...")
        
        response_data = session.get(clean_url, headers=headers, timeout=15)
        response_data.raise_for_status()
        
        # 2. Parse the content with BeautifulSoup
        soup_data = BeautifulSoup(response_data.text, 'html.parser')
        
        found_terms = []
        
        # 3. Search for each term using the precise BeautifulSoup structure
        for term in target['terms']:
            
            # Use find_all(string=True) to grab all text nodes in the document
            all_text_nodes = soup_data.find_all(string=True)
            
            # Filter the text nodes to find lines that contain the target term
            matching_lines = [
                node.strip() for node in all_text_nodes 
                if term in node 
                and len(node.strip()) > 5 # Ignore small, junk matches
            ]

            if matching_lines:
                found_terms.append({
                    "term": term,
                    # Join the unique matching lines found by BS4
                    "context": "\n".join(matching_lines) 
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

    except requests.exceptions.RequestException as e:
        print(f"NETWORK ERROR: Failed to fetch data source: {e}")
        return False
    except Exception as e:
        print(f"PROCESSING ERROR: during {target['type']} processing: {e}")
        return False


def main():
    
    NUM_CHECKS = 6
    SLEEP_INTERVAL = 10 
    
    # Create the proxied session ONCE
    session = create_proxied_session()
    
    print(f"--- Starting FINAL VALIDATION TEST (Direct Access): {NUM_CHECKS} checks for '(GBR)' ---")
    
    for i in range(1, NUM_CHECKS + 1):
        start_time = time.time()
        print(f"\n--- RUN {i}/{NUM_CHECKS} ---")
        
        # We only run the Finished Test page check in this mode
        monitor_page(session, TARGETS[1]) 

        end_time = time.time()
        check_duration = end_time - start_time
        
        time_to_sleep = SLEEP_INTERVAL - check_duration
        
        if time_to_sleep > 0 and i < NUM_CHECKS:
            print(f"CYCLE INFO: Sleeping for {time_to_sleep:.2f} seconds...")
            time.sleep(time_to_sleep)
        elif i < NUM_CHECKS:
             print(f"CYCLE INFO: Check took {check_duration:.2f}s. No need to sleep.")

    print(f"--- FINAL VALIDATION TEST COMPLETED. ---")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
