# DATABASE
# Stores all data locally in a JSON file — no server, no SQL, no installs needed
# File: chatapp_data.json
# Structure:
#   {
#     "users":    { "tim": "hashed_password", ... },
#     "messages": [ { sender, target, content, msg_type, sent_at }, ... ]
#   }

import json
import hashlib
import os
from datetime import datetime

DB_PATH = "chatapp_data.json"


# ── Core read/write ────────────────────────────────────────────────────────────

def load_db():
    """Read the JSON file and return the full data dict."""
    if not os.path.exists(DB_PATH):
        return {"users": {}, "messages": []}
    with open(DB_PATH, "r") as f:
        return json.load(f)


def save_db(data):
    """Write the full data dict back to the JSON file."""
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


def init_db():
    """Create the JSON file with empty structure if it doesn't exist."""
    if not os.path.exists(DB_PATH):
        save_db({"users": {}, "messages": []})
        print("[DB] Database created.")
    else:
        print("[DB] Database loaded.")


# ── Password hashing ───────────────────────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# ── User functions ─────────────────────────────────────────────────────────────

def add_user(username, password):
    """
    Register a new user.
    Returns True on success, False if username already exists.
    """
    data = load_db()
    if username.lower() in data["users"]:
        return False
    data["users"][username.lower()] = hash_password(password)
    save_db(data)
    return True


def check_user(username, password):
    """
    Check login credentials.
    Returns:
      'ok'          — credentials correct
      'wrong_pass'  — username exists but password wrong
      'not_found'   — username doesn't exist
    """
    data = load_db()
    username = username.lower()
    if username not in data["users"]:
        return "not_found"
    if data["users"][username] == hash_password(password):
        return "ok"
    return "wrong_pass"


def get_all_users():
    """Return a list of all registered usernames."""
    data = load_db()
    return list(data["users"].keys())


# ── Message functions ──────────────────────────────────────────────────────────

def save_message(sender, target, content, msg_type="text"):
    """
    Append a message to the messages list in the JSON file.
    Called by server.py every time a message is sent.
    """
    data = load_db()
    data["messages"].append({
        "sender":   sender.lower(),
        "target":   target.lower(),
        "content":  content,
        "msg_type": msg_type,
        "sent_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_db(data)


def get_conversation(user_a, user_b, limit=50):
    """
    Load the conversation between two users when a contact is clicked.

    Filters messages where:
      (sender == user_a AND target == user_b)
      OR (sender == user_b AND target == user_a)

    Returns the last `limit` messages, oldest first.
    Each message: { sender, target, content, msg_type, sent_at }
    """
    data   = load_db()
    user_a = user_a.lower()
    user_b = user_b.lower()

    filtered = [
        m for m in data["messages"]
        if m["msg_type"] == "text"
        and (
            (m["sender"] == user_a and m["target"] == user_b)
            or
            (m["sender"] == user_b and m["target"] == user_a)
        )
    ]

    return filtered[-limit:]


def get_group_conversation(group_name, limit=50):
    """
    Load all messages sent to a group when the group is clicked.

    Filters messages where:
      msg_type == 'group' AND target == group_name

    Returns the last `limit` messages, oldest first.
    Each message: { sender, target, content, msg_type, sent_at }
    """
    data       = load_db()
    group_name = group_name.lower()

    filtered = [
        m for m in data["messages"]
        if m["msg_type"] == "group"
        and m["target"] == group_name
    ]

    return filtered[-limit:]


def get_recent_contacts(username, limit=20):
    """
    Get the list of users that `username` has recently spoken to.
    Used to populate the sidebar/contact list in the UI on login.

    Looks through all text messages involving the user,
    collects the other party in each conversation,
    and returns them ordered by most recent message first.

    Returns a list of usernames: ["kylian", "kp", ...]
    """
    data     = load_db()
    username = username.lower()
    seen     = {}   # contact -> most recent sent_at

    for m in data["messages"]:
        if m["msg_type"] != "text":
            continue
        if m["sender"] == username:
            contact = m["target"]
        elif m["target"] == username:
            contact = m["sender"]
        else:
            continue
        seen[contact] = m["sent_at"]   # keeps updating to the latest

    sorted_contacts = sorted(seen, key=lambda c: seen[c], reverse=True)
    return sorted_contacts[:limit]


# ── Run once to initialise ─────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()

    # Seed test users — run once then comment out
    add_user("tim",    "1234")
    add_user("kylian", "4567")
    add_user("kp",     "999")
    print("[DB] Seed users added.")
    print("[DB] All users:", get_all_users())