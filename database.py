# DATABASE
# Stores all data like chats, usernames, password and all message history locally in a .json no need for server or installs
# stores in chatapp_data.json in project directory
# .json structure:
#   {
#     "users":    { "tim": "hashed_password", ... },
#     "messages": [ {
# 
#  sender, target, content, msg_type, sent_at }, ... ]
#   }

import json
import hashlib
import os
from datetime import datetime

DB_PATH = "chatapp_data.json"


# main read/write functionality

def load_db():
    # read the full json file and return all data
    
    if not os.path.exists(DB_PATH):
        return {"users": {}, "messages": []}
    with open(DB_PATH, "r") as f:
        return json.load(f)


def save_db(data):
    # write the data dictionary back to the json file(ie for newly registered users)
    with open(DB_PATH, "w") as f:
        json.dump(data, f, indent=2)


def init_db():
    # cerate the json file (empty structure if it doesnt exist yet)
    if not os.path.exists(DB_PATH):
        save_db({"users": {}, "messages": []})
        print("[DB] Database created.")
    else:
        print("[DB] Database loaded.")


# hash password
# use SHA-256 hashing algorithm to securely store passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# functions for users

def add_user(username, password):
    # register a new user, return true if success and false if username is taken
    data = load_db()
    if username.lower() in data["users"]:
        return False
    data["users"][username.lower()] = hash_password(password)
    save_db(data)
    return True


def check_user(username, password):
  
    # check credentials for login check database 
    # returns 'ok' is correct, 'wrong_pass' for wrong password, 'not_found' for wrong usernames
    data = load_db()
    username = username.lower()
    if username not in data["users"]:
        return "not_found"
    if data["users"][username] == hash_password(password):
        return "ok"
    return "wrong_pass"


def get_all_users():
    # get list of all usernames to print 
    data = load_db()
    return list(data["users"].keys())


def save_message(sender, target, content, msg_type="text"):
 
    # add message to message list in the json file
    #called by server.py every time a message is send between clients or on a group
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
    
    #load the chat history between 2 clients or group when clicked on contact to message
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
    #load the chat history between 2 clients or group when clicked on contact to message
    data       = load_db()
    group_name = group_name.lower()

    filtered = [
        m for m in data["messages"]
        if m["msg_type"] == "group"
        and m["target"] == group_name
    ]

    return filtered[-limit:]


def get_recent_contacts(username, limit=20):
    # return list of users that username recently chatted with
    # used to fill in side bar on gui addition to not be empty space, like whatsapp
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


if __name__ == "__main__":
    init_db()

    # save test users —- our group members, already populate to database so its not empty 
    add_user("tim",    "1234")
    add_user("kylian", "6767")
    add_user("kp",     "999")
    print("[DB] Seed users added.")
    print("[DB] All users:", get_all_users())