import smtplib
import time
import os
import requests 
import json
from requests_toolbelt import sessions
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- AI AGENT ORCHESTRATOR CONFIGURATION ---

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

# 3. AI/Target URLs
GEMINI_MODEL = "gemini-2.5-flash-preview-09-2025"
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key="
FINISHED_SCORES_URL = "https://www.livexscores.com/paid.php?p=3&sport=tennis-lsh&style=xxeee,x425d3a,x000,xaaa,xc00,x425d3a,xfff,xddd,xc00,verdana,11,xeee,xfff,xeee,NaN,xc00&timezone=+0"
TARGET_TYPE = "Definitive Status (Finished)"

# --- HELPER FUNCTIONS ---

def create_proxied_session():
    """Creates a requests session configured with the proxy credentials."""
    if not all([PROXY_HOST, PROXY_USER, PROXY_PASS]):
        print("CRITICAL PROXY ERROR: Proxy credentials missing. Cannot start proxied session.")
        return requests.Session() 

    if PROXY_USER and PROXY_PASS:
        proxy_auth = f"{PROXY_USER}:{PROXY_PASS}@"
    else:
        proxy_auth = ""
        
    proxy_url = f"http://{proxy_auth}{PROXY_HOST}"
    
    session = requests.Session()
    session.proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }
    return session

def send_email_alert(subject, body, status_url):
    # This is slightly simplified since it's just the final alert
    if not all([SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL]):
        print("ERROR: Email credentials missing. Cannot send alert.")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg['Subject'] = subject
        
        html_body = f"""
        <html>
          <body>
            <h2>🚨 AI ALERT: Confirmed Walkover or Retirement! 🚨</h2>
            <p style="font-size: 16px;">The AI Agent detected the following event(s) in the score feed:</p>
            <pre style="white-space: pre-wrap; font-weight: bold; color: red; background-color: #f7f7f7; padding: 15px; border-radius: 5px;">{body}</pre>
            <p><strong>Action Required:</strong> Check the source page immediately:</p>
            <a href="{status_url}" style="display: inline-block; padding: 10px 20px; color: white; background-color: #007bff; text-decoration: none; border-radius: 5px;">View Finished Scores</a>
            <hr>
            <p style="font-size: 10px; color: #999;">Detection powered by Google Gemini AI.</p>
          </body>
        </html>
        """
        msg.attach(MIMEText(html_body, 'html'))
        
        with smtplib.SMTP(SMTP_SERVER, 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            print(f"SMTP SUCCESS: AI Alert queued for delivery.")
            return True

    except Exception as e:
        print(f"ERROR: Failed to send email: {e}")
        return False

def call_gemini_agent(raw_html_content):
    """Sends the raw HTML content to Gemini for analysis and structured extraction."""

    system_prompt = (
        "You are an expert sports data analyzer. Your task is to extract information about tennis matches "
        "from the provided raw HTML source code. Only identify matches that explicitly show a status of "
        "'retirement' (ret.) or 'walkover' (w.o. or wo.). "
        "Return the result as a single JSON array following the provided schema. "
        "If no matches fit the criteria, return an empty array: []. "
        "For each match found, extract the match name (e.g., Player A vs Player B), the final score, and the exact status tag."
    )
    
    # We send a small snippet of the HTML to keep the token usage low
    searchable_content = raw_html_content[raw_html_content.find('<tbody>'):raw_html_content.rfind('</tbody>')]

    user_query = f"Analyze the following raw HTML score table data and extract only matches with status 'ret.' or 'wo.'. Data: {searchable_content}"

    # Define the required output structure
    response_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "match": {"type": "STRING", "description": "Names of players in the match (e.g., Smith vs Jones)"},
                "status": {"type": "STRING", "description": "The status found: 'Retirement' or 'Walkover'"},
                "score": {"type": "STRING", "description": "The scoreline, including the status tag."}
            },
            "required": ["match", "status", "score"]
        }
    }

    # Construct the API payload
    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        },
    }

    try:
        # NOTE: The API key must be provided by the environment, which is handled implicitly by the Canvas system.
        response = requests.post(
            GEMINI_API_URL,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(payload),
            timeout=30 # Increased timeout for AI processing
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Extract the JSON string from the response
        json_string = result['candidates'][0]['content']['parts'][0]['text']
        
        # Return the parsed Python list/array
        return json.loads(json_string)

    except Exception as e:
        print(f"GEMINI API ERROR: Failed to process data or receive JSON: {e}")
        # Return empty list on failure to prevent accidental alert sending
        return []

def monitor_agent_run(session):
    """Orchestrates the scraping and AI analysis."""
    
    # --- STEP 1: FETCH DATA VIA PROXY ---
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html',
        }
        
        print(f"NETWORK: Fetching data from {TARGET_TYPE} source...")
        response = session.get(FINISHED_SCORES_URL, headers=headers, timeout=15)
        response.raise_for_status() 
        raw_html_content = response.text
        
        # --- STEP 2: ANALYZE DATA WITH GEMINI ---
        print("AI AGENT: Sending raw HTML content to Gemini for analysis...")
        
        matches_found = call_gemini_agent(raw_html_content)
        
        if matches_found:
            print(f"AI SUCCESS: Agent found {len(matches_found)} relevant events.")
            
            # Format the output nicely for the email body
            email_body = json.dumps(matches_found, indent=2)
            subject = f"🚨 AI ALERT: {len(matches_found)} Walkover/Retirement Event(s) Detected!"
            
            # --- STEP 3: SEND ALERT ---
            send_email_alert(subject, email_body, FINISHED_SCORES_URL)
            return True
        else:
            print("AI FAILURE: Agent found no retirements or walkovers.")
            return False

    except requests.exceptions.RequestException as e:
        print(f"NETWORK ERROR: Failed to fetch source URL: {e}")
        return False
    except Exception as e:
        print(f"PROCESSING ERROR: during main monitor loop: {e}")
        return False


def main():
    
    NUM_CHECKS = 6
    SLEEP_INTERVAL = 10 
    
    session = create_proxied_session()
    
    print(f"--- Starting AI AGENT MONITORING RUN: {NUM_CHECKS} checks ---")
    
    for i in range(1, NUM_CHECKS + 1):
        start_time = time.time()
        print(f"\n--- RUN {i}/{NUM_CHECKS} ---")
        
        # Run the AI agent monitoring
        monitor_agent_run(session)

        end_time = time.time()
        check_duration = end_time - start_time
        
        time_to_sleep = SLEEP_INTERVAL - check_duration
        
        if time_to_sleep > 0 and i < NUM_CHECKS:
            print(f"CYCLE INFO: Sleeping for {time_to_sleep:.2f} seconds...")
            time.sleep(time_to_sleep)
        elif i < NUM_CHECKS:
             print(f"CYCLE INFO: Check took {check_duration:.2f}s. No need to sleep.")

    print(f"--- AI AGENT MONITORING RUN COMPLETED. ---")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL SCRIPT ERROR: {e}")
