import socket
import threading
import os
import traceback
from protocol import send_message, recv_message, get_content_type

PORT = 6676
SERVER = "196.42.113.37"
FORMAT = 'utf-8'
ADDR = (SERVER, PORT)
DISCONNECT_MESSAGE = "!DISCONNECTED"

# Directory where received files are saved
DOWNLOADS_DIR = "received_files"
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

#  LOGIN 
name = input("Enter your username: ").lower()
password = input("Enter your password: ")

send_message(client, "POST", "/login", {"FROM": name, "PASSWORD": password})
response = recv_message(client)

status = response["path"]
info = response["headers"].get("ERROR") or response["headers"].get("MESSAGE", "")
print(f"[Server]: {info}")

if "ERROR" in status:
    client.close()
    exit()

joined_groups = set()  # track groups this client has joined


def receive():
    while True:
        try:
            msg = recv_message(client)
            if not msg:
                break

            method = msg["method"]
            path = msg["path"]

            # server status response
            if method == "CHAT/1.0":
                info = msg["headers"].get("ERROR") or msg["headers"].get("MESSAGE", "")
                if info:
                    print(f"[Server {path}]: {info}")

            # incoming text message from another user
            elif method == "POST" and path == "/message":
                sender = msg["headers"].get("FROM", "?")
                target = msg["headers"].get("TARGET", "")
                body = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]
                tag = f"group:{target}" if target in joined_groups else sender
                print(f"[{tag}] {sender}: {body}")

            # incoming file (image / video / any binary) — save to disk
            elif method == "POST" and path == "/file":
                sender = msg["headers"].get("FROM", "?")
                target = msg["headers"].get("TARGET", "")
                content_type = msg["headers"].get("CONTENT-TYPE", "application/octet-stream")
                file_name = msg["headers"].get("FILE-NAME", "received_file")
                file_data = msg["body"]

                save_path = os.path.join(DOWNLOADS_DIR, file_name)
                # Avoid overwriting — prepend sender name if file exists
                if os.path.exists(save_path):
                    base, ext = os.path.splitext(file_name)
                    save_path = os.path.join(DOWNLOADS_DIR, f"{sender}_{base}{ext}")

                with open(save_path, "wb") as f:
                    f.write(file_data)

                tag = f"group:{target}" if target in joined_groups else sender
                print(f"[{tag}] {sender} sent a file: '{file_name}' ({content_type}, {len(file_data)} bytes) → saved to '{save_path}'")

        except Exception as e:
            print(f"[Receive Error]: {e}")
            traceback.print_exc()
            break


threading.Thread(target=receive, daemon=True).start()

print("\nCommands:")
print("  /join groupname              → join or create a group")
print("  /leave groupname             → leave a group")
print("  /file username filepath      → send a file/image/video to a user")
print("  /gfile groupname filepath    → send a file/image/video to a group")
print("  groupname: message           → send text to a group you've joined")
print("  username: message            → send text to a user")
print("  !DISCONNECTED                → logout and exit\n")

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

    # /file username path/to/file.png  — one-to-one file transfer
    elif msg.startswith("/file "):
        parts = msg[6:].strip().split(" ", 1)
        if len(parts) != 2:
            print("Usage: /file username filepath")
            continue
        target, filepath = parts[0].strip().lower(), parts[1].strip().strip("'\"")
        if not os.path.isfile(filepath):
            print(f"[Error]: File not found: '{filepath}'")
            continue
        file_name = os.path.basename(filepath)
        content_type = get_content_type(file_name)
        with open(filepath, "rb") as f:
            file_data = f.read()
        send_message(client, "POST", "/file", {
            "FROM": name,
            "TARGET": target,
            "CONTENT-TYPE": content_type,
            "FILE-NAME": file_name,
        }, file_data)
        print(f"[Client]: Sending '{file_name}' ({content_type}, {len(file_data)} bytes) to '{target}'...")

    # /gfile groupname path/to/file.png  — group file transfer
    elif msg.startswith("/gfile "):
        parts = msg[7:].strip().split(" ", 1)
        if len(parts) != 2:
            print("Usage: /gfile groupname filepath")
            continue
        target, filepath = parts[0].strip().lower(), parts[1].strip().strip("'\"")
        if target not in joined_groups:
            print(f"[Error]: You have not joined group '{target}'. Use /join first.")
            continue
        if not os.path.isfile(filepath):
            print(f"[Error]: File not found: '{filepath}'")
            continue
        file_name = os.path.basename(filepath)
        content_type = get_content_type(file_name)
        with open(filepath, "rb") as f:
            file_data = f.read()
        send_message(client, "POST", "/group-file", {
            "FROM": name,
            "TARGET": target,
            "CONTENT-TYPE": content_type,
            "FILE-NAME": file_name,
        }, file_data)
        print(f"[Client]: Sending '{file_name}' ({content_type}, {len(file_data)} bytes) to group '{target}'...")

    elif ": " in msg:
        target, content = msg.split(": ", 1)
        target = target.strip().lower()

        if target in joined_groups:
            send_message(client, "POST", "/group-message", {
                "FROM": name,
                "TARGET": target,
                "CONTENT-TYPE": "text"
            }, content)
        else:
            send_message(client, "POST", "/message", {
                "FROM": name,
                "TARGET": target,
                "CONTENT-TYPE": "text"
            }, content)
    else:
        print("Format:  username: message   or   groupname: message")