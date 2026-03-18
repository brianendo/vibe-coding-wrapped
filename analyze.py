#!/usr/bin/env python3
"""
Vibe Coding Wrapped — Analyze your AI coding session patterns.

Parses Claude Code and Codex conversation history to measure
how much you're directing vs. vibe coding, your communication
personality, and how you interact with AI over time.

Usage:
    python3 analyze.py                    # Last 30 days
    python3 analyze.py --all              # All time
    python3 analyze.py --since 2025-12-01 # Since specific date
    python3 analyze.py --last 90d         # Last N days
"""

import json
import sqlite3
import sys
import re
import argparse
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from pathlib import Path

# --- Constants ---

CLAUDE_HISTORY = Path.home() / ".claude" / "history.jsonl"
CODEX_HISTORY = Path.home() / ".codex" / "history.jsonl"
CODEX_STATE_DB = Path.home() / ".codex" / "state_5.sqlite"

REACTIVE_WORDS = {
    "yes", "yeah", "ok", "okay", "sure", "yep", "y", "go", "yea",
    "do it", "lets do it", "let's do it", "go ahead", "looks good",
    "sounds good", "perfect", "nice", "cool", "great", "thanks",
    "thank you", "lgtm", "ship it", "continue", "proceed", "lets go",
    "let's go", "good", "fine", "right", "exactly", "correct", "agreed",
    "awesome", "sweet", "done", "got it", "makes sense",
}

CONSTRAINT_WORDS = [
    "don't", "dont", "do not", "instead", "must", "should not",
    "shouldn't", "never", "always", "make sure", "important", "require",
    "specifically", "exactly", "only if",
]

CORRECTION_PATTERNS = [
    r"^no[,.\s]", r"^wrong", r"^actually[,.\s]", r"^wait[,.\s]",
    r"^that's not", r"^that is not", r"^not that", r"^nah",
    r"^hold on", r"^stop", r"^scratch that",
]

TOPIC_KEYWORDS = {
    "building": ["implement", "create", "build", "add", "set up", "setup", "make", "write"],
    "debugging": ["error", "bug", "fix", "broken", "issue", "not working", "failed", "crash", "wrong", "undefined"],
    "thinking": ["brainstorm", "think", "idea", "approach", "strategy", "evaluate", "should i", "should we", "what if", "how should", "compare", "trade-off"],
    "exploring": ["show me", "explain", "what is", "how does", "why", "what does", "walk me through", "tell me about"],
    "deploying": ["deploy", "push", "ship", "launch", "production", "live", "publish", "release"],
    "refactoring": ["refactor", "clean up", "restructure", "reorganize", "rename", "simplify", "optimize"],
    "testing": ["test", "spec", "assert", "expect", "coverage", "mock", "stub"],
}

EMOTION_KEYWORDS = {
    "frustration": ["not working", "broken", "stuck", "frustrated", "annoying", "ugh", "wtf", "damn", "why is", "why isn't", "keeps", "still not"],
    "excitement": ["cool", "awesome", "love", "perfect", "amazing", "great", "nice", "sweet", "dope", "interesting", "exciting"],
    "uncertainty": ["maybe", "not sure", "i think", "probably", "might", "possibly", "idk", "i don't know", "wonder", "hmm"],
    "confidence": ["i know", "definitely", "clearly", "obviously", "for sure", "exactly", "must be", "certain"],
    "impatience": ["just", "quickly", "fast", "simple", "easy", "real quick", "hurry"],
}

STOP_WORDS = {
    "the", "a", "an", "is", "it", "to", "and", "of", "in", "for", "on",
    "that", "this", "with", "i", "you", "we", "can", "do", "my", "me",
    "be", "are", "was", "have", "has", "had", "not", "but", "or", "so",
    "if", "at", "by", "from", "up", "out", "as", "just", "like", "what",
    "how", "all", "about", "get", "make", "go", "no", "there", "its",
    "let", "would", "could", "should", "also", "use", "need", "want",
    "one", "see", "new", "way", "now", "some", "any", "when", "then",
    "here", "more", "than", "been", "will", "into", "each", "did",
}


# --- Message Scoring ---

def score_message(text, position_pct, session_length):
    """
    Score a message on 0-1 scale.
    0 = fully directed (you're driving)
    1 = fully vibing (AI is driving)
    """
    score = 0.5
    lower = text.strip().lower()
    clean = re.sub(r"[!.,?'\s]+$", "", lower)

    # Reactive/agreeing — almost fully vibing
    if clean in REACTIVE_WORDS:
        return 0.95

    # --- Vibe signals (increase score) ---

    # Very short messages
    if len(text.strip()) < 10:
        score += 0.25
    elif len(text.strip()) < 25:
        score += 0.15
    elif len(text.strip()) < 40:
        score += 0.05

    # Generic delegation without specifics
    if re.match(r"^can (you|we) ", lower) and len(text) < 60:
        score += 0.12

    # Open-ended possibility framing
    if "is there a way" in lower or "is there a method" in lower:
        score += 0.08

    # Short questions
    if "?" in text and len(text) < 50:
        score += 0.08

    # Slash commands (delegating to tools)
    if text.strip().startswith("/"):
        score += 0.15

    # --- Directed signals (decrease score) ---

    # Long, detailed messages
    if len(text.strip()) > 300:
        score -= 0.25
    elif len(text.strip()) > 150:
        score -= 0.15
    elif len(text.strip()) > 80:
        score -= 0.08

    # File/code references
    if re.search(r"[\w/]+\.\w{1,4}", text) and "/" in text:
        score -= 0.12
    if re.search(r"`[^`]+`", text):
        score -= 0.08
    if "[Pasted" in text or "pasted" in lower:
        score -= 0.12

    # Constraints and specifics
    constraint_count = sum(1 for w in CONSTRAINT_WORDS if w in lower)
    score -= min(0.2, constraint_count * 0.06)

    # Corrections
    if any(re.match(p, lower) for p in CORRECTION_PATTERNS):
        score -= 0.2

    # Specificity — numbers in context suggest precision
    if re.search(r"\d+", text) and len(text) > 40:
        score -= 0.05

    # Multiple sentences suggest thought
    sentence_count = len(re.findall(r"[.!?]+", text))
    if sentence_count >= 3:
        score -= 0.08

    # Lists or structured input
    if re.search(r"^\s*[-*\d]+[.)]\s", text, re.MULTILINE):
        score -= 0.1

    # Late-session penalty (same message is more "vibing" later)
    if position_pct > 0.8 and score > 0.4:
        score += 0.05

    return max(0.0, min(1.0, score))


def classify_message(text):
    """Classify message intent."""
    lower = text.strip().lower()
    clean = re.sub(r"[!.,?'\s]+$", "", lower)
    if clean in REACTIVE_WORDS or len(text.strip()) < 8:
        return "reactive"
    if "?" in text and len(text) < 80:
        return "question"
    return "directive"


def classify_topic(text):
    """Classify message topic."""
    lower = text.strip().lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return topic
    return "other"


# --- Data Loading ---

def extract_project_name(project_path):
    """Extract clean project name from full path.

    Works regardless of username — finds 'Projects' in the path
    and takes what follows.
    """
    parts = project_path.split("/")
    # Look for common project root markers
    for marker in ["Projects", "projects", "repos", "src", "code"]:
        try:
            idx = parts.index(marker)
            remaining = parts[idx + 1:]
            if remaining:
                return "/".join(remaining[:2])
        except ValueError:
            continue
    # Fallback: skip /Users/<username>/ prefix and take the rest
    if len(parts) > 3 and parts[1] == "Users":
        remaining = parts[3:]
        if remaining:
            return "/".join(remaining[:2])
    meaningful = [p for p in parts if p and p.lower() not in ("users", "home")]
    if meaningful:
        return meaningful[-1]
    return project_path


def load_claude_history(since_ts=None):
    """Load Claude Code history.jsonl."""
    messages = []
    if not CLAUDE_HISTORY.exists():
        return messages
    with open(CLAUDE_HISTORY) as f:
        for line in f:
            try:
                d = json.loads(line)
                ts = d.get("timestamp", 0)
                if since_ts and ts < since_ts:
                    continue
                msg = d.get("display", "").strip()
                if not msg:
                    continue
                messages.append({
                    "text": msg,
                    "timestamp": ts,
                    "project": extract_project_name(d.get("project", "unknown")),
                    "source": "claude_code",
                    "is_command": msg.startswith("/"),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return messages


def load_codex_history(since_ts=None):
    """Load Codex history.jsonl."""
    messages = []
    if not CODEX_HISTORY.exists():
        return messages
    with open(CODEX_HISTORY) as f:
        for line in f:
            try:
                d = json.loads(line)
                ts = d.get("timestamp", 0)
                if since_ts and ts < since_ts:
                    continue
                msg = d.get("display", "").strip()
                if not msg:
                    continue
                project = "unknown"
                if "project" in d:
                    project = extract_project_name(d["project"])
                elif "cwd" in d:
                    project = extract_project_name(d["cwd"])
                messages.append({
                    "text": msg,
                    "timestamp": ts,
                    "project": project,
                    "source": "codex",
                    "is_command": False,
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return messages


def load_codex_threads(since_ts=None):
    """Load Codex thread metadata from SQLite."""
    threads = []
    if not CODEX_STATE_DB.exists():
        return threads
    try:
        conn = sqlite3.connect(str(CODEX_STATE_DB))
        conn.row_factory = sqlite3.Row
        for row in conn.execute("SELECT * FROM threads ORDER BY created_at DESC"):
            created = row["created_at"]
            if since_ts and created < since_ts // 1000:
                continue
            threads.append({
                "id": row["id"],
                "title": row["title"],
                "cwd": row["cwd"],
                "project": extract_project_name(row["cwd"]),
                "created_at": created,
                "updated_at": row["updated_at"],
                "git_branch": row["git_branch"],
                "source": row["source"],
                "first_message": row["first_user_message"],
                "tokens_used": row["tokens_used"],
            })
        conn.close()
    except Exception as e:
        print(f"Warning: Could not read Codex DB: {e}", file=sys.stderr)
    return threads


# --- Session Analysis ---

def group_into_sessions(messages, gap_minutes=60):
    """Group messages into sessions by project + time gap."""
    messages.sort(key=lambda m: m["timestamp"])
    by_project_day = defaultdict(list)
    for msg in messages:
        dt = datetime.fromtimestamp(msg["timestamp"] / 1000)
        key = (msg["project"], dt.strftime("%Y-%m-%d"))
        by_project_day[key].append(msg)

    sessions = []
    for (project, date), msgs in by_project_day.items():
        current_session = [msgs[0]]
        for i in range(1, len(msgs)):
            gap = (msgs[i]["timestamp"] - msgs[i-1]["timestamp"]) / 60000
            if gap > gap_minutes:
                sessions.append({"project": project, "date": date, "messages": current_session})
                current_session = [msgs[i]]
            else:
                current_session.append(msgs[i])
        if current_session:
            sessions.append({"project": project, "date": date, "messages": current_session})
    return sessions


def compute_streaks(scores, threshold=0.6):
    """Find consecutive high-vibe (passive) streaks."""
    streaks = []
    current = 0
    for s in scores:
        if s >= threshold:
            current += 1
        else:
            if current >= 2:
                streaks.append(current)
            current = 0
    if current >= 2:
        streaks.append(current)
    return streaks


def analyze_session(session):
    """Analyze a single session."""
    msgs = session["messages"]
    n = len(msgs)
    if n == 0:
        return None

    scores = []
    classifications = []
    topics = []
    lengths = []
    gaps_sec = []

    for i, msg in enumerate(msgs):
        if msg.get("is_command"):
            continue
        pos = i / max(1, n - 1)
        score = score_message(msg["text"], pos, n)
        scores.append(score)
        classifications.append(classify_message(msg["text"]))
        topics.append(classify_topic(msg["text"]))
        lengths.append(len(msg["text"]))

        # Response time gap
        if i > 0:
            gap = (msg["timestamp"] - msgs[i-1]["timestamp"]) / 1000
            if 0 < gap < 3600:
                gaps_sec.append(gap)

    if not scores:
        return None

    # Engagement decay
    quarter = max(1, len(lengths) // 4)
    first_q_len = sum(lengths[:quarter]) / quarter
    last_q_len = sum(lengths[-quarter:]) / quarter
    first_q_vibe = sum(scores[:quarter]) / quarter
    last_q_vibe = sum(scores[-quarter:]) / quarter
    decay_ratio = last_q_len / first_q_len if first_q_len > 0 else 1.0
    vibe_drift = last_q_vibe - first_q_vibe

    # Streak analysis
    vibe_streaks = compute_streaks(scores, 0.6)
    max_vibe_streak = max(vibe_streaks) if vibe_streaks else 0
    total_streak_msgs = sum(vibe_streaks)

    # Response velocity
    avg_gap = sum(gaps_sec) / len(gaps_sec) if gaps_sec else 0
    snap_replies = sum(1 for g in gaps_sec if g < 15)
    thoughtful_replies = sum(1 for g in gaps_sec if g >= 60)

    # Classification and topic counts
    class_counts = Counter(classifications)
    topic_counts = Counter(topics)

    # Time info
    start_ts = msgs[0]["timestamp"]
    end_ts = msgs[-1]["timestamp"]
    duration_min = (end_ts - start_ts) / 60000
    start_dt = datetime.fromtimestamp(start_ts / 1000)

    # Correction rate
    correction_count = sum(1 for msg in msgs if not msg.get("is_command")
                          and any(re.match(p, msg["text"].strip().lower()) for p in CORRECTION_PATTERNS))

    return {
        "project": session["project"],
        "date": session["date"],
        "start_hour": start_dt.hour,
        "message_count": n,
        "duration_minutes": round(duration_min, 1),
        "vibe_score": round(sum(scores) / len(scores), 3),
        "first_quarter_vibe": round(first_q_vibe, 3),
        "last_quarter_vibe": round(last_q_vibe, 3),
        "vibe_drift": round(vibe_drift, 3),
        "first_quarter_avg_length": round(first_q_len, 1),
        "last_quarter_avg_length": round(last_q_len, 1),
        "engagement_decay": round(decay_ratio, 3),
        "max_vibe_streak": max_vibe_streak,
        "total_streak_msgs": total_streak_msgs,
        "streak_count": len(vibe_streaks),
        "avg_response_sec": round(avg_gap, 1),
        "snap_replies": snap_replies,
        "thoughtful_replies": thoughtful_replies,
        "correction_count": correction_count,
        "classifications": dict(class_counts),
        "topics": dict(topic_counts),
        "message_lengths": lengths,
        "scores": scores,
        "source": msgs[0].get("source", "unknown"),
    }


# --- Personality Profiling ---

def build_personality_profile(messages):
    """Build a deep personality profile from message content."""
    texts = [m["text"] for m in messages if not m.get("is_command")]
    lowers = [t.lower() for t in texts]
    total = len(texts)
    if total == 0:
        return {}

    profile = {}

    # --- Conversation Openers ---
    sessions = defaultdict(list)
    for m in messages:
        dt = datetime.fromtimestamp(m["timestamp"] / 1000)
        key = (m["project"], dt.strftime("%Y-%m-%d"))
        sessions[key].append(m)

    openers = [msgs[0]["text"].lower() for msgs in sessions.values() if msgs and not msgs[0].get("is_command")]
    opener_styles = Counter()
    for o in openers:
        if o.startswith("can you") or o.startswith("can we"):
            opener_styles["asks_permission"] += 1
        elif o.startswith("i want") or o.startswith("i need") or o.startswith("i'm"):
            opener_styles["states_intent"] += 1
        elif o.startswith("help") or "help me" in o:
            opener_styles["asks_for_help"] += 1
        elif o.startswith("how") or o.startswith("what") or o.startswith("why"):
            opener_styles["asks_question"] += 1
        elif o.startswith("let") or o.startswith("let's"):
            opener_styles["collaborative"] += 1
        elif "[pasted" in o:
            opener_styles["drops_context"] += 1
        else:
            opener_styles["direct_command"] += 1
    profile["opener_styles"] = dict(opener_styles)
    profile["total_sessions"] = len(openers)

    # --- Emotional Signals ---
    emotions = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        count = sum(1 for l in lowers if any(k in l for k in keywords))
        top_kws = Counter()
        for k in keywords:
            c = sum(1 for l in lowers if k in l)
            if c > 0:
                top_kws[k] = c
        emotions[emotion] = {
            "count": count,
            "pct": round(count * 100 / total, 1),
            "top_keywords": dict(top_kws.most_common(3)),
        }
    profile["emotions"] = emotions

    # --- Decision Making Style ---
    exploring = sum(1 for l in lowers if any(w in l for w in
        ["option", "alternative", "compare", "trade-off", "tradeoff", "pros and cons", "vs", "versus", "or should", "which is better"]))
    jumping = sum(1 for l in lowers if any(w in l for w in
        ["just do", "just make", "just add", "just use", "go with", "lets just", "let's just"]))
    deliberating = sum(1 for l in lowers if any(w in l for w in
        ["think about", "evaluate", "consider", "should we", "should i", "worth", "makes sense"]))
    profile["decision_style"] = {
        "explores_options": exploring,
        "jumps_to_solutions": jumping,
        "deliberates": deliberating,
        "style": "deliberator" if deliberating > jumping * 2 else
                 "jumper" if jumping > deliberating else "balanced",
    }

    # --- AI Relationship ---
    polite = sum(1 for l in lowers if any(w in l for w in ["please", "thanks", "thank you", "appreciate"]))
    collaborative = sum(1 for l in lowers if any(w in l for w in ["can we", "let's", "lets", "we should", "we need", "we can", "we're"]))
    commanding = sum(1 for l in lowers if any(w in l for w in ["do this", "make this", "fix this", "add this", "change this", "update this", "remove this"]))
    asks_opinion = sum(1 for l in lowers if any(w in l for w in ["what do you think", "do you think", "your opinion", "your thoughts", "you think", "recommend"]))

    profile["ai_relationship"] = {
        "polite": polite,
        "collaborative": collaborative,
        "commanding": commanding,
        "asks_ai_opinion": asks_opinion,
        "style": "collaborator" if collaborative > commanding * 3 else
                 "commander" if commanding > collaborative else "mixed",
    }

    # --- Framing Style ---
    possibility_framing = sum(1 for l in lowers if "is there a way" in l or "is there a method" in l or "a way to" in l)
    direct_framing = sum(1 for l in lowers if any(l.startswith(w) for w in ["i want", "i need", "make it", "change it", "set it"]))
    question_framing = sum(1 for l in lowers if "?" in l)

    profile["framing"] = {
        "possibility_framing": possibility_framing,
        "direct_framing": direct_framing,
        "questions_total": question_framing,
        "possibility_pct": round(possibility_framing * 100 / total, 1),
        "style": "explorer" if possibility_framing > direct_framing * 2 else
                 "commander" if direct_framing > possibility_framing else "balanced",
    }

    # --- Question Types ---
    questions = [l for l in lowers if "?" in l and len(l) > 15]
    q_types = Counter()
    for q in questions:
        first_part = q.split("?")[0][:15]
        if "how" in first_part:
            q_types["how_implementation"] += 1
        elif q.startswith("what") or "what " in q[:15]:
            q_types["what_information"] += 1
        elif q.startswith("why") or "why " in q[:15]:
            q_types["why_understanding"] += 1
        elif any(q.startswith(w) for w in ["is ", "are ", "do ", "does ", "can ", "could "]):
            q_types["yes_no_confirmation"] += 1
        elif "should" in q:
            q_types["should_decision"] += 1
        elif "which" in q:
            q_types["which_comparison"] += 1
        else:
            q_types["other"] += 1
    profile["question_types"] = dict(q_types)

    # --- Delegation Pattern ---
    delegation = Counter()
    for l in lowers:
        if any(w in l for w in ["can you write", "can you create", "can you build", "can you implement", "can you make"]):
            delegation["asks_ai_to_create"] += 1
        elif any(w in l for w in ["can you fix", "can you debug", "can you figure out"]):
            delegation["asks_ai_to_fix"] += 1
        elif any(w in l for w in ["can you explain", "can you show", "can you walk"]):
            delegation["asks_ai_to_explain"] += 1
        elif any(w in l for w in ["i built", "i made", "i wrote", "i created", "i added", "i changed", "i fixed"]):
            delegation["did_it_yourself"] += 1
        elif any(w in l for w in ["can you review", "can you check", "can you look", "can you verify"]):
            delegation["asks_ai_to_review"] += 1
        elif any(w in l for w in ["can you research", "can you find", "can you search"]):
            delegation["asks_ai_to_research"] += 1
    profile["delegation"] = dict(delegation)

    # --- Recurring Themes ---
    themes = {
        "making_money": ["revenue", "money", "monetize", "profit", "business", "pricing", "paying", "customer", "market", "sell"],
        "user_experience": ["user", "ux", "ui", "interface", "experience", "design", "looks", "feel", "clean", "beautiful"],
        "speed_performance": ["fast", "slow", "performance", "speed", "optimize", "efficient", "latency"],
        "data_analytics": ["data", "analytics", "metric", "track", "measure", "dashboard", "chart", "graph", "stats"],
        "architecture": ["architect", "structure", "pattern", "system design", "schema", "model", "framework"],
        "shipping": ["ship", "deploy", "launch", "release", "production", "live", "publish", "mvp"],
    }
    theme_counts = {}
    for theme, keywords in themes.items():
        count = sum(1 for l in lowers if any(k in l for k in keywords))
        theme_counts[theme] = {"count": count, "pct": round(count * 100 / total, 1)}
    profile["themes"] = theme_counts

    # --- Top Words ---
    words = Counter()
    for t in texts:
        for word in re.findall(r"\b\w+\b", t.lower()):
            if word not in STOP_WORDS and len(word) > 2:
                words[word] += 1
    profile["top_words"] = dict(words.most_common(20))

    # --- Top Phrases ---
    bigrams = Counter()
    for t in texts:
        ws = re.findall(r"\b\w+\b", t.lower())
        for i in range(len(ws) - 1):
            bg = f"{ws[i]} {ws[i+1]}"
            bigrams[bg] += 1
    generic_bigrams = {"can you", "i think", "can we", "do you", "is there", "it is",
                       "in the", "to the", "of the", "and the", "on the", "for the",
                       "at the", "with the", "we can", "we should", "let s", "need to",
                       "want to", "i want", "to make"}
    interesting_phrases = [(bg, c) for bg, c in bigrams.most_common(100)
                          if bg not in generic_bigrams and c > 8][:15]
    profile["top_phrases"] = dict(interesting_phrases)

    # --- Response Velocity ---
    sorted_msgs = sorted(messages, key=lambda m: m["timestamp"])
    gaps = []
    for i in range(1, len(sorted_msgs)):
        gap_sec = (sorted_msgs[i]["timestamp"] - sorted_msgs[i-1]["timestamp"]) / 1000
        if 0 < gap_sec < 3600:
            gaps.append({
                "gap_sec": gap_sec,
                "msg_len": len(sorted_msgs[i]["text"]),
            })

    if gaps:
        snap = [g for g in gaps if g["gap_sec"] < 15]
        quick = [g for g in gaps if 15 <= g["gap_sec"] < 60]
        thoughtful = [g for g in gaps if 60 <= g["gap_sec"] < 300]
        deep = [g for g in gaps if g["gap_sec"] >= 300]

        snap_avg_len = sum(g["msg_len"] for g in snap) / len(snap) if snap else 0
        deep_avg_len = sum(g["msg_len"] for g in thoughtful + deep) / len(thoughtful + deep) if thoughtful + deep else 0

        profile["response_velocity"] = {
            "snap_under_15s": {"count": len(snap), "pct": round(len(snap) * 100 / len(gaps), 1), "avg_msg_len": round(snap_avg_len)},
            "quick_15_60s": {"count": len(quick), "pct": round(len(quick) * 100 / len(gaps), 1)},
            "thoughtful_1_5m": {"count": len(thoughtful), "pct": round(len(thoughtful) * 100 / len(gaps), 1)},
            "deep_5m_plus": {"count": len(deep), "pct": round(len(deep) * 100 / len(gaps), 1), "avg_msg_len": round(deep_avg_len)},
        }

    # --- Usage Stats ---
    sorted_msgs = sorted(messages, key=lambda m: m["timestamp"])

    # Hour of day distribution
    hour_dist = Counter()
    for m in sorted_msgs:
        dt = datetime.fromtimestamp(m["timestamp"] / 1000)
        hour_dist[dt.hour] += 1
    profile["hour_distribution"] = {str(h): c for h, c in sorted(hour_dist.items())}

    # Weekday vs weekend
    weekday_msgs = 0
    weekend_msgs = 0
    weekday_days = set()
    weekend_days = set()
    for m in sorted_msgs:
        dt = datetime.fromtimestamp(m["timestamp"] / 1000)
        day_str = dt.strftime("%Y-%m-%d")
        if dt.weekday() < 5:
            weekday_msgs += 1
            weekday_days.add(day_str)
        else:
            weekend_msgs += 1
            weekend_days.add(day_str)
    profile["weekday_vs_weekend"] = {
        "weekday_messages": weekday_msgs,
        "weekend_messages": weekend_msgs,
        "weekday_days": len(weekday_days),
        "weekend_days": len(weekend_days),
        "weekday_pct": round(weekday_msgs * 100 / total, 1) if total else 0,
        "weekend_pct": round(weekend_msgs * 100 / total, 1) if total else 0,
        "avg_msgs_per_weekday": round(weekday_msgs / max(1, len(weekday_days)), 1),
        "avg_msgs_per_weekend_day": round(weekend_msgs / max(1, len(weekend_days)), 1),
    }

    # Day of week distribution
    dow_dist = Counter()
    for m in sorted_msgs:
        dt = datetime.fromtimestamp(m["timestamp"] / 1000)
        dow_dist[dt.strftime("%A")] += 1
    profile["day_of_week_distribution"] = dict(dow_dist.most_common())

    # Longest continuous session (based on message gaps)
    longest_session = {"duration_min": 0, "messages": 0, "project": "", "date": ""}
    current_session_start = sorted_msgs[0]["timestamp"] if sorted_msgs else 0
    current_session_msgs = 1
    current_project = sorted_msgs[0]["project"] if sorted_msgs else ""
    for i in range(1, len(sorted_msgs)):
        gap_min = (sorted_msgs[i]["timestamp"] - sorted_msgs[i-1]["timestamp"]) / 60000
        if gap_min < 30:  # 30 min gap = same session
            current_session_msgs += 1
        else:
            duration = (sorted_msgs[i-1]["timestamp"] - current_session_start) / 60000
            if duration > longest_session["duration_min"]:
                dt = datetime.fromtimestamp(current_session_start / 1000)
                longest_session = {
                    "duration_min": round(duration, 1),
                    "messages": current_session_msgs,
                    "project": current_project,
                    "date": dt.strftime("%Y-%m-%d"),
                    "start_time": dt.strftime("%H:%M"),
                }
            current_session_start = sorted_msgs[i]["timestamp"]
            current_session_msgs = 1
            current_project = sorted_msgs[i]["project"]
    # Check last session
    if sorted_msgs:
        duration = (sorted_msgs[-1]["timestamp"] - current_session_start) / 60000
        if duration > longest_session["duration_min"]:
            dt = datetime.fromtimestamp(current_session_start / 1000)
            longest_session = {
                "duration_min": round(duration, 1),
                "messages": current_session_msgs,
                "project": current_project,
                "date": dt.strftime("%Y-%m-%d"),
                "start_time": dt.strftime("%H:%M"),
            }
    profile["longest_session"] = longest_session

    # Average session duration (for sessions with 5+ messages)
    session_durations = []
    cur_start = sorted_msgs[0]["timestamp"] if sorted_msgs else 0
    cur_count = 1
    for i in range(1, len(sorted_msgs)):
        gap_min = (sorted_msgs[i]["timestamp"] - sorted_msgs[i-1]["timestamp"]) / 60000
        if gap_min < 30:
            cur_count += 1
        else:
            if cur_count >= 5:
                dur = (sorted_msgs[i-1]["timestamp"] - cur_start) / 60000
                session_durations.append(dur)
            cur_start = sorted_msgs[i]["timestamp"]
            cur_count = 1
    if cur_count >= 5 and sorted_msgs:
        dur = (sorted_msgs[-1]["timestamp"] - cur_start) / 60000
        session_durations.append(dur)

    if session_durations:
        profile["session_duration_stats"] = {
            "avg_minutes": round(sum(session_durations) / len(session_durations), 1),
            "median_minutes": round(sorted(session_durations)[len(session_durations) // 2], 1),
            "max_minutes": round(max(session_durations), 1),
            "total_sessions_measured": len(session_durations),
            "total_hours_with_ai": round(sum(session_durations) / 60, 1),
        }

    # --- Evolution Over Time ---
    if len(texts) > 100:
        mid = len(sorted_msgs) // 2
        first_half = [m for m in sorted_msgs[:mid] if not m.get("is_command")]
        second_half = [m for m in sorted_msgs[mid:] if not m.get("is_command")]

        f_texts = [m["text"] for m in first_half]
        s_texts = [m["text"] for m in second_half]
        f_lowers = [t.lower() for t in f_texts]
        s_lowers = [t.lower() for t in s_texts]

        mid_date = datetime.fromtimestamp(sorted_msgs[mid]["timestamp"] / 1000).strftime("%Y-%m-%d")

        f_avg_len = sum(len(t) for t in f_texts) / len(f_texts) if f_texts else 0
        s_avg_len = sum(len(t) for t in s_texts) / len(s_texts) if s_texts else 0

        f_uncertain = sum(1 for l in f_lowers if "i think" in l or "maybe" in l) / len(f_lowers) if f_lowers else 0
        s_uncertain = sum(1 for l in s_lowers if "i think" in l or "maybe" in l) / len(s_lowers) if s_lowers else 0

        f_collab = sum(1 for l in f_lowers if any(w in l for w in ["we can", "we should", "let's", "lets"])) / len(f_lowers) if f_lowers else 0
        s_collab = sum(1 for l in s_lowers if any(w in l for w in ["we can", "we should", "let's", "lets"])) / len(s_lowers) if s_lowers else 0

        f_questions = sum(1 for t in f_texts if "?" in t) / len(f_texts) if f_texts else 0
        s_questions = sum(1 for t in s_texts if "?" in t) / len(s_texts) if s_texts else 0

        profile["evolution"] = {
            "midpoint_date": mid_date,
            "avg_msg_length": {"before": round(f_avg_len), "after": round(s_avg_len),
                              "trend": "shorter" if s_avg_len < f_avg_len * 0.9 else "longer" if s_avg_len > f_avg_len * 1.1 else "stable"},
            "uncertainty": {"before_pct": round(f_uncertain * 100, 1), "after_pct": round(s_uncertain * 100, 1),
                           "trend": "more_uncertain" if s_uncertain > f_uncertain * 1.2 else "more_confident" if s_uncertain < f_uncertain * 0.8 else "stable"},
            "collaboration": {"before_pct": round(f_collab * 100, 1), "after_pct": round(s_collab * 100, 1),
                             "trend": "more_collaborative" if s_collab > f_collab * 1.2 else "less_collaborative" if s_collab < f_collab * 0.8 else "stable"},
            "questions": {"before_pct": round(f_questions * 100, 1), "after_pct": round(s_questions * 100, 1),
                         "trend": "asking_more" if s_questions > f_questions * 1.1 else "asking_less" if s_questions < f_questions * 0.9 else "stable"},
        }

    return profile


# --- Pattern Detection ---

def detect_patterns(sessions_analyzed, messages, codex_threads):
    """Find patterns in session data."""
    patterns = {}
    if not sessions_analyzed:
        return patterns

    substantial = [s for s in sessions_analyzed if s["message_count"] >= 10]

    # Best/worst sessions
    if substantial:
        best = sorted(substantial, key=lambda s: s["vibe_score"])[:5]
        worst = sorted(substantial, key=lambda s: s["vibe_score"], reverse=True)[:5]
        patterns["most_directed_sessions"] = [
            {"project": s["project"], "date": s["date"], "vibe_score": s["vibe_score"],
             "messages": s["message_count"], "duration_min": s["duration_minutes"],
             "max_vibe_streak": s["max_vibe_streak"]}
            for s in best
        ]
        patterns["most_vibed_sessions"] = [
            {"project": s["project"], "date": s["date"], "vibe_score": s["vibe_score"],
             "messages": s["message_count"], "duration_min": s["duration_minutes"],
             "max_vibe_streak": s["max_vibe_streak"]}
            for s in worst
        ]

        # Sessions with worst streaks
        streaky = sorted(substantial, key=lambda s: s["max_vibe_streak"], reverse=True)[:5]
        patterns["longest_autopilot_streaks"] = [
            {"project": s["project"], "date": s["date"], "streak_length": s["max_vibe_streak"],
             "messages": s["message_count"], "vibe_score": s["vibe_score"]}
            for s in streaky if s["max_vibe_streak"] >= 3
        ]

    # Peak hours
    hour_scores = defaultdict(list)
    hour_counts = defaultdict(int)
    for s in sessions_analyzed:
        hour_scores[s["start_hour"]].append(s["vibe_score"])
        hour_counts[s["start_hour"]] += 1
    peak_hours = {}
    for hour, scores in hour_scores.items():
        avg = sum(scores) / len(scores)
        peak_hours[str(hour)] = {
            "avg_vibe_score": round(avg, 3),
            "session_count": hour_counts[hour],
            "label": "directed" if avg < 0.45 else "vibing" if avg > 0.55 else "balanced",
        }
    patterns["hours"] = peak_hours

    # Engagement decay
    if substantial:
        decaying = [s for s in substantial if s["vibe_drift"] > 0.1]
        rising = [s for s in substantial if s["vibe_drift"] < -0.1]
        stable = [s for s in substantial if abs(s["vibe_drift"]) <= 0.1]
        patterns["engagement_trends"] = {
            "sessions_that_decay": len(decaying),
            "sessions_that_improve": len(rising),
            "sessions_that_stay_stable": len(stable),
            "decay_rate": round(len(decaying) / len(substantial), 2) if substantial else 0,
        }

    # Project patterns
    project_stats = defaultdict(lambda: {
        "sessions": 0, "total_messages": 0, "vibe_scores": [],
        "dates": set(), "topics": Counter(), "classifications": Counter(),
        "total_streaks": 0, "max_streak": 0, "corrections": 0,
    })
    for s in sessions_analyzed:
        p = project_stats[s["project"]]
        p["sessions"] += 1
        p["total_messages"] += s["message_count"]
        p["vibe_scores"].append(s["vibe_score"])
        p["dates"].add(s["date"])
        p["topics"].update(s["topics"])
        p["classifications"].update(s["classifications"])
        p["total_streaks"] += s["streak_count"]
        p["max_streak"] = max(p["max_streak"], s["max_vibe_streak"])
        p["corrections"] += s["correction_count"]

    projects = []
    for name, stats in project_stats.items():
        dates = sorted(stats["dates"])
        span = 0
        if len(dates) > 1:
            d1 = datetime.strptime(dates[0], "%Y-%m-%d")
            d2 = datetime.strptime(dates[-1], "%Y-%m-%d")
            span = (d2 - d1).days
        avg_vibe = sum(stats["vibe_scores"]) / len(stats["vibe_scores"])
        correction_rate = stats["corrections"] / stats["total_messages"] if stats["total_messages"] else 0
        projects.append({
            "name": name,
            "sessions": stats["sessions"],
            "total_messages": stats["total_messages"],
            "avg_vibe_score": round(avg_vibe, 3),
            "days_active": len(dates),
            "span_days": span,
            "first_seen": dates[0] if dates else None,
            "last_seen": dates[-1] if dates else None,
            "top_topics": dict(stats["topics"].most_common(3)),
            "classifications": dict(stats["classifications"]),
            "max_autopilot_streak": stats["max_streak"],
            "correction_rate": round(correction_rate, 3),
            "status": "sustained" if len(dates) >= 10 else "explored" if len(dates) >= 3 else "touched",
        })
    projects.sort(key=lambda p: p["total_messages"], reverse=True)
    patterns["projects"] = projects

    # Context switching
    day_projects = defaultdict(set)
    for s in sessions_analyzed:
        day_projects[s["date"]].add(s["project"])
    multi_project_days = sum(1 for d, ps in day_projects.items() if len(ps) > 1)
    total_days = len(day_projects)
    patterns["context_switching"] = {
        "multi_project_days": multi_project_days,
        "total_active_days": total_days,
        "switch_rate": round(multi_project_days / total_days, 2) if total_days else 0,
    }

    # Session length sweet spot
    if substantial:
        short = [s for s in substantial if s["message_count"] <= 20]
        medium = [s for s in substantial if 20 < s["message_count"] <= 50]
        long = [s for s in substantial if s["message_count"] > 50]
        patterns["session_length_impact"] = {
            "short_1_20": {
                "count": len(short),
                "avg_vibe": round(sum(s["vibe_score"] for s in short) / len(short), 3) if short else None,
            },
            "medium_21_50": {
                "count": len(medium),
                "avg_vibe": round(sum(s["vibe_score"] for s in medium) / len(medium), 3) if medium else None,
            },
            "long_50_plus": {
                "count": len(long),
                "avg_vibe": round(sum(s["vibe_score"] for s in long) / len(long), 3) if long else None,
            },
        }

    # Best vs worst comparison
    if substantial and len(substantial) >= 10:
        best_10 = sorted(substantial, key=lambda s: s["vibe_score"])[:10]
        worst_10 = sorted(substantial, key=lambda s: s["vibe_score"], reverse=True)[:10]

        best_topics = Counter()
        worst_topics = Counter()
        for s in best_10:
            best_topics.update(s.get("topics", {}))
        for s in worst_10:
            worst_topics.update(s.get("topics", {}))

        patterns["best_vs_worst"] = {
            "best_avg_msgs": round(sum(s["message_count"] for s in best_10) / 10),
            "worst_avg_msgs": round(sum(s["message_count"] for s in worst_10) / 10),
            "best_avg_hour": round(sum(s["start_hour"] for s in best_10) / 10, 1),
            "worst_avg_hour": round(sum(s["start_hour"] for s in worst_10) / 10, 1),
            "best_projects": dict(Counter(s["project"] for s in best_10)),
            "worst_projects": dict(Counter(s["project"] for s in worst_10)),
            "best_topics": dict(best_topics.most_common(3)),
            "worst_topics": dict(worst_topics.most_common(3)),
            "best_avg_drift": round(sum(s["vibe_drift"] for s in best_10) / 10, 3),
            "worst_avg_drift": round(sum(s["vibe_drift"] for s in worst_10) / 10, 3),
        }

    return patterns


# --- Fun Stats ---

def compute_fun_stats(messages, sessions_analyzed):
    """Compute shareable/fun statistics."""
    stats = {}
    if not messages:
        return stats

    texts = [m["text"] for m in messages if not m.get("is_command")]
    stats["total_messages"] = len(texts)
    stats["total_characters_typed"] = sum(len(t) for t in texts)
    stats["avg_message_length"] = round(sum(len(t) for t in texts) / len(texts), 1) if texts else 0

    # Reactive count
    reactive_count = sum(1 for t in texts if re.sub(r"[!.,?'\s]+$", "", t.strip().lower()) in REACTIVE_WORDS)
    stats["times_said_yes_ok_etc"] = reactive_count

    # Longest message
    longest = max(texts, key=len) if texts else ""
    stats["longest_message_chars"] = len(longest)
    stats["longest_message_preview"] = longest[:120] + "..." if len(longest) > 120 else longest

    # Directed streaks
    max_directed_streak = 0
    current_streak = 0
    for s in sessions_analyzed:
        for score in s.get("scores", []):
            if score < 0.4:
                current_streak += 1
                max_directed_streak = max(max_directed_streak, current_streak)
            else:
                current_streak = 0
    stats["longest_directed_streak"] = max_directed_streak

    # Vibe streaks
    max_vibe_streak = 0
    current_streak = 0
    for s in sessions_analyzed:
        for score in s.get("scores", []):
            if score >= 0.6:
                current_streak += 1
                max_vibe_streak = max(max_vibe_streak, current_streak)
            else:
                current_streak = 0
    stats["longest_vibe_streak"] = max_vibe_streak

    # Total corrections
    total_corrections = sum(s.get("correction_count", 0) for s in sessions_analyzed)
    stats["total_corrections"] = total_corrections
    stats["correction_rate"] = round(total_corrections * 100 / len(texts), 1) if texts else 0

    # Personality type (enhanced)
    if sessions_analyzed:
        overall_vibe = sum(s["vibe_score"] for s in sessions_analyzed) / len(sessions_analyzed)
        decay_sessions = sum(1 for s in sessions_analyzed if s.get("vibe_drift", 0) > 0.1)
        decay_rate = decay_sessions / len(sessions_analyzed)
        avg_streak = sum(s.get("max_vibe_streak", 0) for s in sessions_analyzed) / len(sessions_analyzed)

        if overall_vibe < 0.35:
            stats["personality"] = "The Architect"
            stats["personality_desc"] = "You drive your AI sessions with precision. Clear specs, specific constraints, and you push back when needed."
        elif overall_vibe < 0.42:
            stats["personality"] = "The Navigator"
            stats["personality_desc"] = "You guide with a clear destination but let AI help chart the route. Balanced control."
        elif overall_vibe < 0.48:
            stats["personality"] = "The Collaborator"
            stats["personality_desc"] = "You treat AI as a partner, not a tool. 'We' language, shared thinking, joint ownership of decisions."
        elif overall_vibe < 0.55:
            stats["personality"] = "The Explorer"
            stats["personality_desc"] = "Curious and open-ended. You let sessions go where they go. Great for discovery, risky for shipping."
        elif overall_vibe < 0.65:
            stats["personality"] = "The Delegator"
            stats["personality_desc"] = "You hand off significant work to AI. You know what you want but let AI figure out how."
        else:
            stats["personality"] = "The Viber"
            stats["personality_desc"] = "AI drives most of your sessions. Quick inputs, fast iteration, minimal personal ownership of decisions."

        # Subtraits
        subtraits = []
        if decay_rate > 0.4:
            subtraits.append({"name": "Fading Grip", "desc": "You start sessions strong but lose engagement over time."})
        elif decay_rate < 0.15:
            subtraits.append({"name": "Steady Hand", "desc": "Your engagement stays consistent throughout sessions."})

        if avg_streak > 3:
            subtraits.append({"name": "Autopilot Prone", "desc": f"You average {avg_streak:.1f}-message vibe streaks where AI runs without meaningful input."})
        elif avg_streak < 1:
            subtraits.append({"name": "Always Engaged", "desc": "You rarely let AI run on autopilot. Every step gets your input."})

        if total_corrections < len(texts) * 0.005:
            subtraits.append({"name": "Yes Person", "desc": f"You corrected AI only {total_corrections} times across {len(texts)} messages. You almost never push back."})
        elif total_corrections > len(texts) * 0.03:
            subtraits.append({"name": "Quality Gate", "desc": "You actively push back and correct AI. High standards for output."})

        stats["subtraits"] = subtraits

    # Projects and activity
    unique_projects = set(m["project"] for m in messages)
    stats["unique_projects"] = len(unique_projects)

    active_days = set()
    for m in messages:
        dt = datetime.fromtimestamp(m["timestamp"] / 1000)
        active_days.add(dt.strftime("%Y-%m-%d"))
    stats["active_days"] = len(active_days)

    dow_counts = Counter()
    for day_str in active_days:
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        dow_counts[dt.strftime("%A")] += 1
    stats["day_of_week"] = dict(dow_counts.most_common())

    return stats


# --- Output Generation ---

def generate_private_report(overall_vibe, sessions_analyzed, patterns, fun_stats, personality, messages, timeframe):
    """Generate the full private analysis JSON."""
    return {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "tool": "vibe-coding-wrapped",
            "version": "0.2.0",
            "timeframe": timeframe,
            "sources": list(set(m["source"] for m in messages)),
        },
        "overall": {
            "vibe_score": round(overall_vibe, 3),
            "vibe_pct": round(overall_vibe * 100),
            "directed_pct": round((1 - overall_vibe) * 100),
            "total_sessions": len(sessions_analyzed),
            "total_messages": fun_stats.get("total_messages", 0),
        },
        "personality": personality,
        "patterns": patterns,
        "fun_stats": fun_stats,
        "sessions": [
            {
                "project": s["project"],
                "date": s["date"],
                "start_hour": s["start_hour"],
                "messages": s["message_count"],
                "duration_min": s["duration_minutes"],
                "vibe_score": s["vibe_score"],
                "vibe_drift": s["vibe_drift"],
                "engagement_decay": s["engagement_decay"],
                "max_vibe_streak": s["max_vibe_streak"],
                "snap_replies": s["snap_replies"],
                "correction_count": s["correction_count"],
                "classifications": s["classifications"],
                "topics": s["topics"],
            }
            for s in sessions_analyzed
        ],
    }


def generate_public_wrapped(overall_vibe, fun_stats, patterns, personality, timeframe):
    """Generate the shareable wrapped markdown."""
    lines = []
    lines.append("# Vibe Coding Wrapped")
    lines.append("")
    lines.append(f"*{timeframe['start']} to {timeframe['end']}*")
    lines.append("")

    # Big number
    vibe_pct = round(overall_vibe * 100)
    directed_pct = 100 - vibe_pct
    lines.append(f"## Vibe Code Score: {vibe_pct}%")
    lines.append("")
    lines.append(f"**{directed_pct}%** directed | **{vibe_pct}%** vibing")
    lines.append("")

    # Personality
    if "personality" in fun_stats:
        lines.append(f"### Personality: {fun_stats['personality']}")
        lines.append(fun_stats.get("personality_desc", ""))
        lines.append("")
        if "subtraits" in fun_stats:
            for st in fun_stats["subtraits"]:
                lines.append(f"*{st['name']}* — {st['desc']}")
            lines.append("")

    # AI Relationship
    if "ai_relationship" in personality:
        rel = personality["ai_relationship"]
        lines.append("### How I Talk to AI")
        lines.append(f"- **{rel['collaborative']}** collaborative messages ('we', 'let\\'s')")
        lines.append(f"- **{rel['commanding']}** commands ('do this', 'fix this')")
        lines.append(f"- **{rel['asks_ai_opinion']}** times asked AI's opinion")
        lines.append(f"- **{rel['polite']}** times said please/thanks")
        style_label = {"collaborator": "Partner", "commander": "Boss", "mixed": "Mixed"}.get(rel["style"], rel["style"])
        lines.append(f"- Style: **{style_label}**")
        lines.append("")

    # Decision Style
    if "decision_style" in personality:
        ds = personality["decision_style"]
        lines.append("### Decision Style")
        lines.append(f"- Deliberated **{ds['deliberates']}** times")
        lines.append(f"- Explored options **{ds['explores_options']}** times")
        lines.append(f"- Jumped to solutions **{ds['jumps_to_solutions']}** times")
        style_label = {"deliberator": "Deliberator", "jumper": "Action-First", "balanced": "Balanced"}.get(ds["style"], ds["style"])
        lines.append(f"- Type: **{style_label}**")
        lines.append("")

    # Key stats
    lines.append("### By the Numbers")
    lines.append(f"- **{fun_stats.get('total_messages', 0):,}** messages sent to AI")
    lines.append(f"- **{fun_stats.get('total_characters_typed', 0):,}** characters typed")
    lines.append(f"- **{fun_stats.get('unique_projects', 0)}** projects touched")
    lines.append(f"- **{fun_stats.get('active_days', 0)}** days active")
    lines.append(f"- **{fun_stats.get('times_said_yes_ok_etc', 0)}** rubber stamps ('yes/ok/sure')")
    lines.append(f"- **{fun_stats.get('total_corrections', 0)}** times pushed back on AI")
    lines.append(f"- **{fun_stats.get('longest_directed_streak', 0)}** longest directed streak")
    lines.append(f"- **{fun_stats.get('longest_vibe_streak', 0)}** longest vibe streak")
    lines.append("")

    # Response Velocity
    if "response_velocity" in personality:
        rv = personality["response_velocity"]
        lines.append("### Response Speed")
        lines.append(f"- Snap replies (<15s): **{rv['snap_under_15s']['pct']}%**")
        lines.append(f"- Quick (15-60s): **{rv['quick_15_60s']['pct']}%**")
        lines.append(f"- Thoughtful (1-5m): **{rv['thoughtful_1_5m']['pct']}%**")
        lines.append(f"- Deep thought (5m+): **{rv['deep_5m_plus']['pct']}%**")
        lines.append("")

    # Usage Stats
    if "weekday_vs_weekend" in personality:
        ww = personality["weekday_vs_weekend"]
        lines.append("### When I Code with AI")
        lines.append(f"- Weekdays: **{ww['weekday_pct']}%** ({ww['weekday_messages']} msgs across {ww['weekday_days']} days)")
        lines.append(f"- Weekends: **{ww['weekend_pct']}%** ({ww['weekend_messages']} msgs across {ww['weekend_days']} days)")
        lines.append(f"- Avg per weekday: **{ww['avg_msgs_per_weekday']}** msgs | Avg per weekend day: **{ww['avg_msgs_per_weekend_day']}** msgs")
        lines.append("")

    if "session_duration_stats" in personality:
        sd = personality["session_duration_stats"]
        lines.append("### Session Stats")
        lines.append(f"- Average session: **{sd['avg_minutes']}** minutes")
        lines.append(f"- Median session: **{sd['median_minutes']}** minutes")
        lines.append(f"- Total hours with AI: **{sd['total_hours_with_ai']}** hours")
        lines.append("")

    if "longest_session" in personality and personality["longest_session"]["duration_min"] > 0:
        ls = personality["longest_session"]
        lines.append(f"### Longest Session")
        lines.append(f"- **{ls['duration_min']}** minutes on **{ls['project']}** ({ls['date']} at {ls.get('start_time', '??')})")
        lines.append(f"- {ls['messages']} messages")
        lines.append("")

    if "hour_distribution" in personality:
        hours = personality["hour_distribution"]
        if hours:
            peak_hour = max(hours, key=lambda h: hours[h])
            lines.append(f"### Peak Coding Hour")
            lines.append(f"- **{int(peak_hour)}:00** ({hours[peak_hour]} messages)")
            lines.append("")

    # Projects
    if "projects" in patterns:
        top_projects = patterns["projects"][:5]
        if top_projects:
            lines.append("### Top Projects")
            for p in top_projects:
                vibe_label = f"{round(p['avg_vibe_score'] * 100)}% vibed"
                streak_note = f", max {p['max_autopilot_streak']}-msg autopilot" if p["max_autopilot_streak"] >= 3 else ""
                lines.append(f"- **{p['name']}** — {p['total_messages']} msgs, {p['days_active']} days, {vibe_label}{streak_note}")
            lines.append("")

    # Engagement pattern
    if "engagement_trends" in patterns:
        et = patterns["engagement_trends"]
        lines.append("### Engagement Pattern")
        lines.append(f"- {et['sessions_that_decay']} sessions where I drifted passive")
        lines.append(f"- {et['sessions_that_improve']} sessions where I got MORE engaged")
        lines.append(f"- {et['sessions_that_stay_stable']} sessions that stayed steady")
        lines.append("")

    # Evolution
    if "evolution" in personality:
        evo = personality["evolution"]
        lines.append("### How I've Changed Over Time")
        lines.append(f"- Messages: **{evo['avg_msg_length']['trend']}** ({evo['avg_msg_length']['before']} → {evo['avg_msg_length']['after']} chars)")
        lines.append(f"- Uncertainty: **{evo['uncertainty']['trend']}** ({evo['uncertainty']['before_pct']}% → {evo['uncertainty']['after_pct']}%)")
        lines.append(f"- Collaboration: **{evo['collaboration']['trend']}** ({evo['collaboration']['before_pct']}% → {evo['collaboration']['after_pct']}%)")
        lines.append("")

    # Day of week
    if "day_of_week" in fun_stats:
        lines.append("### Most Active Days")
        for day, count in list(fun_stats["day_of_week"].items())[:3]:
            lines.append(f"- {day}: {count} days")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by [Vibe Coding Wrapped](https://github.com/vibe-coding-wrapped)*")

    return "\n".join(lines)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Vibe Coding Wrapped — Analyze your AI coding patterns")
    parser.add_argument("--all", action="store_true", help="Analyze all-time history")
    parser.add_argument("--since", type=str, help="Analyze since date (YYYY-MM-DD)")
    parser.add_argument("--last", type=str, help="Analyze last N days (e.g., 30d, 90d)")
    parser.add_argument("--output", type=str, default=".", help="Output directory")
    args = parser.parse_args()

    # Determine timeframe
    since_ts = None
    now = datetime.now()

    if args.all:
        timeframe_label = "all time"
    elif args.since:
        since_dt = datetime.strptime(args.since, "%Y-%m-%d")
        since_ts = int(since_dt.timestamp() * 1000)
        timeframe_label = f"since {args.since}"
    elif args.last:
        days = int(args.last.rstrip("d"))
        since_dt = now - timedelta(days=days)
        since_ts = int(since_dt.timestamp() * 1000)
        timeframe_label = f"last {days} days"
    else:
        since_dt = now - timedelta(days=30)
        since_ts = int(since_dt.timestamp() * 1000)
        timeframe_label = "last 30 days"

    print(f"Analyzing {timeframe_label}...")

    # Load data
    claude_msgs = load_claude_history(since_ts)
    codex_msgs = load_codex_history(since_ts)
    codex_threads = load_codex_threads(since_ts)

    all_messages = claude_msgs + codex_msgs
    all_messages.sort(key=lambda m: m["timestamp"])

    if not all_messages:
        print("No messages found in the specified timeframe.")
        sys.exit(1)

    first_ts = all_messages[0]["timestamp"]
    last_ts = all_messages[-1]["timestamp"]
    timeframe = {
        "start": datetime.fromtimestamp(first_ts / 1000).strftime("%Y-%m-%d"),
        "end": datetime.fromtimestamp(last_ts / 1000).strftime("%Y-%m-%d"),
        "label": timeframe_label,
    }

    print(f"Found {len(claude_msgs)} Claude Code messages, {len(codex_msgs)} Codex messages")
    print(f"Date range: {timeframe['start']} to {timeframe['end']}")

    # Group into sessions
    sessions = group_into_sessions(all_messages)
    print(f"Grouped into {len(sessions)} sessions")

    # Analyze each session
    sessions_analyzed = []
    for s in sessions:
        result = analyze_session(s)
        if result:
            sessions_analyzed.append(result)

    # Overall vibe score
    if sessions_analyzed:
        overall_vibe = sum(s["vibe_score"] for s in sessions_analyzed) / len(sessions_analyzed)
    else:
        overall_vibe = 0.5

    print(f"\nOverall Vibe Score: {round(overall_vibe * 100)}%")

    # Build personality profile
    print("Building personality profile...")
    personality = build_personality_profile(all_messages)

    # Detect patterns
    patterns = detect_patterns(sessions_analyzed, all_messages, codex_threads)

    # Fun stats
    fun_stats = compute_fun_stats(all_messages, sessions_analyzed)

    # Generate outputs
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Private report
    private_report = generate_private_report(overall_vibe, sessions_analyzed, patterns, fun_stats, personality, all_messages, timeframe)
    private_path = output_dir / "analysis_private.json"
    with open(private_path, "w") as f:
        json.dump(private_report, f, indent=2, default=str)
    print(f"\nPrivate report: {private_path}")

    # Public wrapped
    public_wrapped = generate_public_wrapped(overall_vibe, fun_stats, patterns, personality, timeframe)
    public_path = output_dir / "wrapped_public.md"
    with open(public_path, "w") as f:
        f.write(public_wrapped)
    print(f"Public wrapped: {public_path}")

    # Print summary
    print(f"\n{'='*50}")
    print(f"  VIBE CODING WRAPPED")
    print(f"{'='*50}")
    print(f"  Vibe Score: {round(overall_vibe * 100)}% vibing / {round((1-overall_vibe)*100)}% directed")
    if "personality" in fun_stats:
        print(f"  Personality: {fun_stats['personality']}")
    if "subtraits" in fun_stats:
        for st in fun_stats["subtraits"]:
            print(f"  Subtrait: {st['name']} — {st['desc']}")
    if "ai_relationship" in personality:
        style = personality["ai_relationship"]["style"]
        print(f"  AI Relationship: {style}")
    if "decision_style" in personality:
        style = personality["decision_style"]["style"]
        print(f"  Decision Style: {style}")
    print(f"  Messages: {fun_stats.get('total_messages', 0):,}")
    print(f"  Projects: {fun_stats.get('unique_projects', 0)}")
    print(f"  Active Days: {fun_stats.get('active_days', 0)}")
    print(f"  Corrections: {fun_stats.get('total_corrections', 0)}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
