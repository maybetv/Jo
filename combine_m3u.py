import os
import re
import requests

OUTPUT = "Zoh.m3u"
MARKER = "# --- LIVE EVENTS ---"
ISL_START_MARKER = "# --- ISL SPECIAL EVENTS ---"
ISL_END_MARKER = "# --- END ISL SPECIAL EVENTS ---"

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


def update_group_title(extinf, group):
    """Replace or insert group-title in #EXTINF line."""
    if 'group-title="' in extinf:
        return re.sub(
            r'group-title="[^"]*"',
            f'group-title="{group}"',
            extinf
        )

    return extinf.replace(
        "#EXTINF:-1",
        f'#EXTINF:-1 group-title="{group}"',
        1
    )


def get_isl_type(block_lines):
    """Detect Sony ISL Malayalam and English channels."""
    full_text = " ".join(block_lines).lower()
    has_isl = bool(re.search(r'\bisl\b|indian super league', full_text)) or ('sony' in full_text and 'isl' in full_text)

    if has_isl:
        if re.search(r'malayalam|മലയാളം', full_text):
            return 'Malayalam'
        elif re.search(r'english|ഇംഗ്ലീഷ്', full_text):
            return 'English'
    return None


def clean_previous_isl_block(content):
    """Removes previously injected ISL block to prevent duplication and file damage."""
    pattern = rf"\n*{re.escape(ISL_START_MARKER)}.*?{re.escape(ISL_END_MARKER)}\n*"
    return re.sub(pattern, "\n\n", content, flags=re.DOTALL)


def insert_below_asianet(base_content, isl_blocks):
    """Inserts ISL Malayalam & English below Asianet HD with 2 blank lines gap."""
    if not isl_blocks:
        return base_content

    lines = base_content.splitlines()
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

    # 2. Asianet HD ഇല്ലെങ്കിൽ സാധാരണ Asianet-ന് താഴെ പ്ലേസ് ചെയ്യാനുള്ള ബാക്കപ്പ്
    if insert_idx == -1:
        found_asianet = False
        for i, line in enumerate(lines):
            if line.startswith("#EXTINF") and re.search(r'asianet', line, re.I):
                found_asianet = True
                continue
            if found_asianet and line.strip().startswith(("http://", "https://")):
                insert_idx = i + 1
                break

    # മലയാളവും ഇംഗ്ലീഷും ചാനലുകൾ ക്രമീകരിക്കുന്നു
    isl_content_list = []
    for lang in ["Malayalam", "English"]:
        if lang in isl_blocks:
            isl_content_list.append("\n".join(isl_blocks[lang]))

    isl_section = f"{ISL_START_MARKER}\n" + "\n\n".join(isl_content_list) + f"\n{ISL_END_MARKER}"

    if insert_idx != -1:
        before = "\n".join(lines[:insert_idx]).rstrip()
        after = "\n".join(lines[insert_idx:]).lstrip()
        # 3 newlines നൽകുന്നത് വഴി 2 ബ്ലാങ്ക് ലൈനുകൾ ഗ്യാപ് വരും
        return f"{before}\n\n\n{isl_section}\n\n\n{after}"
    else:
        return f"{base_content.rstrip()}\n\n\n{isl_section}\n\n"


def main():
    seen = set()
    isl_blocks = {}
    live_blocks = []

    # 1. നിലവിലുള്ള Zoh.m3u സേഫ് ആയി റീഡ് ചെയ്യുന്നു
    base_content = "#EXTM3U\n\n"
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if MARKER in content:
            base_content = content.split(MARKER)[0].rstrip() + "\n\n"
        elif content.strip():
            base_content = content.rstrip() + "\n\n"

    # മുൻപ് ആഡ് ചെയ്ത ISL ബ്ലോക്ക് ക്ലീൻ ചെയ്യുന്നു (ഡ്യൂപ്ലിക്കേഷൻ ഒഴിവാക്കാൻ)
    base_content = clean_previous_isl_block(base_content)

    # നിലവിലുള്ള മെയിൻ ചാനലുകളുടെ URL ലിസ്റ്റ് എടുക്കുന്നു
    for line in base_content.splitlines():
        line_str = line.strip()
        if line_str.startswith(("http://", "https://")):
            seen.add(line_str)

    # 2. ലൈവ് പ്ലേലിസ്റ്റുകൾ ഫെച്ച് ചെയ്യുന്നു
    for provider, url in PLAYLISTS.items():
        print(f"Fetching {provider}...")

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30
            )
            response.raise_for_status()

            lines = response.text.splitlines()

            if lines and lines[0].startswith("#EXTM3U"):
                lines = lines[1:]

            i = 0
            while i < len(lines):
                if not lines[i].startswith("#EXTINF"):
                    i += 1
                    continue

                block = [update_group_title(lines[i], provider)]
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

                if stream and stream not in seen:
                    seen.add(stream)

                    # Sony ISL മലയാളം അല്ലെങ്കിൽ ഇംഗ്ലീഷ് വേർതിരിക്കുന്നു
                    isl_type = get_isl_type(block)
                    if isl_type and isl_type not in isl_blocks:
                        isl_blocks[isl_type] = block
                    else:
                        live_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    # 3. Asianet HD-ക്ക് താഴെ കൃത്യമായി 2 ലൈൻ ഗ്യാപ്പോടെ പ്ലേസ് ചെയ്യുന്നു
    updated_base = insert_below_asianet(base_content, isl_blocks)

    # 4. Zoh.m3u സേവ് ചെയ്യുന്നു
    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(updated_base.rstrip() + "\n\n")
        out.write(f"{MARKER}\n\n")
        if live_blocks:
            out.write("\n\n".join(live_blocks) + "\n\n")

    print(f"\nSuccessfully updated {OUTPUT}!")
    if isl_blocks:
        print(f"Placed ISL channels ({', '.join(isl_blocks.keys())}) directly below Asianet HD.")


if __name__ == "__main__":
    main()
