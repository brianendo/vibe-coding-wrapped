#!/usr/bin/env python3
"""
Generate a shareable Vibe Coding Wrapped card image for X/Twitter.

Reads the analysis JSON and generates a polished 1200x675 PNG card.
Stats only — no raw messages or sensitive data.

Usage:
    python3 generate_card.py                              # Uses default output dir
    python3 generate_card.py --input ./output              # Custom input dir
    python3 generate_card.py --output ./my_card.png        # Custom output path
    python3 generate_card.py --stats '{"vibe_score": 46}'  # Pass stats as JSON directly

Requires: pip install Pillow
"""

import json
import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:
    print("Pillow is required. Install with: pip install Pillow")
    sys.exit(1)

WIDTH, HEIGHT = 1200, 675


def create_gradient(width, height, color1, color2):
    """Create a vertical gradient background."""
    img = Image.new("RGBA", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(color1[0] + (color2[0] - color1[0]) * ratio)
        g = int(color1[1] + (color2[1] - color1[1]) * ratio)
        b = int(color1[2] + (color2[2] - color1[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))
    return img


def draw_glow_text(img, position, text, font, text_color, glow_color, glow_radius=10):
    """Draw text with a soft glow effect behind it."""
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.text(position, text, font=font, fill=glow_color)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=glow_radius))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)
    draw.text(position, text, font=font, fill=text_color)
    return img


def load_font(size, bold=False):
    """Try to load a nice font, fall back to default."""
    font_paths = [
        # macOS
        "/Library/Fonts/Montserrat-Bold.ttf" if bold else "/Library/Fonts/Montserrat-Regular.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/TTF/DejaVuSans.ttf",
        # Windows
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def load_stats(input_dir):
    """Load stats from analysis JSON files."""
    stats = {}

    # Try quick analysis
    quick_path = Path(input_dir) / "analysis_private.json"
    if quick_path.exists():
        with open(quick_path) as f:
            quick = json.load(f)
        stats["vibe_score"] = quick["overall"]["vibe_pct"]
        stats["directed_pct"] = quick["overall"]["directed_pct"]
        stats["total_messages"] = quick["overall"]["total_messages"]
        stats["total_sessions"] = quick["overall"]["total_sessions"]

        fs = quick.get("fun_stats", {})
        stats["personality"] = fs.get("personality", "Unknown")
        stats["personality_desc"] = fs.get("personality_desc", "")
        stats["active_days"] = fs.get("active_days", 0)
        stats["unique_projects"] = fs.get("unique_projects", 0)
        stats["total_chars"] = fs.get("total_characters_typed", 0)
        stats["longest_directed_streak"] = fs.get("longest_directed_streak", 0)
        stats["longest_vibe_streak"] = fs.get("longest_vibe_streak", 0)
        stats["total_corrections"] = fs.get("total_corrections", 0)

        pers = quick.get("personality", {})
        sd = pers.get("session_duration_stats", {})
        stats["total_hours"] = sd.get("total_hours_with_ai", 0)

        timeframe = quick.get("meta", {}).get("timeframe", {})
        stats["date_range"] = f"{timeframe.get('start', '?')} to {timeframe.get('end', '?')}"

    # Try deep analysis
    deep_path = Path(input_dir) / "deep_analysis.json"
    if deep_path.exists():
        with open(deep_path) as f:
            deep = json.load(f)
        dyn = deep.get("dynamics", {})
        stats["accept_rate"] = dyn.get("accept_rate", 0)
        stats["correct_rate"] = dyn.get("correct_rate", 0)
        stats["total_interactions"] = sum(dyn.get("response_types", {}).values())
        streaks = dyn.get("accept_streaks", {})
        stats["max_autopilot_streak"] = streaks.get("max_consecutive_accepts", 0)
        stats["streaks_5_plus"] = streaks.get("streaks_of_5_plus", 0)
        tok = dyn.get("tokens", {})
        stats["estimated_cost"] = tok.get("estimated_cost_usd", 0)

        spec = deep.get("patterns", {}).get("specificity", {})
        stats["constraint_pct"] = spec.get("constraint_pct", 0)

    return stats


def generate_card(stats, output_path="wrapped_card.png"):
    """Generate the shareable card image."""
    # Background gradient — dark purple to deep blue
    bg = create_gradient(WIDTH, HEIGHT, (25, 5, 45), (5, 15, 60))

    # Fonts
    title_font = load_font(42, bold=True)
    hero_font = load_font(88, bold=True)
    hero_label_font = load_font(22)
    stat_value_font = load_font(38, bold=True)
    stat_label_font = load_font(16)
    personality_font = load_font(28, bold=True)
    desc_font = load_font(18)
    footer_font = load_font(14)

    # Title
    bg = draw_glow_text(
        bg, (60, 35),
        "VIBE CODING WRAPPED",
        title_font,
        text_color=(255, 255, 255, 240),
        glow_color=(138, 43, 226, 80),
        glow_radius=12,
    )

    # Date range
    draw = ImageDraw.Draw(bg)
    date_range = stats.get("date_range", "")
    if date_range:
        draw.text((60, 85), date_range, font=footer_font, fill=(180, 180, 180, 180))

    # Hero stat — vibe score or accept rate
    hero_value = stats.get("accept_rate") or stats.get("vibe_score", "?")
    hero_label = "autopilot rate" if "accept_rate" in stats else "vibe score"
    accent = (0, 230, 180, 255)
    accent_glow = (0, 230, 180, 50)

    bg = draw_glow_text(
        bg, (60, 115),
        f"{hero_value}%",
        hero_font,
        text_color=accent,
        glow_color=accent_glow,
        glow_radius=15,
    )
    draw = ImageDraw.Draw(bg)
    draw.text((60, 215), hero_label, font=hero_label_font, fill=(180, 180, 180, 200))

    # Personality
    personality = stats.get("personality", "")
    if personality:
        draw.text((60, 260), personality, font=personality_font, fill=(255, 255, 255, 230))
        desc = stats.get("personality_desc", "")
        if desc and len(desc) > 80:
            desc = desc[:77] + "..."
        if desc:
            draw.text((60, 295), desc, font=desc_font, fill=(160, 160, 160, 200))

    # Stat cards row
    card_y = 345
    card_h = 120
    card_w = 250
    gap = 22
    margin = 60

    stat_items = []
    if "total_interactions" in stats:
        stat_items.append((f"{stats['total_interactions']:,}", "interactions"))
    elif "total_messages" in stats:
        stat_items.append((f"{stats['total_messages']:,}", "messages"))

    if "max_autopilot_streak" in stats:
        stat_items.append((f"{stats['max_autopilot_streak']}", "max autopilot streak"))
    elif "longest_vibe_streak" in stats:
        stat_items.append((f"{stats['longest_vibe_streak']}", "longest vibe streak"))

    if "total_hours" in stats and stats["total_hours"]:
        stat_items.append((f"{stats['total_hours']:.0f}h", "total hours with AI"))
    elif "active_days" in stats:
        stat_items.append((f"{stats['active_days']}", "days active"))

    if "unique_projects" in stats:
        stat_items.append((f"{stats['unique_projects']}", "projects"))

    # Only show up to 4
    stat_items = stat_items[:4]

    for i, (value, label) in enumerate(stat_items):
        x = margin + i * (card_w + gap)

        # Semi-transparent card
        card = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
        card_draw = ImageDraw.Draw(card)
        card_draw.rounded_rectangle(
            [(0, 0), (card_w - 1, card_h - 1)],
            radius=14,
            fill=(255, 255, 255, 18),
            outline=(255, 255, 255, 35),
            width=1,
        )
        bg.paste(card, (x, card_y), card)

        draw = ImageDraw.Draw(bg)
        draw.text((x + 20, card_y + 18), value, font=stat_value_font, fill=(255, 255, 255, 255))
        draw.text((x + 20, card_y + 72), label, font=stat_label_font, fill=(160, 160, 160, 200))

    # Bottom stats row
    bottom_y = 500
    bottom_items = []
    if "constraint_pct" in stats:
        bottom_items.append(f"{stats['constraint_pct']}% messages with constraints")
    if "total_corrections" in stats:
        bottom_items.append(f"{stats['total_corrections']} corrections")
    if "streaks_5_plus" in stats:
        bottom_items.append(f"{stats['streaks_5_plus']} autopilot streaks (5+)")

    if bottom_items:
        bottom_text = "  |  ".join(bottom_items[:3])
        draw.text((margin, bottom_y), bottom_text, font=desc_font, fill=(120, 120, 120, 180))

    # Footer
    draw.text((margin, HEIGHT - 50), "github.com/brianendo/vibe-coding-wrapped", font=footer_font, fill=(100, 100, 100, 150))

    # Save
    final = bg.convert("RGB")
    final.save(output_path, "PNG", quality=95)
    print(f"Card saved: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate Vibe Coding Wrapped shareable card")
    parser.add_argument("--input", type=str, default=".", help="Directory with analysis JSON files")
    parser.add_argument("--output", type=str, default="wrapped_card.png", help="Output image path")
    parser.add_argument("--stats", type=str, help="Pass stats as JSON string directly")
    args = parser.parse_args()

    if args.stats:
        stats = json.loads(args.stats)
    else:
        stats = load_stats(args.input)

    if not stats:
        print("No analysis data found. Run analyze.py or deep_analyze.py first.")
        sys.exit(1)

    generate_card(stats, args.output)


if __name__ == "__main__":
    main()
