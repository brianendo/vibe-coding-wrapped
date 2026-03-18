# Vibe Coding Wrapped — Deep Analysis

Parse full Claude Code conversation JSONL files to analyze BOTH sides of
the conversation. The script extracts raw metrics. YOUR job is to interpret
them into real insights about how this person works with AI.

## Step 1: Run the script

Run from the repo root directory:
```
python3 deep_analyze.py --all --output ./output
```

- Use `--project <name>` to filter to a specific project
- This may take 1-2 minutes for large histories

## Step 2: Read the data

Read both files:
```
output/deep_analysis.json
output/deep_wrapped.md
```

Also read the quick analysis if available for cross-referencing:
```
output/analysis_private.json
```

## Step 3: Deep interpretation

This is the "co-founder who won't let you skip hard truths" analysis.
The script gives you data. You find the story in the data.

### Conversation Dynamics

**Accept/Correct Ratio:**
- What does their accept rate actually mean in context?
- Is low correction rate because AI is good, or because they're not checking?
- Look at the `correction_contexts` — what actually triggers pushback? What pattern is there?
- Compare accept rates across projects — where do they engage more vs less? Why?

**Autopilot Streaks:**
- Where are the longest streaks? Which projects?
- What percentage of total interactions happen inside streaks?
- Is there a session length threshold where autopilot kicks in?

**Input Specificity:**
- What's the constraint rate? How many messages explain reasoning or say what they DON'T want?
- What's the bare short message percentage?
- Are there projects where they're more specific? What's different?
- How does specificity correlate with AI thinking depth?

### Behavioral Patterns

**Frustration Response:**
- What happens after frustration? Accept? Redirect? Question?
- This is the most actionable insight — frustration is a signal they're already ignoring
- Calculate the frustration→accept vs frustration→redirect ratio

**Delegation Balance:**
- Create-to-own ratio — are they building or spectating?

**Per-Project Breakdown:**
- Rank projects by engagement quality (not just volume)
- Identify the user's "best self" project — where metrics are healthiest
- Identify the "worst" project — where they most need to change behavior
- What distinguishes the two?

### Synthesis

**The core question:** Is this person using AI as a tool they direct, or are they along for the ride?

**Connect insights across dimensions:**
- If they're most engaged on brainstorming but most passive on implementation — say that
- If engagement drops after message 20 in every project — that's a session hygiene issue
- If they never correct but frequently express frustration — they're swallowing feedback

### What NOT to do
- Don't suggest cosmetic framing changes (e.g., "say I want instead of can you")
- Don't treat all short messages as bad — short + specific is fine
- Don't just list numbers — interpret them into a narrative
- Don't soften findings — this exists to surface uncomfortable truths

## Step 4: Actionable takeaways

End with 3-5 specific, behavioral changes. Not vague advice.
Tie each suggestion to a specific number from their data.
