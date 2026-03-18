---
description: Quick analysis of your AI coding patterns, personality, and vibe score
---

# Vibe Coding Wrapped — Quick Analysis

The Python script extracts and organizes raw data from your AI history.
YOUR job is to interpret it into real insights.

## Step 1: Find and run the script

Find the plugin install path:
```
find ~/.claude/plugins/cache -name "analyze.py" -path "*/vibe-coding-wrapped/*" 2>/dev/null | head -1
```

Run it (use the path found above):
```
python3 <path>/analyze.py --all --output /tmp/vibe-wrapped
```

- Use `--all` for all-time, `--last 30d` for recent, or `--since YYYY-MM-DD`
- If the user specifies a timeframe, pass it as an argument

## Step 2: Read the data

Read the JSON output:
```
/tmp/vibe-wrapped/analysis_private.json
```

## Step 3: Interpret the data

The script gives you numbers and organized text. You generate ALL interpretation.
Do NOT just read back the script's output. Analyze the raw data yourself.

### What to analyze

**Personality & Communication Style:**
- How do they talk to AI? Look at `ai_relationship`, `opener_styles`, `emotions`
- What verbal tics or signature phrases do they have? Check `top_words`, `top_phrases`
- How has their style evolved? Check `evolution` data
- What's their emotional pattern? Cross-reference `emotions` with `response_velocity`

**Session Patterns:**
- When are they sharpest? Cross-reference `hours` with project `vibe_scores`
- Where does engagement decay? Look at `vibe_drift` per session
- What's the relationship between session length and quality? Check `session_length_impact`

**Project Patterns:**
- Which projects get sustained attention? Check `days_active`, `span_days`, `status`
- Where are they most/least vibed? What's different about those projects?

**Actionable Insights:**
- What 2-3 specific behaviors should they change?
- What's working well that they should do more of?
- Focus on specificity (constraints, context) not surface-level framing changes

### How to present

- Lead with the most surprising finding
- Numbers support narrative — don't just list them
- Be direct and honest
- Connect patterns to each other

## Step 4: Offer next steps

- Ask if they want `/vibe-deep` for full conversation analysis (both sides)
- Ask if they want a shareable card for X
