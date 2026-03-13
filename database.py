# DATABASE
# Hosted on your home server alongside server.py
# Uses SQLite — built into Python, no install needed
# Tables: users, messages

import sqlite3
import hashlib

DB_PATH = "chatapp.db"


def get_conn():
    """Get a thread-safe DB connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist. Call once on server startup."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    UNIQUE NOT NULL,
            password    TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id   INTEGER NOT NULL,
            target_id   INTEGER NOT NULL,
            content     TEXT,
            msg_type    TEXT    DEFAULT 'text',
            sent_at     TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (target_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Tables ready.")


# ── Password hashing ───────────────────────────────────────────────────────────

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# ── User functions ─────────────────────────────────────────────────────────────

def add_user(username, password):
    """Register a new user. Returns True on success, False if username taken."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username.lower(), hash_password(password))
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def check_user(username, password):
    """
    Returns:
      'ok'          — credentials correct
      'wrong_pass'  — username exists but password wrong
      'not_found'   — username doesn't exist
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT password FROM users WHERE username = ?",
        (username.lower(),)
    ).fetchone()
    conn.close()

    if row is None:
        return "not_found"
    if row["password"] == hash_password(password):
        return "ok"
    return "wrong_pass"


def get_user_id(username):
    """Get a user's numeric ID from their username."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (username.lower(),)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


def get_all_users():
    """Return a list of all registered usernames."""
    conn = get_conn()
    rows = conn.execute("SELECT username FROM users").fetchall()
    conn.close()
    return [r["username"] for r in rows]


# ── Message functions ──────────────────────────────────────────────────────────

def save_message(sender, target, content, msg_type="text"):
    """
    Save a message using sender/target usernames.
    Resolves usernames to IDs internally — server.py needs no changes.
    For group messages, target is the group name stored as a plain string.
    """
    sender_id = get_user_id(sender)

    if msg_type == "group":
        # Groups don't have a users.id — store sender_id twice as a placeholder
        # and rely on msg_type + content to identify group messages
        target_id = sender_id
    else:
        target_id = get_user_id(target)

    if sender_id is None or target_id is None:
        print(f"[DB] save_message failed — unknown user: {sender} or {target}")
        return

    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (sender_id, target_id, content, msg_type) VALUES (?, ?, ?, ?)",
        (sender_id, target_id, content, msg_type)
    )
    conn.commit()
    conn.close()


def get_conversation(user_a, user_b, limit=50):
    """
    Load the full conversation between two users when a contact is clicked.

    SELECT all messages where
      (sender = user_a AND target = user_b)
      OR (sender = user_b AND target = user_a)
    Ordered oldest -> newest, capped at limit.

    Returns a list of dicts ready to render in the UI:
      [{ sender, target, content, msg_type, sent_at }, ...]
    """
    id_a = get_user_id(user_a)
    id_b = get_user_id(user_b)

    if id_a is None or id_b is None:
        return []

    conn = get_conn()
    rows = conn.execute("""
        SELECT
            u_sender.username   AS sender,
            u_target.username   AS target,
            m.content,
            m.msg_type,
            m.sent_at
        FROM messages m
        JOIN users u_sender ON m.sender_id = u_sender.id
        JOIN users u_target ON m.target_id = u_target.id
        WHERE
            (m.sender_id = ? AND m.target_id = ?)
            OR
            (m.sender_id = ? AND m.target_id = ?)
        ORDER BY m.sent_at ASC
        LIMIT ?
    """, (id_a, id_b, id_b, id_a, limit)).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def get_group_conversation(group_name, limit=50):
    """
    Load all messages sent to a group when the group is clicked.

    SELECT all messages where msg_type = 'group' AND content target = group_name.
    Ordered oldest -> newest.

    Returns a list of dicts:
      [{ sender, group_name, content, sent_at }, ...]
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            u_sender.username   AS sender,
            m.content,
            m.sent_at
        FROM messages m
        JOIN users u_sender ON m.sender_id = u_sender.id
        WHERE m.msg_type = 'group'
          AND m.content LIKE ?
        ORDER BY m.sent_at ASC
        LIMIT ?
    """, (f"%{group_name}%", limit)).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def get_recent_contacts(username, limit=20):
    """
    Get the contacts a user has recently spoken to.
    Used to populate the sidebar/contact list in the UI on login.

    Returns usernames ordered by most recent message first:
      ["kylian", "kp", ...]
    """
    user_id = get_user_id(username)
    if user_id is None:
        return []

    conn = get_conn()
    rows = conn.execute("""
        SELECT DISTINCT
            CASE
                WHEN m.sender_id = ? THEN u_target.username
                ELSE u_sender.username
            END AS contact,
            MAX(m.sent_at) AS last_msg
        FROM messages m
        JOIN users u_sender ON m.sender_id = u_sender.id
        JOIN users u_target ON m.target_id = u_target.id
        WHERE (m.sender_id = ? OR m.target_id = ?)
          AND m.msg_type = 'text'
        GROUP BY contact
        ORDER BY last_msg DESC
        LIMIT ?
    """, (user_id, user_id, user_id, limit)).fetchall()
    conn.close()

    return [r["contact"] for r in rows]


# ── Run once to initialise ─────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()

    # Seed test users — run once then comment out
    add_user("tim",    "1234")
    add_user("kylian", "4567")
    add_user("kp",     "999")
    print("[DB] Seed users added.")
    print("[DB] All users:", get_all_users())