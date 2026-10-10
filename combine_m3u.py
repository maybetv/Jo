import os
import re
import requests

OUTPUT = "Zoh.m3u"
MARKER = "# ==================== LIVE EVENTS ===================="

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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}


def update_group_title(extinf, group):
    """Replace or insert group-title in #EXTINF line safely."""
    if 'group-title="' in extinf:
        return re.sub(
            r'group-title="[^"]*"',
            f'group-title="{group}"',
            extinf
        )

    match = re.match(r'(#EXTINF:[^ ,]*)', extinf)
    if match:
        prefix = match.group(1)
        return extinf.replace(prefix, f'{prefix} group-title="{group}"', 1)

    return f'{extinf} group-title="{group}"'


def get_base_content():
    """Reads existing Zoh.m3u and preserves all original channels above the marker."""
    if not os.path.exists(OUTPUT):
        return "#EXTM3U\n\n", set()

    try:
        with open(OUTPUT, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {OUTPUT}: {e}")
        return "#EXTM3U\n\n", set()

    # If previous live events exist, keep everything before the marker
    if MARKER in content:
        base_part = content.split(MARKER)[0].strip()
    else:
        base_part = content.strip()

    if not base_part.startswith("#EXTM3U"):
        base_part = "#EXTM3U\n\n" + base_part

    # Record existing URLs so base channels are never duplicated
    existing_urls = set()
    for line in base_part.splitlines():
        line_str = line.strip()
        if line_str.startswith(("http://", "https://")):
            existing_urls.add(line_str)

    return base_part + "\n\n", existing_urls


def main():
    base_content, seen = get_base_content()
    event_blocks = []

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

            # Remove remote playlist header
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
                    event_blocks.append("\n".join(block))

                i += 1

        except Exception as e:
            print(f"Failed to fetch {provider}: {e}")

    # Write: Base channels untouched + Marker + Updated live events
    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(base_content)
        out.write(f"{MARKER}\n\n")
        if event_blocks:
            out.write("\n\n".join(event_blocks) + "\n")

    print(f"\nSuccessfully updated {OUTPUT} with {len(event_blocks)} live events!")


if __name__ == "__main__":
    main()
