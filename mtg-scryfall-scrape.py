#!/usr/bin/env python3
import argparse, json, os, re, time, urllib.parse, urllib.request

API = "https://api.scryfall.com/cards/search"
UA  = "scryfall-stdlib/1.0 (personal use)"

def slug(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def build_query(sets, include_tokens=True):
    parts = []
    for sc in sets:
        sc = sc.lower()
        parts.append(f"e:{sc}")
        if include_tokens:
            parts.append(f"e:t{sc}")
    return " OR ".join(parts)

def http_get_json(url: str, params: dict | None = None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def stream_to_file(url: str, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 14)
            if not chunk:
                break
            f.write(chunk)

def fetch_all_cards(query: str, include_variations=True, delay=0.12):
    params = {
        "order": "set",
        "q": query,
        "unique": "prints",                # all prints (alt art)
        "include_extras": "true",
        "include_variations": "true" if include_variations else "false",
    }
    data = http_get_json(API, params)
    out = data.get("data", [])
    while data.get("has_more"):
        data = http_get_json(data["next_page"])
        out.extend(data.get("data", []))
        time.sleep(delay)
    return out

def pick_image(card, version: str):
    # Single-faced
    if card.get("image_uris"):
        u = card["image_uris"]
        return (u.get(version) or u.get("png") or u.get("large")
                or u.get("normal"))
    # Double-faced
    if card.get("card_faces"):
        m = {}
        for i, face in enumerate(card["card_faces"], 1):
            u = (face or {}).get("image_uris") or {}
            url = (u.get(version) or u.get("png") or u.get("large") 
                   or u.get("normal"))
            if url:
                m[("front" if i == 1 else "back")] = url
        return m if m else None
    # Fallback image endpoint
    cid = card.get("id")
    if cid:
        return ("https://api.scryfall.com/cards/"
                f"{urllib.parse.quote(cid)}?format=image&version={version}")
    return None

def main():
    ap = argparse.ArgumentParser(
        description="Scryfall list & images (stdlib only)")
    ap.add_argument("sets", nargs="+",
                    help="Set codes, e.g. spm spe mar or m21")
    ap.add_argument("--no-tokens", action="store_true",
                    help="Do not include tokens")
    ap.add_argument("--no-variations", action="store_true",
                    help="Do not include alternate prints")
    ap.add_argument("--download-images", action="store_true",
                    help="Download images instead of names")
    ap.add_argument("--image-version", default="png",
                    choices=["png","large","normal","art_crop","border_crop"],
                    help="Image size (for print: png)")
    ap.add_argument("--out", default="output",
                    help="TXT file or folder for images")
    ap.add_argument("--delay", type=float, default=0.12,
                    help="Delay between requests (s)")
    args = ap.parse_args()

    q = build_query(args.sets, include_tokens=not args.no_tokens)
    cards = fetch_all_cards(q, include_variations=not args.no_variations,
                            delay=args.delay)
    cards.sort(key=lambda c: (c.get("set",""), c.get("collector_number","")))

    if not args.download_images:
        lines = [f'{c["name"]} ({c["set"].upper()}) {c["collector_number"]}'
                 for c in cards]
        out_path = args.out if args.out.endswith(".txt") else f"{args.out}.txt"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Zapisano {len(lines)} redaka → {os.path.abspath(out_path)}")
        return

    # Download images
    out_dir = args.out
    total = 0
    for c in cards:
        set_code = (c.get("set") or "").upper()
        num = c.get("collector_number") or "?"
        name = c.get("name") or "Unknown"
        base = f"{num} - {slug(name)} ({set_code})"
        folder = os.path.join(out_dir, set_code)
        chosen = pick_image(c, args.image_version)

        if isinstance(chosen, str):
            ext = ".png" if args.image_version == "png" else ".jpg"
            path = os.path.join(folder, base + ext)
            try:
                stream_to_file(chosen, path); total += 1
            except Exception as e:
                print(f"[SKIP] {name} #{num} ({set_code}) -> {e}")
            time.sleep(args.delay)

        elif isinstance(chosen, dict):
            for side, url in chosen.items():
                ext = ".png" if args.image_version == "png" else ".jpg"
                path = os.path.join(folder, base + f" - {side}" + ext)
                try:
                    stream_to_file(url, path); total += 1
                except Exception as e:
                    print(f"[SKIP] {name} #{num} ({set_code}) [{side}] -> {e}")
                time.sleep(args.delay)
        else:
            print(f"[NOIMG] {name} #{num} ({set_code})")
    print(f"Downloaded {total} images → {os.path.abspath(out_dir)}")

if __name__ == "__main__":
    main()
