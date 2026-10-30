import os
import re
import requests

OUTPUT = "Zoh.m3u"
MARKER = "# --- LIVE EVENTS ---"
ISL_START_MARKER = "# --- ISL SPECIAL EVENTS ---"
ISL_END_MARKER = "# --- END ISL SPECIAL EVENTS ---"

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


def get_isl_mal_eng_type(block_lines, provider):
    """
    SonyLiv-ൽ നിന്നുള്ള ISL മാച്ചുകൾ മാത്രമാണോ എന്ന് കർശനമായി ഉറപ്പുവരുത്തുന്നു.
    മറ്റെന്ത് വന്നാലും None റിട്ടേൺ ചെയ്യും (അവ നേരെ താഴെയുള്ള LIVE EVENTS-ലേക്ക് പോകും).
    """
    full_text = " ".join(block_lines)
    full_lower = full_text.lower()

    # പ്രൊവൈഡർ SonyLiv അല്ലെങ്കിൽ Sony ആയിരിക്കണം
    is_sony = (provider.lower() == "sonyliv") or ("sony" in full_lower)
    if not is_sony:
        return None

    # ക്രിക്കറ്റ് ലിങ്കുകളോ ടാഗുകളോ ഉണ്ടെങ്കിൽ പൂർണ്ണമായി തള്ളിക്കളയുന്നു
    if "sonyeventsglobal" in full_lower or 'group-title="cricket"' in full_lower:
        return None

    # ISL ഹുക്ക് (Title, Logo URL, അല്ലെങ്കിൽ സ്ട്രീമിൽ ISL ടാഗ് ഉണ്ടായിരിക്കണം)
    match_pattern = r'(_isl\d*|\bisl\b|/isl/|indian super league|\bfootlive\b)'
    if not re.search(match_pattern, full_lower):
        return None

    # ഭാഷ തിരിച്ചറിയുന്നു
    if re.search(r'(?i)(\bmal\b|\[mal\]|_mal|/mal/|\bmalayalam\b|മലയാളം)', full_lower):
        return 'Malayalam'
    elif re.search(r'(?i)(\beng\b|\[eng\]|_eng|/eng/|\benglish\b|ഇംഗ്ലീഷ്)', full_lower):
        return 'English'

    return 'English'


def clean_file_content(content):
    """
    പഴയ ISL സെക്ഷനും, ചാനലുകൾക്കിടയിൽ തെറ്റായി കയറിയ sonyliv ക്രിക്കറ്റുകളും,
    അവസാനമുള്ള ലൈവ് ഇവന്റുകളും പൂർണ്ണമായി നീക്കം ചെയ്ത് ഒറിജിനൽ ലിസ്റ്റ് മാത്രം ബാക്കിവെക്കുന്നു.
    """
    # 1. പഴയ LIVE EVENTS മാർക്കറിന് ശേഷമുള്ളത് കളയുന്നു
    if MARKER in content:
        content = content.split(MARKER)[0]

    # 2. ഏഷ്യാനെറ്റിന് താഴെയുള്ള പഴയ ISL ബ്ലോക്ക് പൂർണ്ണമായി നീക്കം ചെയ്യുന്നു
    while ISL_START_MARKER in content and ISL_END_MARKER in content:
        start_idx = content.find(ISL_START_MARKER)
        end_idx = content.find(ISL_END_MARKER) + len(ISL_END_MARKER)
        if start_idx < end_idx:
            content = content[:start_idx] + content[end_idx:]
        else:
            break

    content = content.replace(ISL_START_MARKER, "").replace(ISL_END_MARKER, "")

    # 3. ഏഷ്യാനെറ്റിന് താഴെ കയറിക്കൂടിയ പഴയ സോണി ലൈവ് സ്ട്രീമുകളെ നീക്കം ചെയ്യുന്നു
    lines = content.splitlines(keepends=True)
    cleaned_lines = []
    skip = False

    for line in lines:
        line_lower = line.lower()
        if line.startswith("#EXTINF") and ("sonyliv-" in line_lower or "sonyeventsglobal" in line_lower):
            skip = True
            continue

        if skip:
            if line.startswith("#EXTINF"):
                skip = False
            else:
                continue

        cleaned_lines.append(line)

    return "".join(cleaned_lines).strip()


def insert_below_asianet(content, mal_list, eng_list):
    """SonyLiv ISL മാത്രം Asianet HD-ക്ക് തൊട്ടുതാഴെ പ്ലേസ് ചെയ്യുന്നു"""
    if not eng_list and not mal_list:
        return content

    ordered_items = []
    for block in eng_list:
        ordered_items.append("\n".join(block))
    for block in mal_list:
        ordered_items.append("\n".join(block))

    isl_section = f"{ISL_START_MARKER}\n\n" + "\n\n\n".join(ordered_items) + f"\n\n{ISL_END_MARKER}"

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
    malayalam_isl = []
    english_isl = []
    live_blocks = []
    seen_identifiers = set()

    base_content = "#EXTM3U\n\n"
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        base_content = clean_file_content(content)

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

                extinf_line = lines[i]
                block = [extinf_line]
                i += 1
                stream = None

                while i < len(lines):
                    line = lines[i]
                    if line.startswith("#EXTINF"):
                        i -= 1
                        break
                    block.append(line)
                    if line.strip().startswith(("http://", "https://")):
                        stream = line.strip()
                        break
                    i += 1

                # ടൈറ്റിൽ അല്ലെങ്കിൽ സ്ട്രീമിന്റെ ലിങ്ക് വെച്ച് ഡ്യൂപ്ലിക്കേഷൻ വരുന്നത് തടയുന്നു
                title_match = re.search(r',(.+)$', extinf_line)
                unique_key = title_match.group(1).strip() if title_match else (stream.split('?')[0] if stream else extinf_line)

                if unique_key not in seen_identifiers:
                    seen_identifiers.add(unique_key)

                    # SonyLiv-ൽ നിന്നുള്ള ISL മാത്രമാണോ എന്ന് ചെക്ക് ചെയ്യുന്നു
                    lang_type = get_isl_mal_eng_type(block, provider)
                    
                    if lang_type == 'Malayalam':
                        malayalam_isl.append(block)
                    elif lang_type == 'English':
                        english_isl.append(block)
                    else:
                        # ബാക്കി എന്ത് ലിങ്ക് വന്നാലും (SonyLiv ക്രിക്കറ്റ്, Fancode, Hotstar etc.) ഇവിടെ വരുന്നു
                        live_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    # Asianet-ന് താഴെ SonyLiv ISL മാത്രം ചേർക്കുന്നു
    updated_base = insert_below_asianet(base_content, malayalam_isl, english_isl)

    # സേവ് ചെയ്യുന്നു
    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(updated_base.rstrip() + "\n\n")

        # മറ്റെല്ലാ ലൈവ് ഇവന്റുകളും ഫയലിന്റെ അവസാനം കൃത്യമായ മാർക്കറിൽ മാത്രം പ്ലേസ് ചെയ്യുന്നു
        if INCLUDE_OTHER_LIVE_EVENTS and live_blocks:
            out.write(f"{MARKER}\n\n")
            out.write("\n\n".join(live_blocks) + "\n\n")

    print(f"\nSuccessfully updated {OUTPUT}!")


if __name__ == "__main__":
    main()
