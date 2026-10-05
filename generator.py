import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

PLAYLIST_URL = os.environ.get("PLAYLIST_URL", "").strip()
IP_MANAGER_URL = "https://game.playindia.fun/Jtv/IP.php?id=RiYlIZ"
OUTPUT_DIR = "playlist"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "Rexz.m3u")

def get_robust_session():
    session = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session

def clear_old_ips(session):
    print("[*] Checking and clearing old IPs from IP Manager...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Referer": "https://game.playindia.fun/"
    }
    try:
        res = session.get(IP_MANAGER_URL, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            forms = soup.find_all('form')
            ip_list = []
            for form in forms:
                action_input = form.find('input', {'name': 'action', 'value': 'delete_ip'})
                ip_input = form.find('input', {'name': 'ip'})
                if action_input and ip_input:
                    ip_list.append(ip_input.get('value'))
            for ip_val in ip_list:
                try:
                    session.post(IP_MANAGER_URL, data={'action': 'delete_ip', 'ip': ip_val}, headers=headers, timeout=5)
                except Exception:
                    pass
            print(f"[+] Cleared {len(ip_list)} old IP(s) successfully!\n")
    except Exception as e:
        print(f"[-] IP Manager check failed (continuing anyway): {e}")

def fetch_and_save_complete_playlist():
    if not PLAYLIST_URL:
        raise ValueError("PLAYLIST_URL secret is empty or missing! Please add it in GitHub Secrets.")

    session = get_robust_session()
    clear_old_ips(session)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    print(f"[*] Downloading complete data from source...")
    res = session.get(PLAYLIST_URL, headers=headers, timeout=30)
    
    if res.status_code != 200:
        raise RuntimeError(f"Failed to fetch source link. HTTP Status: {res.status_code}")

    content = res.text.strip()
    
    # Check if the content is empty
    if not content:
        raise RuntimeError("Source returned empty data!")

    # Check if source content is wrapped in HTML body/pre tag
    if "<pre>" in content and "</pre>" in content:
        content = content.split("<pre>")[1].split("</pre>")[0].strip()

    # Create target directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Save complete original content directly to the new folder
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[+] Success! Complete A-Z data saved to '{OUTPUT_FILE}'. Size: {len(content)} bytes.")

if __name__ == "__main__":
    fetch_and_save_complete_playlist()
