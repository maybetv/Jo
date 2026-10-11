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
    "SonyLiv": "https://github.com/kajju027/SonyLiv-Events-Json/raw/refs/heads/main/sonyliv.m3u",
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
    1. ആദ്യം Sony ഉറപ്പുവരുത്തുന്നു.
    2. ISL / കേരള ബ്ലാസ്റ്റേഴ്സ് മാച്ചുകൾ മാത്രം കണ്ടെത്തുന്നു.
    3. മലയാളം, ഇംഗ്ലീഷ് എന്നിങ്ങനെ വേർതിരിക്കുന്നു.
    """
    full_text = " ".join(block_lines).lower()

    # 1. FIRST HINT: പ്രൊവൈഡർ SonyLiv ആയിരിക്കണം അല്ലെങ്കിൽ വരികളിൽ 'sony' ഉണ്ടായിരിക്കണം
    is_sony = (provider.lower() == "sonyliv") or ("sony" in full_text)
    if not is_sony:
        return None  # Sony അല്ലെങ്കിൽ ഇവിടെ വെച്ച് തന്നെ ഒഴിവാക്കും

    # 2. SECOND HINT: ISL / കേരള ബ്ലാസ്റ്റേഴ്സ് കീവേഡുകൾ ഉണ്ടോ എന്ന് പരിശോധിക്കുന്നു
    match_keywords = (
        r'\b(isl|indian super league|kerala blasters|blasters|kbfc|kerala|footlive)\b'
        r'|കേരള|ബ്ലാസ്റ്റേഴ്സ്'
    )
    if not re.search(match_keywords, full_text):
        return None  # ഇവന്റ് മാച്ച് അല്ലെങ്കിൽ ഒഴിവാക്കും

    # 3. THIRD HINT: ഭാഷ മലയാളമാണോ ഇംഗ്ലീഷാണോ എന്ന് തിരിക്കുന്നു
    if re.search(r'(\bmal\b|\[mal\]|_mal|/mal/|malayalam|മലയാളം)', full_text):
        return 'Malayalam'
    elif re.search(r'(\beng\b|\[eng\]|_eng|/eng/|english|ഇംഗ്ലീഷ്)', full_text):
        return 'English'

    return None


def clean_previous_isl_block(content):
    """മുൻപ് ചേർത്ത ISL ബ്ലോക്ക് ഫയലിൽ നിന്ന് കൃത്യമായി നീക്കം ചെയ്യുന്നു."""
    pattern = rf"\n*{re.escape(ISL_START_MARKER)}.*?{re.escape(ISL_END_MARKER)}\n*"
    return re.sub(pattern, "\n\n", content, flags=re.DOTALL)


def insert_below_asianet(content, isl_blocks):
    """
    മാച്ചുകൾ ഉണ്ടെങ്കിൽ മാത്രം ഏഷ്യാനെറ്റിന് താഴെ മലയാളം, ഇംഗ്ലീഷ് ക്രമത്തിൽ ചേർക്കുന്നു.
    മാച്ചുകൾ ഇല്ലെങ്കിൽ ഫയലിൽ യാതൊരു മാറ്റവും വരുത്തില്ല.
    """
    has_any_isl = any(len(blocks) > 0 for blocks in isl_blocks.values())
    if not has_any_isl:
        return content  # ലിങ്ക് ഇല്ലെങ്കിൽ ബ്ലാങ്ക് ആയി നിലനിർത്തും

    # മലയാളം ആദ്യം, രണ്ടാമത് ഇംഗ്ലീഷ്
    isl_content_list = []
    for lang in ["Malayalam", "English"]:
        for block in isl_blocks.get(lang, []):
            isl_content_list.append("\n".join(block))

    isl_section = f"{ISL_START_MARKER}\n" + "\n\n".join(isl_content_list) + f"\n{ISL_END_MARKER}"

    lines = content.splitlines(keepends=True)
    insert_idx = -1
    found_asianet = False

    # 1. Asianet HD കണ്ടെത്തുന്നു
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and re.search(r'asianet.*hd', line, re.I):
            found_asianet = True
            continue
        if found_asianet and line.strip().startswith(("http://", "https://")):
            insert_idx = i + 1
            break

    # 2. ബാക്കപ്പായി സാധാരണ Asianet
    if insert_idx == -1:
        found_asianet = False
        for i, line in enumerate(lines):
            if line.startswith("#EXTINF") and re.search(r'asianet', line, re.I):
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

    # 1. നിലവിലുള്ള ഫയൽ അതേപടി റീഡ് ചെയ്യുന്നു
    base_content = "#EXTM3U\n\n"
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if MARKER in content:
            base_content = content.split(MARKER)[0].rstrip() + "\n\n"
        elif content.strip():
            base_content = content.rstrip() + "\n\n"

    # പഴയ ISL ബ്ലോക്ക് ക്ലീൻ ചെയ്യുന്നു
    base_content = clean_previous_isl_block(base_content)

    existing_streams = set()
    for line in base_content.splitlines():
        line_str = line.strip()
        if line_str.startswith(("http://", "https://")):
            existing_streams.add(line_str)

    # 2. പ്ലേലിസ്റ്റുകൾ പരിശോധിക്കുന്നു
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

                if stream and stream not in existing_streams:
                    existing_streams.add(stream)

                    # ഫിൽട്ടർ പരിശോധിക്കുന്നു (Sony -> Match -> Language)
                    isl_type = get_isl_type(block, provider)
                    if isl_type:
                        isl_blocks[isl_type].append(block)
                    else:
                        live_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    # 3. Asianet HD-ക്ക് താഴെ ഇൻസേർട്ട് ചെയ്യുന്നു (മാച്ചുകൾ ഉണ്ടെങ്കിൽ മാത്രം)
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
        print(f"Placed {len(isl_blocks['Malayalam'])} Malayalam and {len(isl_blocks['English'])} English matches below Asianet HD.")
    else:
        print("No active Sony ISL matches found. Left clean without modifications.")


if __name__ == "__main__":
    main()
