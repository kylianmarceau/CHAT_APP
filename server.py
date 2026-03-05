import socket
import threading
import os
from protocol import send_message, recv_message

HEADER = 64
PORT = 6676
SERVER = "196.42.113.37"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECTED"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

clients = {}
groups = {}

# Lock protecting both clients and groups dicts
state_lock = threading.Lock()

# Directory where received files are saved server-side (forwarded copies)
FILES_DIR = "server_files"
os.makedirs(FILES_DIR, exist_ok=True)

users = {"tim": "1234", "kylian": "4567", "kp": "999"} #HARD CODE FOR NOW, DATABASE LATER ON
users_lock = threading.Lock()

def handle_client(conn, addr):
    name = None
    try:
        #  LOGIN 
        msg = recv_message(conn)
        name = msg["headers"].get("FROM", "").lower()
        password = msg["headers"].get("PASSWORD", "")

        # check credentials
        if name not in users:
            send_message(conn, "CHAT/1.0", "401 ERROR", {"ERROR": "Username incorrect."})
            conn.close()
            return

        if users[name] != password:
            send_message(conn, "CHAT/1.0", "401 ERROR", {"ERROR": "password incorrect."})
            conn.close()
            return

        if name in clients:
            send_message(conn, "CHAT/1.0", "409 ERROR", {"ERROR": "User already logged in."})
            conn.close()
            return

        clients[name] = conn
        print(f"[+] {name} connected from {addr}")
        send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Welcome {name}! Login successful."})

        
        while True:
            msg = recv_message(conn)
            if not msg:
                break

            path = msg["path"]
            sender = msg["headers"].get("FROM", "").lower()
            target = msg["headers"].get("TARGET", "").lower()
            body = msg["body"]  # keep as raw bytes
            # Only decode to text for text-based messages, not binary
            body_text = body.decode(FORMAT) if (
                isinstance(body, bytes) and
                msg["headers"].get("CONTENT-TYPE", "text") == "text"
            ) else body if isinstance(body, str) else ""

            # LOGOUT
            if path == "/logout":
                break

            # ONE-TO-ONE MESSAGE 
            elif path == "/message":
                with state_lock:
                    target_conn = clients.get(target)
                if target_conn:
                    send_message(target_conn, "POST", "/message", {
                        "FROM": sender,
                        "TARGET": target,
                        "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")
                    }, body_text)
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Message delivered."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

            # FILE / IMAGE / VIDEO TRANSFER (TCP, server-forwarded — matches Stage 1 spec)
            # Protocol: POST /file CHAT/1.0
            #   FROM: <sender>  TARGET: <recipient>
            #   CONTENT-TYPE: image/png  FILE-NAME: photo.png
            #   CONTENT-LENGTH: <bytes>
            #   <binary body>
            elif path == "/file":
                content_type = msg["headers"].get("CONTENT-TYPE", "application/octet-stream")
                file_name = msg["headers"].get("FILE-NAME", "file")

                if not target:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "No target specified."})
                    continue

                with state_lock:
                    target_conn = clients.get(target)

                if not target_conn:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})
                    continue

                # Forward the raw binary body to the recipient
                send_message(target_conn, "POST", "/file", {
                    "FROM": sender,
                    "TARGET": target,
                    "CONTENT-TYPE": content_type,
                    "FILE-NAME": file_name,
                }, body)  # body is bytes

                print(f"[FILE] {sender} → {target}: {file_name} ({content_type}, {len(body)} bytes)")
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"File '{file_name}' sent to '{target}'."})

            # GROUP FILE TRANSFER
            elif path == "/group-file":
                content_type = msg["headers"].get("CONTENT-TYPE", "application/octet-stream")
                file_name = msg["headers"].get("FILE-NAME", "file")

                with state_lock:
                    in_group = target in groups and sender in groups[target]
                    members = list(groups.get(target, set()))

                if not target or target not in groups:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"Group '{target}' does not exist."})
                    continue
                if not in_group:
                    send_message(conn, "CHAT/1.0", "403 ERROR", {"ERROR": f"You are not a member of '{target}'."})
                    continue

                with state_lock:
                    member_conns = [(m, clients[m]) for m in members if m != sender and m in clients]

                for member, mconn in member_conns:
                    send_message(mconn, "POST", "/file", {
                        "FROM": sender,
                        "TARGET": target,
                        "CONTENT-TYPE": content_type,
                        "FILE-NAME": file_name,
                    }, body)

                print(f"[GROUP FILE] {sender} → {target}: {file_name} ({len(body)} bytes)")
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"File '{file_name}' sent to group '{target}'."})

            # JOIN GROUP
            elif path == "/join":
                if not target:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "No group specified."})
                    continue
                with state_lock:
                    if target not in groups:
                        groups[target] = set()
                    groups[target].add(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You joined group '{target}'."})

            # LEAVE GROUP
            elif path == "/leave":
                with state_lock:
                    in_group = target and target in groups and sender in groups[target]
                if not in_group:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "You are not in that group."})
                    continue
                with state_lock:
                    groups[target].remove(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You left group '{target}'."})

            # GROUP MESSAGE
            elif path == "/group-message":
                with state_lock:
                    in_group = target in groups and sender in groups[target]
                    members = list(groups.get(target, set()))

                if not target or target not in groups:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"Group '{target}' does not exist."})
                    continue
                if not in_group:
                    send_message(conn, "CHAT/1.0", "403 ERROR", {"ERROR": f"You are not a member of '{target}'."})
                    continue

                with state_lock:
                    member_conns = [(m, clients[m]) for m in members if m != sender and m in clients]

                for member, mconn in member_conns:
                    send_message(mconn, "POST", "/message", {
                        "FROM": sender,
                        "TARGET": target,
                        "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")
                    }, body_text)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Message sent to group '{target}'."})

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        if name:
            with state_lock:
                if name in clients:
                    del clients[name]
            print(f"[-] {name} disconnected")
        conn.close()


def start():
    server.listen()
    print(f"[LISTENING] SERVER IS LISTENING ON {SERVER}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()
        print(f"[ACTIVE CONNECTIONS] {threading.activeCount() - 1}")


print("[STARTING] server is starting .....")
start()