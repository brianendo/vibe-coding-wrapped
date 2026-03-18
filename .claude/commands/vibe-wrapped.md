# Vibe Coding Wrapped — Quick Analysis

Run the vibe coding wrapped analyzer on the user's Claude Code and Codex history.
The Python script extracts and organizes data. YOUR job is to interpret it.

## Step 1: Run the script

Run from the repo root directory:
```
python3 analyze.py --all --output ./output
```

- Use `--all` for all-time, `--last 30d` for recent, or `--since YYYY-MM-DD`
- If the user specifies a timeframe, pass it as an argument

## Step 2: Read the data

Read the private report JSON:
```
output/analysis_private.json
```

## Step 3: Interpret — this is the hard part

The script gives you numbers. You give the user meaning. Don't just recite stats.

### What to analyze

**Personality & Communication Style:**
- How do they talk to AI? (collaborative, commanding, deferential?)
- What's their emotional pattern? (frustrated but accepting? uncertain but deliberating?)
- How do they open sessions? What does that reveal about their default mode?
- What are their verbal tics or signature phrases? What do those reveal?
- How has their style evolved over time? Is the trend healthy or concerning?

**Session Patterns:**
- When are they sharpest? (time of day, session length, which projects)
- Where does engagement decay? What triggers it?
- What's the relationship between session duration and quality?
- How often do they context-switch between projects? Is it productive or scattered?

**Project Patterns:**
- Which projects get sustained attention vs abandoned?
- Which projects have the best engagement? What's different about them?
- Where are they most/least vibed? Why might that be?

**Actionable Insights:**
- What 2-3 specific behaviors should they change?
- What's working well that they should do more of?
- Based on their patterns, what's their biggest risk?

### How to present

- Lead with the most surprising or important finding
- Use the numbers to support narrative, don't just list them
- Be direct and honest — this exists to surface truths, not flatter
- Connect patterns to each other
- Keep suggestions focused on specificity (constraints, context) not surface-level framing changes

## Step 4: Ask follow-up

Ask if they want `/vibe-deep` for full conversation dynamics (both sides of the conversation, accept/correct ratio, autopilot streaks).
