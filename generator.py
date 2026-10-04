import os
import base64
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

PLAYLIST_URL = os.environ.get("PLAYLIST_URL")
IP_MANAGER_URL = "https://game.playindia.fun/Jtv/IP.php?id=RiYlIZ"

MAX_CHANNELS = 1000
MAX_WORKERS = 40
OUTPUT_FILE = "rexz.m3u"

def get_robust_session():
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def clear_old_ips(session):
    print("[*] Checking and clearing old IPs from IP Manager...")
    headers = {
        "User-Agent": "Denver1769",
        "Referer": "https://game.playindia.fun/"
    }
    try:
        res = session.get(IP_MANAGER_URL, headers=headers, timeout=10)
        if res.status_code != 200:
            return

        soup = BeautifulSoup(res.text, 'html.parser')
        forms = soup.find_all('form')
        ip_list = []
        for form in forms:
            action_input = form.find('input', {'name': 'action', 'value': 'delete_ip'})
            ip_input = form.find('input', {'name': 'ip'})
            if action_input and ip_input:
                val = ip_input.get('value')
                if val:
                    ip_list.append(val)

        if not ip_list:
            print("[*] No old IPs to delete.")
            return

        def delete_single(ip_val):
            try:
                session.post(
                    IP_MANAGER_URL,
                    data={'action': 'delete_ip', 'ip': ip_val},
                    headers=headers,
                    timeout=5
                )
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=15) as executor:
            list(executor.map(delete_single, ip_list))

        print("[+] All old IPs cleared successfully!\n")
    except Exception as e:
        print(f"[-] Error clearing IPs: {e}")

def b64_to_hex(b64_str):
    padding = 4 - (len(b64_str) % 4)
    if padding < 4:
        b64_str += '=' * padding
    try:
        decoded = base64.urlsafe_b64decode(b64_str)
        return decoded.hex()
    except Exception:
        return b64_str

def resolve_stream_url(url, session, user_agent, is_hotstar, is_sliv):
    if not url:
        return url

    headers = {"User-Agent": user_agent}
    if is_hotstar:
        headers.update({"Origin": "https://www.hotstar.com", "Referer": "https://www.hotstar.com/"})
    elif is_sliv:
        headers.update({"Origin": "https://www.sonyliv.com", "Referer": "https://www.sonyliv.com/"})

    try:
        r = session.get(url, headers=headers, allow_redirects=True, timeout=7)
        if r.status_code == 200:
            lines = r.text.splitlines()
            nested_links = []
            for line in lines:
                s_line = line.strip()
                if "http" in s_line and ("m3u8" in s_line or "mpd" in s_line) and "playindia.fun" not in s_line:
                    idx = s_line.find("http")
                    clean_link = s_line[idx:].split()[0].strip('"\'')
                    nested_links.append(clean_link)

            if nested_links:
                chosen_link = nested_links[-1]
                if not chosen_link.startswith("http"):
                    chosen_link = urljoin(r.url, chosen_link)
                return chosen_link

        if r.url and "playindia.fun" not in r.url:
            resolved_final = r.url
            if not resolved_final.startswith("http"):
                resolved_final = urljoin(url, resolved_final)
            return resolved_final

    except Exception:
        pass

    return url

def process_single_channel(i, lines, session):
    extinf_line = lines[i].strip()

    raw_stream_line = ""
    for f in range(i + 1, min(len(lines), i + 5)):
        candidate = lines[f].strip()
        if candidate.startswith("http"):
            raw_stream_line = candidate.split()[0].rstrip("~")
            break

    lower_text = (extinf_line + raw_stream_line).lower()
    for b in range(max(0, i - 3), min(len(lines), i + 4)):
        lower_text += lines[b].lower()

    is_hotstar = "hotstar" in lower_text or "jhs" in lower_text
    is_sliv = "sliv" in lower_text or "sony" in lower_text or "ten" in lower_text

    channel_lines = [extinf_line]
    formatted_license_key = "null:null"
    user_agent = "Denver1769"

    try:
        key_url = None
        for b in range(max(0, i - 3), i):
            sub_b = lines[b].strip()
            if "inputstream.adaptive.license_key=" in sub_b:
                key_url = sub_b.split("inputstream.adaptive.license_key=")[1].strip().strip('"')

        if is_hotstar:
            user_agent = "Hotstar;in.startv.hotstar/25.02.26.8.11169@Premium Plugx(Android/15)"
        elif is_sliv:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

        for f in range(i + 1, min(len(lines), i + 4)):
            sub_f = lines[f].strip()
            if sub_f.startswith("#EXTVLCOPT:http-user-agent="):
                user_agent = sub_f.split("=")[1].strip()

        if key_url:
            try:
                key_res = session.get(key_url, headers={"User-Agent": user_agent}, timeout=3)
                if key_res.status_code == 200:
                    keys_list = key_res.json().get("base64", {}).get("keys", [])
                    key_pairs = [
                        f"{b64_to_hex(k['kid'])}:{b64_to_hex(k['k'])}"
                        for k in keys_list if "kid" in k and "k" in k
                    ]
                    if key_pairs:
                        formatted_license_key = ",".join(key_pairs)
            except Exception:
                pass

        final_stream_url = raw_stream_line
        if raw_stream_line:
            resolved = resolve_stream_url(raw_stream_line, session, user_agent, is_hotstar, is_sliv)
            if resolved:
                final_stream_url = resolved

        fallback_url = final_stream_url or "http://dummy-link-to-prevent-break"
        is_mpd_link = ".mpd" in fallback_url.lower()

        channel_lines.extend([
            "#KODIPROP:inputstream=inputstream.adaptive",
            f"#KODIPROP:inputstream.adaptive.manifest_type={'mpd' if is_mpd_link else 'hls'}",
            "#KODIPROP:inputstream.adaptive.max_bandwidth=0",
            "#KODIPROP:inputstream.adaptive.stream_selection_type=buffered",
            "#KODIPROP:inputstream.adaptive.buffer_segment_size=1",
            "#KODIPROP:inputstream.adaptive.live_delay=0"
        ])

        if is_hotstar:
            channel_lines.extend([
                "#KODIPROP:inputstream.adaptive.license_type=clearkey",
                f"#KODIPROP:inputstream.adaptive.license_key={formatted_license_key}",
                f"#EXTVLCOPT:http-user-agent={user_agent}",
                "#EXTVLCOPT:http-referrer=https://www.hotstar.com/",
                "#EXTVLCOPT:http-extra-headers=Origin: https://www.hotstar.com"
            ])

            cookie_str = ""
            for check_line in [raw_stream_line] + lines[max(0, i - 2):min(len(lines), i + 3)]:
                if "hdntl=" in check_line:
                    try:
                        for p in check_line.split("hdntl=")[1:]:
                            candidate = p.split()[0].strip('"\'')
                            if "exp=" in candidate:
                                cookie_str = "hdntl=" + candidate.split("&")[0]
                                break
                    except Exception:
                        pass
                if cookie_str:
                    break

            if not cookie_str:
                cookie_str = "hdntl=exp=1790846295~acl=%2f*~id=af9f2444dbd242ba96e15a82e9d5f668~data=hdntl~hmac=85fbbe3fd86f68e27d194b494a1eab8666d65bf230c58a4231acdbc50e3b2caa"

            channel_lines.extend([
                f"#EXTVLCOPT:http-cookie={cookie_str}",
                f'#EXTHTTP:{{"Origin":"https://www.hotstar.com","Referer":"https://www.hotstar.com/","Cookie":"{cookie_str}","Connection":"keep-alive"}}',
                fallback_url
            ])

        elif is_sliv:
            if is_mpd_link:
                channel_lines.extend([
                    "#KODIPROP:inputstream.adaptive.license_type=clearkey",
                    f"#KODIPROP:inputstream.adaptive.license_key={formatted_license_key}"
                ])

            channel_lines.extend([
                f"#EXTVLCOPT:http-user-agent={user_agent}",
                "#EXTVLCOPT:http-referrer=https://www.sonyliv.com/",
                "#EXTVLCOPT:http-extra-headers=Origin: https://www.sonyliv.com",
                '#EXTHTTP:{"Origin":"https://www.sonyliv.com/","Referer":"https://www.sonyliv.com/","Connection":"keep-alive"}',
                fallback_url
            ])

        else:
            channel_lines.extend([
                "#KODIPROP:inputstream.adaptive.license_type=clearkey",
                f"#KODIPROP:inputstream.adaptive.license_key={formatted_license_key}",
                f"#EXTVLCOPT:http-user-agent={user_agent}"
            ])

            jio_cookie = ""
            for check_line in [raw_stream_line] + lines[max(0, i - 2):min(len(lines), i + 3)]:
                if "hdnea=" in check_line:
                    try:
                        for p in check_line.split("hdnea=")[1:]:
                            candidate = p.split()[0].strip('"\'')
                            if "exp=" in candidate or "st=" in candidate:
                                jio_cookie = "hdnea=" + candidate.split("&")[0]
                                break
                    except Exception:
                        pass
                if jio_cookie:
                    break

            if jio_cookie:
                channel_lines.extend([
                    f"#EXTVLCOPT:http-cookie={jio_cookie}",
                    f'#EXTHTTP:{{"Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/","Cookie":"{jio_cookie}","Connection":"keep-alive"}}'
                ])
            else:
                channel_lines.append('#EXTHTTP:{"Origin":"https://www.jiotv.com/","Referer":"https://www.jiotv.com/","Connection":"keep-alive"}')

            channel_lines.append(fallback_url)

    except Exception:
        channel_lines.extend([
            "#KODIPROP:inputstream.adaptive.license_type=clearkey",
            f"#KODIPROP:inputstream.adaptive.license_key={formatted_license_key}",
            f"#EXTVLCOPT:http-user-agent={user_agent}",
            raw_stream_line or "http://dummy-link-to-prevent-break"
        ])

    return channel_lines

def generate_safe_playlist_1000():
    if not PLAYLIST_URL:
        print("[-] PLAYLIST_URL environment variable is missing!")
        return

    session = get_robust_session()
    clear_old_ips(session)

    try:
        print("[*] Fetching playlist source...")
        res = session.get(PLAYLIST_URL, headers={"User-Agent": "Denver1769"}, timeout=30)
        if res.status_code != 200:
            print(f"[-] Failed to fetch playlist: HTTP {res.status_code}")
            return

        lines = res.text.splitlines()
        all_channels = [
            (i, line) for i, line in enumerate(lines)
            if line.strip().startswith("#EXTINF")
        ]

        if not all_channels:
            print("[-] No channels found with #EXTINF tag.")
            return

        target_indices = [item[0] for item in all_channels[:MAX_CHANNELS]]
        print(f"[*] Processing {len(target_indices)} channels cleanly...")

        channel_results = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(process_single_channel, idx, lines, session): idx
                for idx in target_indices
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    res_lines = future.result()
                    if res_lines:
                        channel_results[idx] = res_lines
                except Exception:
                    pass

        new_lines = ["#EXTM3U"]
        for idx in target_indices:
            if idx in channel_results:
                new_lines.extend(channel_results[idx])

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

        print(f"\n[+] Success! Final playlist saved as '{OUTPUT_FILE}'.")

    except Exception as e:
        print(f"\n[-] Critical Error: {e}")

if __name__ == "__main__":
    generate_safe_playlist_1000()
