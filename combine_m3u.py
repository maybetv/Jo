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
    full_text = " ".join(block_lines)
    full_lower = full_text.lower()

    is_sony = (provider.lower() == "sonyliv") or ("sony" in full_lower)
    if not is_sony:
        return None

    # sonyliv- നമ്പറുകളും ഒപ്പം isl അല്ലെങ്കിൽ footlive കീവേഡുകളും ഓട്ടോമാറ്റിക്കായി റെക്കഗ്നൈസ് ചെയ്യുന്നു
    match_pattern = r'(sonyliv-\d+|\bisl\b|\bisl\d+\b|\bfootlive\b)'
    if not re.search(match_pattern, full_lower):
        return None

    if re.search(r'(?i)(\bmal\b|\[mal\]|_mal|/mal/|\bmalayalam\b|മലയാളം)', full_lower):
        return 'Malayalam'
    elif re.search(r'(?i)(\beng\b|\[eng\]|_eng|/eng/|\benglish\b|ഇംഗ്ലീഷ്)', full_lower):
        return 'English'

    return None


def clean_file_content(content):
    """
    നമ്പറുകൾ എന്തുതന്നെയായാലും 'sonyliv-' പാറ്റേണും ISL കീവേഡും വെച്ച് 
    പഴയ ISL മാച്ചുകൾ മാത്രം സുരക്ഷിതമായി നീക്കം ചെയ്യുന്നു.
    """
    if MARKER in content:
        base_part = content.split(MARKER)[0]
    else:
        base_part = content

    while ISL_START_MARKER in base_part and ISL_END_MARKER in base_part:
        start_idx = base_part.find(ISL_START_MARKER)
        end_idx = base_part.find(ISL_END_MARKER) + len(ISL_END_MARKER)
        if start_idx < end_idx:
            base_part = base_part[:start_idx] + base_part[end_idx:]
        else:
            break
            
    base_part = base_part.replace(ISL_START_MARKER, "").replace(ISL_END_MARKER, "")

    lines = base_part.splitlines(keepends=True)
    cleaned_lines = []
    skip = False
    
    for line in lines:
        line_lower = line.lower()
        # sonyliv- നമ്പറുകളും isl/footlive ഉള്ളവ മാത്രം ക്ലീൻ ചെയ്യുന്നു (സ്റ്റാറ്റിക് ചാനലുകളെ ഒഴിവാക്കി)
        if (re.search(r'sonyliv-\d+', line_lower) or 'footlive' in line_lower) and ('isl' in line_lower or 'footlive' in line_lower) and not ('asianet' in line.lower()):
            if cleaned_lines and cleaned_lines[-1].startswith("#EXTINF"):
                cleaned_lines.pop()
            skip = True
            continue
            
        if skip and (line.startswith("http://") or line.startswith("https://") or line.startswith("#KODIPROP") or line.startswith("PlayBackConfig") or line.strip() == ""):
            continue
        else:
            skip = False
            cleaned_lines.append(line)

    return "".join(cleaned_lines).strip()


def insert_below_asianet(content, mal_list, eng_list):
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
    seen_base_urls = set()

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

                if stream:
                    base_stream_url = stream.split('?')[0]

                    if base_stream_url not in seen_base_urls:
                        seen_base_urls.add(base_stream_url)

                        lang_type = get_isl_mal_eng_type(block, provider)
                        
                        if lang_type == 'Malayalam':
                            malayalam_isl.append(block)
                        elif lang_type == 'English':
                            english_isl.append(block)
                        else:
                            live_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    updated_base = insert_below_asianet(base_content, malayalam_isl, english_isl)

    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(updated_base.rstrip() + "\n\n")

        if INCLUDE_OTHER_LIVE_EVENTS and live_blocks:
            out.write(f"{MARKER}\n\n")
            out.write("\n\n".join(live_blocks) + "\n\n")

    print(f"\nSuccessfully updated {OUTPUT}!")


if __name__ == "__main__":
    main()
