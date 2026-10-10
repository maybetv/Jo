import os
import re
import requests

OUTPUT = "Zoh.m3u"
MARKER = "# --- LIVE EVENTS ---"

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


def main():
    seen = set()

    # Zoh.m3u ഫയലിലെ നിലവിലുള്ള ചാനലുകൾ ഒരു കേടുപാടും വരാതെ നിലനിർത്തുന്നു
    base_content = "#EXTM3U\n\n"
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        if MARKER in content:
            base_content = content.split(MARKER)[0].rstrip() + "\n\n"
        elif content.strip():
            base_content = content.rstrip() + "\n\n"

    # നിലവിലുള്ള ചാനലുകളുടെ അടിയിൽ പുതിയ ഇവന്റുകൾ എഴുതുന്നു
    with open(OUTPUT, "w", encoding="utf-8") as out:
        out.write(base_content)
        out.write(f"{MARKER}\n\n")

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

                # Remove playlist header
                if lines and lines[0].startswith("#EXTM3U"):
                    lines = lines[1:]

                i = 0

                while i < len(lines):

                    if not lines[i].startswith("#EXTINF"):
                        i += 1
                        continue

                    # Update group-title
                    block = [update_group_title(lines[i], provider)]

                    i += 1
                    stream = None

                    while i < len(lines):
                        line = lines[i]

                        if line.startswith("#EXTINF"):
                            # Next channel encountered
                            i -= 1
                            break

                        block.append(line)

                        if line.startswith(("http://", "https://")):
                            stream = line.strip()
                            break

                        i += 1

                    if stream and stream not in seen:
                        seen.add(stream)
                        out.write("\n".join(block))
                        out.write("\n\n")

                    i += 1

            except Exception as e:
                print(f"Failed to fetch {provider}: {e}")

    print(f"\nCombined playlist saved to {OUTPUT}")


if __name__ == "__main__":
    main()
