# client file

import socket
import threading
import os
from protocol import send_message, recv_message

PORT = 5050
SERVER = "13.49.137.214"    # IP for AWS server
FORMAT = 'utf-8'
ADDR = (SERVER, PORT)
DISCONNECT_MESSAGE = "!DISCONNECT"


client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

# login
name     = input("Enter your username: ").lower()
password = input("Enter your password: ")

send_message(client, "POST", "/login", {"FROM": name, "PASSWORD": password})

response = recv_message(client)
status   = response["path"]
info     = response["headers"].get("ERROR") or response["headers"].get("MESSAGE", "")
print(f"[Server]: {info}")

if "ERROR" in status:
    client.close()
    exit()

joined_groups = set()  # track groups this client has joined


# FILE SEND — via TCP through server
def tcp_send_file(target, filepath):
    if not os.path.exists(filepath):
        print(f"[FILE] File not found: {filepath}")
        return

    filename = os.path.basename(filepath)

    with open(filepath, "rb") as f:
        data = f.read()

    print(f"[FILE] Sending '{filename}' to {target} ({len(data)} bytes)...")

    send_message(
        client, "POST", "/file",
        {
            "FROM":      name,
            "TARGET":    target,
            "FILE-NAME": filename,
        },
        data  # binary body sent over TCP
    )

    print(f"[FILE] Sent '{filename}' to {target}.")


# FILE RECEIVE — reassemble and save locally
def handle_incoming_file(msg):
    sender   = msg["headers"].get("FROM", "?")
    filename = msg["headers"].get("FILE-NAME", "received_file")
    data     = msg["body"]  # already complete — TCP guarantees full delivery

    save_path = f"received_{filename}"
    with open(save_path, "wb") as f:
        f.write(data)

    print(f"[FILE] Received '{filename}' from {sender} — saved as '{save_path}'.")


# SERVER TCP RECEIVE LOOP
def receive():
    while True:
        try:
            msg = recv_message(client)
            if not msg:
                break

            method = msg["method"]
            path   = msg["path"]

            if method == "CHAT/1.0":
                info = msg["headers"].get("ERROR") or msg["headers"].get("MESSAGE", "")
                if info:
                    print(f"[Server {path}]: {info}")

            elif method == "POST" and path == "/message":
                sender       = msg["headers"].get("FROM", "?")
                target       = msg["headers"].get("TARGET", "")
                content_type = msg["headers"].get("CONTENT-TYPE", "text")
                body         = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]

                tag = f"group:{target}" if target in joined_groups else sender
                print(f"[{tag}] {sender}: {body}")

            elif method == "POST" and path == "/file":
                # incoming file transfer relayed by server over TCP
                threading.Thread(
                    target=handle_incoming_file,
                    args=(msg,),
                    daemon=True
                ).start()

        except Exception:
            break


threading.Thread(target=receive, daemon=True).start()

# print commands
print("\nCommands:")
print("  /join groupname          --- join or create a group")
print("  /leave groupname         --- leave a group")
print("  groupname: message       --- send to a group you've joined")
print("  username: message        --- send to a user")
print("  /file username filepath  --- send a file to a user via TCP")
print("  !DISCONNECT            ---- logout and exit\n")

while True:
    msg = input()

    if msg == DISCONNECT_MESSAGE:
        send_message(client, "POST", "/logout", {"FROM": name})
        print("[Client]: Disconnected.")
        client.close()
        break

    elif msg.startswith("/join "):
        group_name = msg[6:].strip().lower()
        send_message(client, "POST", "/join", {"FROM": name, "TARGET": group_name})
        joined_groups.add(group_name)

    elif msg.startswith("/leave "):
        group_name = msg[7:].strip().lower()
        send_message(client, "POST", "/leave", {"FROM": name, "TARGET": group_name})
        joined_groups.discard(group_name)

    elif msg.startswith("/file "):
        # usage: /file username /path/to/file
        parts = msg[6:].strip().split(" ", 1)
        if len(parts) != 2:
            print("Usage: /file username filepath")
        else:
            target, filepath = parts
            threading.Thread(
                target=tcp_send_file,
                args=(target.lower(), filepath.strip()),
                daemon=True
            ).start()

    elif ": " in msg:
        target, content = msg.split(": ", 1)
        target = target.strip().lower()

        if target in joined_groups:
            send_message(client, "POST", "/group-message",
                         {"FROM": name, "TARGET": target, "CONTENT-TYPE": "text"}, content)
        else:
            send_message(client, "POST", "/message",
                         {"FROM": name, "TARGET": target, "CONTENT-TYPE": "text"}, content)
    else:
        print("Format:  username: message   or   groupname: message")