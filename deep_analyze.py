#!/usr/bin/env python3
"""
Vibe Coding Wrapped — Deep Analysis

Parses full Claude Code conversation JSONL files to analyze
both sides of the conversation: your inputs AND AI responses.

This reveals things the quick analysis can't:
- Accept/correct ratio (do you push back on AI?)
- AI output volume vs your input
- Thinking depth (how hard is AI working?)
- Tool usage patterns (what is AI doing for you?)
- Conversation dynamics (who's really driving?)

Usage:
    python3 deep_analyze.py                    # Last 30 days
    python3 deep_analyze.py --all              # All time
    python3 deep_analyze.py --project scraper  # Specific project
    python3 deep_analyze.py --top 10           # Top N projects by size
"""

import json
import re
import sys
import argparse
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
CODEX_DIR = Path.home() / ".codex"
PROJECTS_DIR = CLAUDE_DIR / "projects"

REACTIVE_WORDS = {
    "yes", "yeah", "ok", "okay", "sure", "yep", "y", "go", "yea",
    "do it", "lets do it", "let's do it", "go ahead", "looks good",
    "sounds good", "perfect", "nice", "cool", "great", "thanks",
    "thank you", "lgtm", "ship it", "continue", "proceed", "lets go",
    "let's go", "good", "fine", "right", "exactly", "correct", "agreed",
    "awesome", "sweet", "done", "got it", "makes sense",
}

CORRECTION_PATTERNS = [
    r"^no[,.\s]", r"^wrong", r"^actually[,.\s]", r"^wait[,.\s]",
    r"^that's not", r"^that is not", r"^not that", r"^nah",
    r"^hold on", r"^stop", r"^scratch that", r"^hmm",
]


def extract_project_name(dir_name):
    """Extract project name from directory name.

    Claude Code encodes paths as: -Users-username-Projects-myproject
    This extracts the meaningful project name regardless of username.
    """
    # Remove the leading user home path prefix
    # Pattern: -Users-<username>-Projects-<project> or -Users-<username>-<path>
    import re as _re
    # Strip leading -Users-<anything>-Projects-
    cleaned = _re.sub(r'^-Users-[^-]+-Projects-', '', dir_name)
    if cleaned == dir_name:
        # Try just -Users-<anything>-
        cleaned = _re.sub(r'^-Users-[^-]+-', '', dir_name)
    if cleaned == dir_name:
        # No match, just use as-is
        cleaned = dir_name
    return cleaned.replace("-", "/")


def find_conversation_files(project_filter=None, top_n=None, scan_all=True):
    """Find all conversation JSONL files.

    Scans ~/.claude/projects/ which contains all conversation history
    organized by project directory name.
    """
    files = []
    for jsonl in PROJECTS_DIR.glob("**/*.jsonl"):
        # Skip subagent files unless we want everything
        if "subagent" in str(jsonl):
            continue
        project = extract_project_name(jsonl.parent.name)
        if project_filter and project_filter.lower() not in project.lower():
            continue
        size = jsonl.stat().st_size
        # Skip tiny files (< 1KB, probably empty/corrupt)
        if size < 1024:
            continue
        files.append({"path": jsonl, "project": project, "size": size})

    files.sort(key=lambda f: f["size"], reverse=True)
    if top_n and not scan_all:
        files = files[:top_n]
    return files


def parse_conversation(filepath):
    """Parse a conversation JSONL into structured entries."""
    entries = []
    with open(filepath) as f:
        for line in f:
            try:
                d = json.loads(line)
                if d.get("type") == "user" and "message" in d:
                    content = d["message"].get("content", "")
                    if isinstance(content, list):
                        text = " ".join(
                            c.get("text", "") for c in content
                            if isinstance(c, dict) and c.get("type") == "text"
                        )
                    else:
                        text = str(content)
                    entries.append({
                        "role": "user",
                        "text": text.strip(),
                        "len": len(text.strip()),
                    })

                elif d.get("type") == "assistant" and "message" in d:
                    msg = d["message"]
                    content = msg.get("content", [])
                    thinking_text = ""
                    response_text = ""
                    tool_uses = []

                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict):
                                if c.get("type") == "thinking":
                                    thinking_text += c.get("thinking", "")
                                elif c.get("type") == "text":
                                    response_text += c.get("text", "")
                                elif c.get("type") == "tool_use":
                                    tool_uses.append(c.get("name", "unknown"))

                    usage = msg.get("usage", {})
                    entries.append({
                        "role": "assistant",
                        "text": response_text.strip(),
                        "thinking": thinking_text,
                        "len": len(response_text.strip()),
                        "thinking_len": len(thinking_text),
                        "tools": tool_uses,
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "cache_read": usage.get("cache_read_input_tokens", 0),
                        "cache_creation": usage.get("cache_creation_input_tokens", 0),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
    return entries


def build_interaction_pairs(entries):
    """Build user→AI pairs from conversation entries."""
    pairs = []
    for i in range(len(entries) - 1):
        if entries[i]["role"] == "user" and entries[i+1]["role"] == "assistant":
            pairs.append({"user": entries[i], "ai": entries[i+1]})
    return pairs


def classify_user_response(text):
    """Classify how the user responds after AI output."""
    lower = text.strip().lower()
    clean = re.sub(r"[!.,?'\s]+$", "", lower)

    if clean in REACTIVE_WORDS or len(text.strip()) < 8:
        return "accept"
    if any(re.match(p, lower) for p in CORRECTION_PATTERNS):
        return "correct"
    if "?" in text and len(text) < 80:
        return "question"
    if len(text) > 150:
        return "redirect"  # substantial new input
    return "continue"


def analyze_conversation_dynamics(all_pairs):
    """Analyze the back-and-forth dynamics."""
    dynamics = {}

    if not all_pairs:
        return dynamics

    # --- Accept/Correct ratio ---
    response_types = Counter()
    for i in range(len(all_pairs)):
        rtype = classify_user_response(all_pairs[i]["user"]["text"])
        response_types[rtype] += 1

    dynamics["response_types"] = dict(response_types)
    total = sum(response_types.values())
    dynamics["accept_rate"] = round(response_types.get("accept", 0) * 100 / total, 1) if total else 0
    dynamics["correct_rate"] = round(response_types.get("correct", 0) * 100 / total, 1) if total else 0
    dynamics["redirect_rate"] = round(response_types.get("redirect", 0) * 100 / total, 1) if total else 0

    # --- Input/Output volume ---
    user_chars = sum(p["user"]["len"] for p in all_pairs)
    ai_chars = sum(p["ai"]["len"] for p in all_pairs)
    ai_thinking = sum(p["ai"]["thinking_len"] for p in all_pairs)
    dynamics["volume"] = {
        "user_chars": user_chars,
        "ai_response_chars": ai_chars,
        "ai_thinking_chars": ai_thinking,
        "ratio": round(ai_chars / user_chars, 1) if user_chars else 0,
        "thinking_to_response_ratio": round(ai_thinking / ai_chars, 1) if ai_chars else 0,
    }

    # --- Input length distribution ---
    input_lengths = [p["user"]["len"] for p in all_pairs]
    short = sum(1 for l in input_lengths if l < 50)
    medium = sum(1 for l in input_lengths if 50 <= l < 200)
    long = sum(1 for l in input_lengths if l >= 200)
    dynamics["input_distribution"] = {
        "short_under_50": {"count": short, "pct": round(short * 100 / len(all_pairs), 1)},
        "medium_50_200": {"count": medium, "pct": round(medium * 100 / len(all_pairs), 1)},
        "long_200_plus": {"count": long, "pct": round(long * 100 / len(all_pairs), 1)},
    }

    # --- How AI response size changes with your input ---
    by_input_size = defaultdict(list)
    for p in all_pairs:
        if p["user"]["len"] < 50:
            by_input_size["short"].append(p)
        elif p["user"]["len"] < 200:
            by_input_size["medium"].append(p)
        else:
            by_input_size["long"].append(p)

    dynamics["ai_response_by_input_size"] = {}
    for size, pairs in by_input_size.items():
        if pairs:
            dynamics["ai_response_by_input_size"][size] = {
                "avg_ai_response": round(sum(p["ai"]["len"] for p in pairs) / len(pairs)),
                "avg_ai_thinking": round(sum(p["ai"]["thinking_len"] for p in pairs) / len(pairs)),
                "avg_tools_used": round(sum(len(p["ai"]["tools"]) for p in pairs) / len(pairs), 1),
            }

    # --- Tool usage ---
    tool_counts = Counter()
    for p in all_pairs:
        tool_counts.update(p["ai"]["tools"])
    dynamics["tool_usage"] = dict(tool_counts.most_common(15))
    dynamics["total_tool_calls"] = sum(tool_counts.values())

    # --- Consecutive accept streaks ---
    max_accept_streak = 0
    current_streak = 0
    accept_streaks = []
    for p in all_pairs:
        rtype = classify_user_response(p["user"]["text"])
        if rtype == "accept":
            current_streak += 1
        else:
            if current_streak >= 2:
                accept_streaks.append(current_streak)
            max_accept_streak = max(max_accept_streak, current_streak)
            current_streak = 0
    if current_streak >= 2:
        accept_streaks.append(current_streak)
        max_accept_streak = max(max_accept_streak, current_streak)

    dynamics["accept_streaks"] = {
        "max_consecutive_accepts": max_accept_streak,
        "streaks_of_3_plus": sum(1 for s in accept_streaks if s >= 3),
        "streaks_of_5_plus": sum(1 for s in accept_streaks if s >= 5),
        "total_msgs_in_streaks": sum(accept_streaks),
    }

    # --- Token usage ---
    total_input_tokens = sum(p["ai"].get("input_tokens", 0) for p in all_pairs)
    total_output_tokens = sum(p["ai"].get("output_tokens", 0) for p in all_pairs)
    dynamics["tokens"] = {
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd": round(total_input_tokens * 0.003 / 1000 + total_output_tokens * 0.015 / 1000, 2),
    }

    # --- AI thinking patterns ---
    thinking_entries = [p for p in all_pairs if p["ai"]["thinking_len"] > 0]
    if thinking_entries:
        dynamics["ai_thinking"] = {
            "messages_with_thinking": len(thinking_entries),
            "pct_with_thinking": round(len(thinking_entries) * 100 / len(all_pairs), 1),
            "avg_thinking_length": round(sum(p["ai"]["thinking_len"] for p in thinking_entries) / len(thinking_entries)),
            "max_thinking_length": max(p["ai"]["thinking_len"] for p in thinking_entries),
            "short_thinks_under_500": sum(1 for p in thinking_entries if p["ai"]["thinking_len"] < 500),
            "deep_thinks_over_2k": sum(1 for p in thinking_entries if p["ai"]["thinking_len"] >= 2000),
        }

    return dynamics


def analyze_your_patterns(all_pairs):
    """Extract patterns unique to how you interact with AI."""
    patterns = {}

    user_texts = [p["user"]["text"] for p in all_pairs]
    lowers = [t.lower() for t in user_texts]

    # --- Framing analysis ---
    possibility = sum(1 for l in lowers if "is there a way" in l or "a way to" in l)
    permission = sum(1 for l in lowers if l.startswith("can you") or l.startswith("can we"))
    command = sum(1 for l in lowers if any(l.startswith(w) for w in ["make ", "add ", "fix ", "change ", "update ", "remove ", "create "]))
    intent = sum(1 for l in lowers if any(l.startswith(w) for w in ["i want", "i need", "i'd like"]))

    patterns["framing_style"] = {
        "possibility_framing": {"count": possibility, "example": "is there a way to..."},
        "permission_asking": {"count": permission, "example": "can you/we..."},
        "direct_command": {"count": command, "example": "make/add/fix..."},
        "intent_statement": {"count": intent, "example": "I want/need..."},
    }

    # --- Question depth ---
    questions = [l for l in lowers if "?" in l]
    surface_q = sum(1 for q in questions if len(q) < 40)
    deep_q = sum(1 for q in questions if len(q) >= 100 and "?" in q)
    patterns["question_depth"] = {
        "total_questions": len(questions),
        "surface_questions_under_40": surface_q,
        "deep_questions_over_100": deep_q,
        "depth_ratio": round(deep_q / len(questions), 2) if questions else 0,
    }

    # --- Multi-sentence inputs (structured thinking) ---
    multi_sentence = [t for t in user_texts if len(re.findall(r'[.!?]+\s+[A-Z]', t)) >= 2]
    patterns["structured_inputs"] = {
        "multi_sentence_messages": len(multi_sentence),
        "pct": round(len(multi_sentence) * 100 / len(user_texts), 1) if user_texts else 0,
    }

    # --- Context references ---
    context_refs = sum(1 for l in lowers if any(w in l for w in
        ["earlier", "before", "previously", "we discussed", "you said", "you mentioned", "last time", "remember", "we talked"]))
    patterns["context_awareness"] = {
        "references_to_prior_context": context_refs,
        "pct": round(context_refs * 100 / len(user_texts), 1) if user_texts else 0,
    }

    # --- What triggers corrections ---
    # Find the user message right before a correction
    correction_contexts = []
    for i in range(1, len(all_pairs)):
        if classify_user_response(all_pairs[i]["user"]["text"]) == "correct":
            correction_contexts.append({
                "your_correction": all_pairs[i]["user"]["text"][:150],
                "ai_said_before": all_pairs[i-1]["ai"]["text"][:150] if i > 0 else "",
            })
    patterns["correction_contexts"] = correction_contexts[:10]

    # --- What you delegate vs own ---
    creates = sum(1 for l in lowers if any(w in l for w in ["can you write", "can you create", "can you build", "can you implement", "can you make"]))
    reviews = sum(1 for l in lowers if any(w in l for w in ["can you review", "can you check", "can you look at", "can you verify"]))
    self_did = sum(1 for l in lowers if any(w in l for w in ["i built", "i made", "i wrote", "i created", "i added", "i changed", "i fixed"]))
    patterns["delegation"] = {
        "asks_ai_to_create": creates,
        "asks_ai_to_review": reviews,
        "reports_own_work": self_did,
        "create_to_own_ratio": round(creates / max(1, self_did), 1),
    }

    return patterns


def generate_insights(dynamics, patterns):
    """Generate narrative insights from the analysis."""
    insights = []

    # Accept/correct insight
    accept_rate = dynamics.get("accept_rate", 0)
    correct_rate = dynamics.get("correct_rate", 0)
    if accept_rate > 80:
        insights.append({
            "type": "warning",
            "title": "Low Pushback Rate",
            "insight": f"You accept AI output {accept_rate}% of the time and correct only {correct_rate}%. "
                      f"This means AI is making most implementation decisions unchallenged.",
            "suggestion": "Try: After AI proposes something, ask 'what are the trade-offs?' or 'what's another approach?' "
                         "before accepting. Force yourself to evaluate at least one alternative.",
        })

    # Input size insight
    input_dist = dynamics.get("input_distribution", {})
    short_pct = input_dist.get("short_under_50", {}).get("pct", 0)
    if short_pct > 70:
        insights.append({
            "type": "pattern",
            "title": "Mostly Short Inputs",
            "insight": f"{short_pct}% of your messages are under 50 characters. Short inputs "
                      f"give AI maximum freedom to interpret your intent.",
            "suggestion": "For important decisions, write 2-3 sentences minimum. Include: what you want, "
                         "why, and any constraints. 'Add auth' vs 'Add JWT auth with refresh tokens, "
                         "store in httpOnly cookies, 15min expiry' produces very different results.",
        })

    # Accept streaks
    streaks = dynamics.get("accept_streaks", {})
    max_streak = streaks.get("max_consecutive_accepts", 0)
    if max_streak >= 5:
        insights.append({
            "type": "warning",
            "title": "Autopilot Streaks",
            "insight": f"Your longest streak of accepting AI output without meaningful input was "
                      f"{max_streak} messages in a row. You had {streaks.get('streaks_of_5_plus', 0)} "
                      f"streaks of 5+ consecutive accepts.",
            "suggestion": "Set a personal rule: never accept more than 3 AI outputs in a row without "
                         "adding specific input, asking a question, or stating a preference.",
        })

    # Framing style
    framing = patterns.get("framing_style", {})
    possibility = framing.get("possibility_framing", {}).get("count", 0)
    command = framing.get("direct_command", {}).get("count", 0)
    intent = framing.get("intent_statement", {}).get("count", 0)
    if possibility > (command + intent) * 2:
        insights.append({
            "type": "personality",
            "title": "Possibility Framer",
            "insight": f"You say 'is there a way to...' {possibility} times vs direct commands {command} times. "
                      f"You frame problems as open questions, which gives AI latitude to choose the approach.",
            "suggestion": "Swap 'is there a way to X?' for 'I want X. Here's how I think it should work: ...' "
                         "Same curiosity, but you set the frame instead of asking AI to set it.",
        })

    # Delegation ratio
    delegation = patterns.get("delegation", {})
    create_to_own = delegation.get("create_to_own_ratio", 0)
    if create_to_own > 3:
        insights.append({
            "type": "pattern",
            "title": "High Delegation Ratio",
            "insight": f"You ask AI to create things {delegation.get('asks_ai_to_create', 0)} times "
                      f"but reference your own work only {delegation.get('reports_own_work', 0)} times. "
                      f"Ratio: {create_to_own}:1.",
            "suggestion": "Try building the scaffold yourself, then ask AI to fill in specific parts. "
                         "You'll understand the code better and catch issues AI misses.",
        })

    # Volume ratio
    volume = dynamics.get("volume", {})
    ratio = volume.get("ratio", 0)
    if ratio > 2:
        insights.append({
            "type": "stat",
            "title": "AI Writes Way More Than You",
            "insight": f"AI outputs {ratio}x more text than you input. For every character you type, "
                      f"AI writes {ratio} characters.",
            "suggestion": "This isn't necessarily bad, but check: are those AI characters code you "
                         "understand, or boilerplate you'll never read?",
        })

    # Thinking depth
    thinking = dynamics.get("ai_thinking", {})
    if thinking:
        deep_thinks = thinking.get("deep_thinks_over_2k", 0)
        insights.append({
            "type": "stat",
            "title": "AI Thinking Patterns",
            "insight": f"AI used extended thinking in {thinking.get('pct_with_thinking', 0)}% of responses. "
                      f"{deep_thinks} were deep thinks (2k+ chars). "
                      f"Average thinking: {thinking.get('avg_thinking_length', 0):,} chars.",
        })

    return insights


def generate_deep_report(dynamics, patterns, insights, projects_analyzed, timeframe):
    """Generate the full deep analysis report."""
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "tool": "vibe-coding-wrapped-deep",
            "version": "0.1.0",
            "timeframe": timeframe,
            "projects_analyzed": projects_analyzed,
        },
        "dynamics": dynamics,
        "patterns": patterns,
        "insights": insights,
    }


def generate_deep_wrapped(dynamics, patterns, insights, projects_analyzed, timeframe):
    """Generate the deep analysis markdown."""
    lines = []
    lines.append("# Vibe Coding Wrapped — Deep Analysis")
    lines.append("")
    lines.append(f"*{timeframe.get('label', 'all time')} | {len(projects_analyzed)} projects analyzed*")
    lines.append("")

    # Accept/Correct headline
    lines.append("## The Big Number")
    lines.append("")
    accept = dynamics.get("accept_rate", 0)
    correct = dynamics.get("correct_rate", 0)
    lines.append(f"**{accept}%** of AI outputs accepted without pushback")
    lines.append(f"**{correct}%** corrected")
    lines.append("")

    # Volume
    vol = dynamics.get("volume", {})
    lines.append("## Who's Writing More?")
    lines.append(f"- You typed: **{vol.get('user_chars', 0):,}** characters")
    lines.append(f"- AI responded: **{vol.get('ai_response_chars', 0):,}** characters")
    lines.append(f"- AI thought: **{vol.get('ai_thinking_chars', 0):,}** characters")
    lines.append(f"- Ratio: **{vol.get('ratio', 0)}x** AI output per your input")
    lines.append("")

    # Input distribution
    inp = dynamics.get("input_distribution", {})
    lines.append("## Your Input Size")
    for key, data in inp.items():
        label = key.replace("_", " ").replace("short under 50", "Short (<50 chars)").replace("medium 50 200", "Medium (50-200)").replace("long 200 plus", "Long (200+)")
        lines.append(f"- {label}: **{data.get('pct', 0)}%** ({data.get('count', 0)})")
    lines.append("")

    # Accept streaks
    streaks = dynamics.get("accept_streaks", {})
    lines.append("## Autopilot Streaks")
    lines.append(f"- Longest consecutive accepts: **{streaks.get('max_consecutive_accepts', 0)}**")
    lines.append(f"- Streaks of 3+: **{streaks.get('streaks_of_3_plus', 0)}**")
    lines.append(f"- Streaks of 5+: **{streaks.get('streaks_of_5_plus', 0)}**")
    lines.append("")

    # Tool usage
    tools = dynamics.get("tool_usage", {})
    if tools:
        lines.append("## What AI Does For You")
        for tool, count in list(tools.items())[:8]:
            lines.append(f"- **{tool}**: {count} calls")
        lines.append("")

    # Thinking
    thinking = dynamics.get("ai_thinking", {})
    if thinking:
        lines.append("## AI Thinking Depth")
        lines.append(f"- Thinks before responding: **{thinking.get('pct_with_thinking', 0)}%** of the time")
        lines.append(f"- Average thinking: **{thinking.get('avg_thinking_length', 0):,}** chars")
        lines.append(f"- Deep thinks (2k+): **{thinking.get('deep_thinks_over_2k', 0)}**")
        lines.append("")

    # Framing
    framing = patterns.get("framing_style", {})
    if framing:
        lines.append("## How You Frame Requests")
        for style, data in framing.items():
            label = style.replace("_", " ").title()
            lines.append(f"- {label}: **{data.get('count', 0)}** ({data.get('example', '')})")
        lines.append("")

    # Per-project breakdown
    project_breakdowns = patterns.get("project_breakdowns", [])
    if project_breakdowns:
        lines.append("## Per-Project Breakdown")
        lines.append("")
        lines.append(f"| Project | Interactions | Accept% | Max Autopilot | Short Input% | AI:You |")
        lines.append(f"|---------|-------------|---------|---------------|-------------|--------|")
        for pb in project_breakdowns[:15]:
            lines.append(
                f"| {pb['project'][:20]} | {pb['interactions']} | {pb['accept_rate']}% | "
                f"{pb['max_autopilot_streak']} | {pb['short_input_pct']}% | {pb['ai_to_user_ratio']}x |"
            )
        lines.append("")

    # Insights
    if insights:
        lines.append("## Insights & Suggestions")
        lines.append("")
        for insight in insights:
            icon = {"warning": "!!", "pattern": ">>", "personality": "**", "stat": "##"}.get(insight["type"], "")
            lines.append(f"### {icon} {insight['title']}")
            lines.append(insight["insight"])
            if "suggestion" in insight:
                lines.append(f"")
                lines.append(f"*Suggestion: {insight['suggestion']}*")
            lines.append("")

    # Tokens/Cost
    tokens = dynamics.get("tokens", {})
    if tokens:
        lines.append("## Token Usage")
        lines.append(f"- Input tokens: **{tokens.get('total_input_tokens', 0):,}**")
        lines.append(f"- Output tokens: **{tokens.get('total_output_tokens', 0):,}**")
        lines.append(f"- Estimated cost: **${tokens.get('estimated_cost_usd', 0):.2f}**")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by [Vibe Coding Wrapped](https://github.com/vibe-coding-wrapped) — Deep Analysis*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Vibe Coding Wrapped — Deep conversation analysis")
    parser.add_argument("--all", action="store_true", help="Analyze all-time history")
    parser.add_argument("--since", type=str, help="Analyze since date (YYYY-MM-DD)")
    parser.add_argument("--last", type=str, help="Analyze last N days (e.g., 30d, 90d)")
    parser.add_argument("--project", type=str, help="Filter to specific project")
    parser.add_argument("--top", type=int, default=15, help="Analyze top N projects by size (default: 15)")
    parser.add_argument("--output", type=str, default=".", help="Output directory")
    args = parser.parse_args()

    # Timeframe
    now = datetime.now()
    if args.all:
        timeframe_label = "all time"
    elif args.since:
        timeframe_label = f"since {args.since}"
    elif args.last:
        days = int(args.last.rstrip("d"))
        timeframe_label = f"last {days} days"
    else:
        timeframe_label = "all time"
        args.all = True

    timeframe = {"label": timeframe_label}

    print(f"Deep analyzing {timeframe_label}...")

    # Find conversation files
    scan_all = not args.project  # scan everything unless filtering
    files = find_conversation_files(project_filter=args.project, top_n=args.top, scan_all=scan_all)
    if not files:
        print("No conversation files found.")
        sys.exit(1)

    total_size = sum(f["size"] for f in files)
    print(f"Found {len(files)} conversation files ({total_size / 1048576:.1f} MB)")

    # Parse all conversations, tracking per-project pairs
    all_pairs = []
    project_pairs = defaultdict(list)
    projects_analyzed = []
    seen_projects = set()
    for i, f in enumerate(files):
        proj = f["project"]
        print(f"  [{i+1}/{len(files)}] {proj}... ({f['size'] / 1048576:.1f} MB)", end="", flush=True)
        entries = parse_conversation(f["path"])
        pairs = build_interaction_pairs(entries)
        all_pairs.extend(pairs)
        project_pairs[proj].extend(pairs)
        if proj not in seen_projects:
            projects_analyzed.append(proj)
            seen_projects.add(proj)
        print(f" → {len(pairs)} interactions")

    print(f"\nTotal interaction pairs: {len(all_pairs)}")

    # Analyze overall
    print("\nAnalyzing conversation dynamics...")
    dynamics = analyze_conversation_dynamics(all_pairs)

    print("Extracting your patterns...")
    patterns = analyze_your_patterns(all_pairs)

    # Per-project breakdown
    print("Analyzing per-project dynamics...")
    project_breakdowns = []
    for proj in projects_analyzed:
        pairs = project_pairs.get(proj, [])
        if len(pairs) < 5:
            continue
        proj_dynamics = analyze_conversation_dynamics(pairs)

        # Compute accept rate and key stats per project
        accept_rate = proj_dynamics.get("accept_rate", 0)
        vol = proj_dynamics.get("volume", {})
        streaks = proj_dynamics.get("accept_streaks", {})
        tools = proj_dynamics.get("tool_usage", {})
        inp = proj_dynamics.get("input_distribution", {})

        project_breakdowns.append({
            "project": proj,
            "interactions": len(pairs),
            "accept_rate": accept_rate,
            "correct_rate": proj_dynamics.get("correct_rate", 0),
            "ai_to_user_ratio": vol.get("ratio", 0),
            "user_chars": vol.get("user_chars", 0),
            "ai_chars": vol.get("ai_response_chars", 0),
            "ai_thinking_chars": vol.get("ai_thinking_chars", 0),
            "max_autopilot_streak": streaks.get("max_consecutive_accepts", 0),
            "streaks_5_plus": streaks.get("streaks_of_5_plus", 0),
            "short_input_pct": inp.get("short_under_50", {}).get("pct", 0),
            "top_tools": dict(Counter(tools).most_common(3)),
        })
    project_breakdowns.sort(key=lambda p: p["interactions"], reverse=True)
    patterns["project_breakdowns"] = project_breakdowns

    print("Generating insights...")
    insights = generate_insights(dynamics, patterns)

    # Output
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = generate_deep_report(dynamics, patterns, insights, projects_analyzed, timeframe)
    report_path = output_dir / "deep_analysis.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nDeep report: {report_path}")

    wrapped = generate_deep_wrapped(dynamics, patterns, insights, projects_analyzed, timeframe)
    wrapped_path = output_dir / "deep_wrapped.md"
    with open(wrapped_path, "w") as f:
        f.write(wrapped)
    print(f"Deep wrapped: {wrapped_path}")

    # Summary
    print(f"\n{'='*50}")
    print(f"  DEEP ANALYSIS")
    print(f"{'='*50}")
    print(f"  Accept rate: {dynamics.get('accept_rate', 0)}%")
    print(f"  Correct rate: {dynamics.get('correct_rate', 0)}%")
    vol = dynamics.get("volume", {})
    print(f"  AI:You ratio: {vol.get('ratio', 0)}x")
    streaks = dynamics.get("accept_streaks", {})
    print(f"  Max autopilot streak: {streaks.get('max_consecutive_accepts', 0)}")
    print(f"  Interactions: {len(all_pairs):,}")
    print(f"  Insights: {len(insights)}")
    print(f"{'='*50}")

    if insights:
        print("\n  Key Insights:")
        for insight in insights:
            print(f"  • {insight['title']}: {insight['insight'][:100]}...")


if __name__ == "__main__":
    main()
