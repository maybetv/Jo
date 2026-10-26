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
    full_text = " ".join(block_lines)
    full_lower = full_text.lower()

    is_sony = (provider.lower() == "sonyliv") or ("sony" in full_lower)
    if not is_sony:
        return None

    match_keywords = (
        r'\b(isl|isl\d+|indian super league|footlive|kerala blasters|blasters|kbfc|east bengal|mohun bagan|mumbai city|bengaluru fc|chennaiyin|goa|hyderabad|jamshedpur|northeast united|odisha|punjab|churchill brothers)\b'
        r'|കേരള|ബ്ലാസ്റ്റേഴ്സ്'
    )
    if not re.search(match_keywords, full_lower):
        return None

    if re.search(r'(\bmal\b|\[mal\]|_mal|/mal/|malayalam|മലയാളം)', full_lower):
        return 'Malayalam'
    elif re.search(r'(\beng\b|\[eng\]|_eng|/eng/|english|ഇംഗ്ലീഷ്)', full_lower):
        return 'English'

    return None


def clean_previous_isl_block(content):
    """ഫയലിൽ നിലനിൽക്കുന്ന പഴയ എല്ലാ ISL സ്റ്റാർട്ട്/എൻഡ് ബ്ലോക്കുകളും പൂർണ്ണമായി നീക്കം ചെയ്യുന്നു."""
    pattern = rf"\n*{re.escape(ISL_START_MARKER)}.*?{re.escape(ISL_END_MARKER)}\n*"
    while re.search(pattern, content, flags=re.DOTALL):
        content = re.sub(pattern, "\n\n", content, flags=re.DOTALL)
    return content


def insert_below_asianet(content, isl_blocks):
    eng_count = len(isl_blocks.get("English", []))
    mal_count = len(isl_blocks.get("Malayalam", []))

    if eng_count == 0 and mal_count == 0:
        return content

    # ആദ്യം ഇംഗ്ലീഷ്, തുടർന്ന് മലയാളം എന്ന ക്രമത്തിൽ ലിങ്കുകൾ അടുക്കുന്നു
    ordered_isl_items = []
    for block in isl_blocks.get("English", []):
        ordered_isl_items.append("\n".join(block))
    for block in isl_blocks.get("Malayalam", []):
        ordered_isl_items.append("\n".join(block))

    # എല്ലാ ISL ലിങ്കുകൾക്കും ഒടുവിൽ ഒരൊറ്റ പ്രാവശ്യം മാത്രം സ്റ്റാർട്ടും എൻഡും വരുന്ന രീതി
    isl_section = f"{ISL_START_MARKER}\n\n" + "\n\n\n".join(ordered_isl_items) + f"\n\n{ISL_END_MARKER}"

    lines = content.splitlines(keepends=True)
    insert_idx = -1
    found_asianet = False

    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and re.search(r'asianet.*hd', line, re.IGNORECASE):
            found_asianet = True
            continue
        if found_asianet and line.strip().startswith(("http://", "https://")):
            insert_idx = i + 1
            break

    if insert_idx == -1:
        found_asianet = False
        for i, line in enumerate(lines):
            if line.startswith("#EXTINF") and re.search(r'asianet', line, re.IGNORECASE):
                found_asianet = True
                continue
            if found_asianet and line.strip().startswith(("http://", "https://")):
                insert_idx = i + 1
                break

    if insert_idx != -1:
        before = "".join(lines[:insert_idx]).rstrip("\r\n")
        after = "".join(lines[insert_idx:]).lstrip("\r\n")
        return f"{before}\n\n\n{isl_section}\n\n\n{after}"
    else:
        return f"{content.rstrip()}\n\n\n{isl_section}\n\n"


def main():
    isl_blocks = {"Malayalam": [], "English": []}
    live_blocks = []
    seen_urls = set()

    # 1. നിലവിലുള്ള ഫയൽ റീഡ് ചെയ്യുന്നു
    base_content = "#EXTM3U\n\n"
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if MARKER in content:
            base_content = content.split(MARKER)[0].rstrip() + "\n\n"
        elif content.strip():
            base_content = content.strip() + "\n\n"

    # പഴയ ISL സെക്ഷനുകൾ പൂർണ്ണമായി ഒഴിവാക്കുന്നു
    base_content = clean_previous_isl_block(base_content)

    # 2. സോഴ്സ് പ്ലേലിസ്റ്റുകൾ ഫെച്ച് ചെയ്ത് പ്രോസസ്സ് ചെയ്യുന്നു
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

                if stream and stream not in seen_urls:
                    seen_urls.add(stream)

                    isl_type = get_isl_type(block, provider)
                    if isl_type:
                        isl_blocks[isl_type].append(block)
                    else:
                        live_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    # 3. Asianet-ന് താഴെ ഒറ്റ ബ്ലോക്കായി ISL മാച്ചുകൾ ചേർക്കുന്നു
    updated_base = insert_below_asianet(base_content, isl_blocks)

    # 4. ഫയൽ സേവ് ചെയ്യുന്നു
    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(updated_base.rstrip() + "\n\n")

        if INCLUDE_OTHER_LIVE_EVENTS and live_blocks:
            out.write(f"{MARKER}\n\n")
            out.write("\n\n".join(live_blocks) + "\n\n")

    print(f"\nSuccessfully updated {OUTPUT}!")
    total_isl = len(isl_blocks['Malayalam']) + len(isl_blocks['English'])
    if total_isl > 0:
        print(f"Placed {len(isl_blocks['English'])} English and {len(isl_blocks['Malayalam'])} Malayalam matches below Asianet.")
    else:
        print("No active Sony ISL matches found. File kept clean.")


if __name__ == "__main__":
    main()
