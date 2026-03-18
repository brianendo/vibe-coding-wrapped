---
description: Generate a shareable Vibe Coding Wrapped card image for X/Twitter
---

# Generate Shareable Card

Generate a polished image card from the analysis data. The card shows public stats
only — no raw messages, no project names unless the user opts in.

## Step 1: Ensure analysis has been run

Check if analysis output exists at `/tmp/vibe-wrapped/`. If not, run the quick analysis first:
```
python3 <plugin-path>/analyze.py --all --output /tmp/vibe-wrapped
```

Also run deep analysis if not already done (it has better stats for the card):
```
python3 <plugin-path>/deep_analyze.py --all --output /tmp/vibe-wrapped
```

## Step 2: Generate the card

```
python3 <plugin-path>/generate_card.py --input /tmp/vibe-wrapped --output /tmp/vibe-wrapped/wrapped_card.png
```

Requires Pillow: `pip install Pillow`

## Step 3: Show the user

Read and display the generated card image:
```
/tmp/vibe-wrapped/wrapped_card.png
```

## Step 4: Customize

Ask the user if they want to adjust anything:
- Different hero stat (vibe score vs accept rate vs autopilot streak)
- Include or exclude project names
- Custom personality description (Claude-generated from the analysis)
- Different color theme

If they want a custom personality line, generate one from the analysis data —
something specific and memorable, not generic. Example: "Deliberator who treats
AI as a partner but rarely pushes back" is better than "The Collaborator."

To pass custom stats, use:
```
python3 <plugin-path>/generate_card.py --stats '{"vibe_score": 46, "personality": "Custom text", ...}' --output /tmp/vibe-wrapped/wrapped_card.png
```
