# Vibe Coding Wrapped

Spotify Wrapped for your AI coding sessions. Analyzes your Claude Code and Codex conversation history to measure how much you're **directing** vs **vibe coding**.

## What it measures

**Quick Analysis** (`analyze.py`) — parses your message history:
- Vibe Code Score (% directed vs vibing)
- AI personality type (Architect → Navigator → Collaborator → Explorer → Delegator → Viber)
- Engagement decay (do you fade out in long sessions?)
- Communication style (how you frame requests, emotional signals, decision patterns)
- Session stats (duration, peak hours, weekday/weekend split)
- Project focus map (where you spend time, which projects you return to)

**Deep Analysis** (`deep_analyze.py`) — parses full conversation files (both sides):
- Accept/correct ratio (do you ever push back on AI?)
- Autopilot streaks (consecutive messages where AI runs unchallenged)
- AI output volume vs your input
- Thinking depth (how hard AI works on your problems)
- Tool usage patterns
- Per-project breakdown
- Actionable suggestions for improvement

## Quick start

```bash
# Quick analysis (runs in seconds)
python3 analyze.py --all

# Deep analysis (parses full conversations, 1-2 min)
python3 deep_analyze.py --all

# Last 30 days
python3 analyze.py --last 30d

# Specific timeframe
python3 analyze.py --since 2025-12-01

# Filter to a project
python3 deep_analyze.py --project scraper
```

## Output

Both scripts generate:
- **Private report** (JSON) — full data for AI interpretation or further analysis
- **Public wrapped** (Markdown) — shareable summary with no raw message content

```
output/
├── analysis_private.json   # Quick: full stats + session data
├── wrapped_public.md       # Quick: shareable wrapped card
├── deep_analysis.json      # Deep: conversation dynamics
└── deep_wrapped.md         # Deep: shareable deep analysis
```

## Data sources

All data is read locally from your machine. Nothing is sent anywhere.

| Source | Location | Contains |
|--------|----------|----------|
| Claude Code history | `~/.claude/history.jsonl` | Your prompts, timestamps, project |
| Claude Code conversations | `~/.claude/projects/**/*.jsonl` | Full conversations (both sides), token usage, tool calls |
| Codex history | `~/.codex/history.jsonl` | Your prompts |
| Codex threads | `~/.codex/state_5.sqlite` | Thread metadata, git info |

## Personality types

| Type | Vibe Score | Description |
|------|-----------|-------------|
| The Architect | < 35% | Drives sessions with precision. Clear specs, pushes back. |
| The Navigator | 35-42% | Guides with a destination, lets AI help with the route. |
| The Collaborator | 42-48% | Treats AI as a partner. "We" language, shared thinking. |
| The Explorer | 48-55% | Curious and open-ended. Great for discovery, risky for shipping. |
| The Delegator | 55-65% | Hands off significant work. Knows what, lets AI figure how. |
| The Viber | > 65% | AI drives most sessions. Quick inputs, minimal ownership. |

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- Claude Code and/or Codex installed (for data to analyze)
