import os
import re
import requests

OUTPUT = "Zoh.m3u"
MARKER = "# --- LIVE EVENTS ---"
ISL_START_MARKER = "# --- ISL SPECIAL EVENTS ---"
ISL_END_MARKER = "# --- END ISL SPECIAL EVENTS ---"

# മറ്റ് ലൈവ് ഇവന്റുകൾ ഫയലിന്റെ ഏറ്റവും അവസാനം വേണമെങ്കിൽ True, വേണ്ടെങ്കിൽ False
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
    SonyLiv-ൽ നിന്നുള്ള ISL മാച്ചുകളിൽ മലയാളവും ഇംഗ്ലീഷും മാത്രം കണ്ടെത്തുന്നു.
    ഹിന്ദി, ബംഗാളി തുടങ്ങിയ മറ്റ് ഭാഷകളോ ക്രിക്കറ്റോ വന്നാൽ ഒഴിവാക്കും (None).
    """
    full_text = " ".join(block_lines)
    full_lower = full_text.lower()

    # പ്രൊവൈഡർ SonyLiv അല്ലെങ്കിൽ Sony ആയിരിക്കണം
    is_sony = (provider.lower() == "sonyliv") or ("sony" in full_lower)
    if not is_sony:
        return None

    # ക്രിക്കറ്റ് പാറ്റേണുകൾ ഒഴിവാക്കുന്നു
    if "sonyeventsglobal" in full_lower or 'group-title="cricket"' in full_lower:
        return None

    # ISL ടാഗ് ഉണ്ടെന്ന് ഉറപ്പാക്കുന്നു
    isl_pattern = r'(_isl\d*|\bisl\b|/isl/|indian super league|\bfootlive\b)'
    if not re.search(isl_pattern, full_lower):
        return None

    # ഹിന്ദിയോ മറ്റ് ഭാഷകളോ ഉണ്ടെങ്കിൽ ഒഴിവാക്കുന്നു
    if re.search(r'(?i)(\bhin\b|\[hin\]|_hin|/hin/|\bhindi\b|ഹിന്ദി)', full_lower):
        return None

    # മലയാളം കണ്ടെത്തുന്നു
    if re.search(r'(?i)(\bmal\b|\[mal\]|_mal|/mal/|\bmalayalam\b|മലയാളം)', full_lower):
        return 'Malayalam'

    # ഇംഗ്ലീഷ് കണ്ടെത്തുന്നു
    if re.search(r'(?i)(\beng\b|\[eng\]|_eng|/eng/|\benglish\b|ഇംഗ്ലീഷ്)', full_lower):
        return 'English'

    return None


def clean_file_content(content):
    """
    പഴയ ISL ബ്ലോക്കുകളും, അവസാനം കിടക്കുന്ന ലൈവ് ഇവന്റുകളും, 
    തെറ്റായി കയറിയ മറ്റ് SonyLiv സ്ട്രീമുകളും നീക്കം ചെയ്ത് ഒറിജിനൽ ചാനലുകൾ മാത്രം ബാക്കിവെക്കുന്നു.
    """
    if MARKER in content:
        content = content.split(MARKER)[0]

    while ISL_START_MARKER in content and ISL_END_MARKER in content:
        start_idx = content.find(ISL_START_MARKER)
        end_idx = content.find(ISL_END_MARKER) + len(ISL_END_MARKER)
        if start_idx < end_idx:
            content = content[:start_idx] + content[end_idx:]
        else:
            break

    content = content.replace(ISL_START_MARKER, "").replace(ISL_END_MARKER, "")

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
    """ഇംഗ്ലീഷും മലയാളവും ISL മാത്രം Asianet HD-ക്ക് താഴെ പ്ലേസ് ചെയ്യുന്നു"""
    if not eng_list and not mal_list:
        return content

    ordered_items = []
    # ഇംഗ്ലീഷ് ആദ്യം, ശേഷം മലയാളം
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

                # യുണീക് ഐഡി വെച്ച് ഡ്യൂപ്ലിക്കേഷൻ പൂർണ്ണമായി തടയുന്നു
                title_match = re.search(r',(.+)$', extinf_line)
                unique_key = title_match.group(1).strip() if title_match else (stream.split('?')[0] if stream else extinf_line)

                if unique_key not in seen_identifiers:
                    seen_identifiers.add(unique_key)

                    lang_type = get_isl_mal_eng_type(block, provider)

                    if lang_type == 'Malayalam':
                        malayalam_isl.append(block)
                    elif lang_type == 'English':
                        english_isl.append(block)
                    else:
                        # ISL അല്ലാത്ത മറ്റെല്ലാ ലൈവ് ഇവന്റുകളും താഴേക്ക് വെക്കുന്നു
                        live_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    # Asianet-ന് താഴെ ഇംഗ്ലീഷും മലയാളവും ISL മാത്രം പ്ലേസ് ചെയ്യുന്നു
    updated_base = insert_below_asianet(base_content, malayalam_isl, english_isl)

    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(updated_base.rstrip() + "\n\n")

        # മറ്റെല്ലാ ഇവന്റുകളും ഫയലിന്റെ അവസാന ഭാഗത്ത് മാത്രം എഴുതുന്നു
        if INCLUDE_OTHER_LIVE_EVENTS and live_blocks:
            out.write(f"{MARKER}\n\n")
            out.write("\n\n".join(live_blocks) + "\n\n")

    print(f"\nSuccessfully updated {OUTPUT}!")


if __name__ == "__main__":
    main()
