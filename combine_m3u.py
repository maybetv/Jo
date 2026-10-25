import os
import re
import requests

OUTPUT = "Zoh.m3u"
MARKER = "# --- LIVE EVENTS ---"
ISL_START_MARKER = "# --- ISL SPECIAL EVENTS ---"
ISL_END_MARKER = "# --- END ISL SPECIAL EVENTS ---"

# മറ്റ് പ്രൊവൈഡർമാരുടെ ലൈവ് ഇവന്റുകൾ ഏറ്റവും താഴെ വേണമെങ്കിൽ True, വേണ്ടെങ്കിൽ False നൽകാം
INCLUDE_OTHER_LIVE_EVENTS = True

PLAYLISTS = {
    "SonyLiv": "https://raw.githubusercontent.com/srhady/SonyLiv/refs/heads/main/sonyliv_playlist.m3u",
    "Fancode": "https://github.com/kajju027/Fancode-Events-Json/raw/refs/heads/main/fc.m3u",
    "Hotstar": "https://github.com/Sflex0719/JH4K/raw/refs/heads/main/JHS.m3u",
    "ICC TV": "https://github.com/doctor-8trange/nexphi0/raw/refs/heads/main/data/icc.m3u",
    "Willow": "https://github.com/srhady/willow-event/raw/refs/heads/main/live_sports.m3u",
    "Prime Video": "https://github.com/srhady/willow-event/raw/refs/heads/main/primevideo_sports.m3u",
    "AxSports": "https://github.com/srhady/axsports/raw/refs/heads/main/playlist.m3u",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_isl_type(block_lines, provider):
    """
    3-ഘട്ട ഫിൽട്ടറിംഗ്:
    1. പ്രൊവൈഡർ SonyLiv ആയിരിക്കണം അല്ലെങ്കിൽ ഡൊമൈൻ/കണ്ടന്റിൽ Sony ഉണ്ടായിരിക്കണം.
    2. ISL / ഫുട്ബോൾ ഇവന്റ് ടാഗുകൾ (ഉദാ: ISL26, footlive, kerala blasters മുതലായവ) കണ്ടെത്തുന്നു.
    3. [MAL], /MAL/ അല്ലെങ്കിൽ [ENG], /ENG/ വഴി മലയാളവും ഇംഗ്ലീഷും കൃത്യമായി വേർതിരിക്കുന്നു.
    """
    full_text = " ".join(block_lines)
    full_lower = full_text.lower()

    # 1. FIRST HINT: Sony ആവണം
    is_sony = (provider.lower() == "sonyliv") or ("sony" in full_lower)
    if not is_sony:
        return None

    # 2. SECOND HINT: ISL / ടീം പേരുകൾ / സ്ട്രീം ടാഗുകൾ (ISL26, footlive മുതലായവ)
    match_keywords = (
        r'\b(isl|isl\d+|indian super league|footlive|kerala blasters|blasters|kbfc|east bengal|mohun bagan|mumbai city|bengaluru fc|chennaiyin|goa|hyderabad|jamshedpur|northeast united|odisha|punjab|churchill brothers)\b'
        r'|കേരള|ബ്ലാസ്റ്റേഴ്സ്'
    )
    if not re.search(match_keywords, full_lower):
        return None

    # 3. THIRD HINT: ലാംഗ്വേജ് കൃത്യമായി ഡിറ്റക്റ്റ് ചെയ്യുന്നു ([MAL], /MAL/ അല്ലെങ്കിൽ [ENG], /ENG/)
    # മലയാളം മുൻഗണന നൽകുന്നു
    if re.search(r'(\bmal\b|\[mal\]|_mal|/mal/|malayalam|മലയാളം)', full_lower):
        return 'Malayalam'
    # ഇംഗ്ലീഷ് ചെക്ക്
    elif re.search(r'(\beng\b|\[eng\]|_eng|/eng/|english|ഇംഗ്ലീഷ്)', full_lower):
        return 'English'

    return None


def clean_previous_isl_block(content):
    """മുൻപ് ചേർത്ത ISL ബ്ലോക്ക് ഫയലിൽ നിന്ന് പൂർണ്ണമായി നീക്കം ചെയ്യുന്നു."""
    pattern = rf"\n*{re.escape(ISL_START_MARKER)}.*?{re.escape(ISL_END_MARKER)}\n*"
    return re.sub(pattern, "\n\n", content, flags=re.DOTALL)


def insert_below_asianet(content, isl_blocks):
    """
    Asianet HD (അല്ലെങ്കിൽ Asianet) ചാനൽ സ്ട്രീം അവസാനിക്കുന്ന വരിക്ക് തൊട്ടുതാഴെ
    മലയാളം ആദ്യം, രണ്ടാമത് ഇംഗ്ലീഷ് എന്ന ക്രമത്തിൽ ഇൻസേർട്ട് ചെയ്യുന്നു.
    മാച്ചുകൾ ഇല്ലെങ്കിൽ ഫയൽ ബ്ലാങ്ക് ആക്കാതെ ക്ലീനായി നിലനിർത്തുന്നു.
    """
    mal_count = len(isl_blocks.get("Malayalam", []))
    eng_count = len(isl_blocks.get("English", []))

    if mal_count == 0 and eng_count == 0:
        return content  # പുതിയ മാച്ചുകൾ ഇല്ലെങ്കിൽ മാറ്റം വരുത്തേണ്ടതില്ല

    # മലയാളം ആദ്യം, തുടർന്ന് ഇംഗ്ലീഷ്
    ordered_isl_items = []
    for block in isl_blocks.get("Malayalam", []):
        ordered_isl_items.append("\n".join(block))
    for block in isl_blocks.get("English", []):
        ordered_isl_items.append("\n".join(block))

    isl_section = f"{ISL_START_MARKER}\n" + "\n\n".join(ordered_isl_items) + f"\n{ISL_END_MARKER}"

    lines = content.splitlines(keepends=True)
    insert_idx = -1
    found_asianet = False

    # 1. ആദ്യം Asianet HD കണ്ടെത്തുന്നു (അതിന്റെ സ്ട്രീം ലിങ്കിന് താഴെ)
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and re.search(r'asianet.*hd', line, re.IGNORECASE):
            found_asianet = True
            continue
        if found_asianet and line.strip().startswith(("http://", "https://")):
            insert_idx = i + 1
            break

    # 2. HD ഇല്ലെങ്കിൽ സാധാരണ Asianet കണ്ടെത്തുന്നു
    if insert_idx == -1:
        found_asianet = False
        for i, line in enumerate(lines):
            if line.startswith("#EXTINF") and re.search(r'asianet', line, re.IGNORECASE):
                found_asianet = True
                continue
            if found_asianet and line.strip().startswith(("http://", "https://")):
                insert_idx = i + 1
                break

    # ഏഷ്യാനെറ്റ് കണ്ടെത്തിയാൽ അതിനു തൊട്ടുതാഴെ വെയ്ക്കുന്നു, ഇല്ലെങ്കിൽ അവസാനം വെയ്ക്കുന്നു
    if insert_idx != -1:
        before = "".join(lines[:insert_idx]).rstrip("\r\n")
        after = "".join(lines[insert_idx:]).lstrip("\r\n")
        return f"{before}\n\n\n{isl_section}\n\n\n{after}"
    else:
        return f"{content.rstrip()}\n\n\n{isl_section}\n\n"


def main():
    isl_blocks = {"Malayalam": [], "English": []}
    live_blocks = []
    seen_urls = set()  # ഡ്യൂപ്ലിക്കേറ്റുകൾ ഒഴിവാക്കാൻ ട്രാക്ക് ചെയ്യുന്നു

    # 1. നിലവിലുള്ള ഫയൽ വായിക്കുന്നു
    base_content = "#EXTM3U\n\n"
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if MARKER in content:
            base_content = content.split(MARKER)[0].rstrip() + "\n\n"
        elif content.strip():
            base_content = content.rstrip() + "\n\n"

    # പഴയ ISL സെക്ഷൻ നീക്കം ചെയ്യുന്നു
    base_content = clean_previous_isl_block(base_content)

    # ബേസ് കണ്ടന്റിലുള്ള സ്റ്റാറ്റിക് സ്ട്രീമുകൾ ശേഖരിക്കുന്നു
    for line in base_content.splitlines():
        line_str = line.strip()
        if line_str.startswith(("http://", "https://")):
            seen_urls.add(line_str)

    # 2. പ്ലേലിസ്റ്റുകൾ ഫെച്ച് ചെയ്ത് പ്രോസസ്സ് ചെയ്യുന്നു
    for provider, url in PLAYLISTS.items():
        print(f"Checking {provider}...")

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()

            lines = response.text.splitlines()
            if lines and lines[0].startswith("#EXTM3U"):
                lines = lines[1:]

            i = 0
            while i < len(lines):
                if not lines[i].startswith("#EXTINF"):
                    i += 1
                    continue

                block = [lines[i]]
                i += 1
                stream = None

                while i < len(lines):
                    line = lines[i]
                    if line.startswith("#EXTINF"):
                        i -= 1
                        break
                    block.append(line)
                    if line.startswith(("http://", "https://")):
                        stream = line.strip()
                        break
                    i += 1

                # സ്ട്രീം ലഭ്യമാണെങ്കിൽ ഒപ്പം നിലവിൽ സീൻ ചെയ്യാത്തതാണെങ്കിൽ മാത്രം പ്രോസസ്സ് ചെയ്യുക (ഡ്യൂപ്ലിക്കേറ്റ് ഒഴിവാക്കൽ)
                if stream and stream not in seen_urls:
                    seen_urls.add(stream)

                    # ISL ഫിൽട്ടർ പരിശോധിക്കുന്നു
                    isl_type = get_isl_type(block, provider)
                    if isl_type:
                        isl_blocks[isl_type].append(block)
                    else:
                        live_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    # 3. Asianet-ന് താഴെ പ്രോപ്പർ ഓർഡറിൽ ചേർക്കുന്നു
    updated_base = insert_below_asianet(base_content, isl_blocks)

    # 4. ഫയൽ സേവ് ചെയ്യുന്നു
    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(updated_base.rstrip() + "\n\n")

        # മറ്റ് ലൈവ് ഇവന്റുകൾ ഏറ്റവും താഴെ ചേർക്കുന്നു (സോഴ്സിൽ ഇല്ലാത്തവ ഓട്ടോമാറ്റിക്കായി ഒഴിവാക്കപ്പെടും)
        if INCLUDE_OTHER_LIVE_EVENTS and live_blocks:
            out.write(f"{MARKER}\n\n")
            out.write("\n\n".join(live_blocks) + "\n\n")

    print(f"\nSuccessfully updated {OUTPUT}!")
    total_isl = len(isl_blocks['Malayalam']) + len(isl_blocks['English'])
    if total_isl > 0:
        print(f"Placed {len(isl_blocks['Malayalam'])} Malayalam and {len(isl_blocks['English'])} English matches below Asianet.")
    else:
        print("No active Sony ISL matches found. File kept clean.")


if __name__ == "__main__":
    main()
