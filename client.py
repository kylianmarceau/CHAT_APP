# client file

import socket
import threading
import os
from protocol import send_message, recv_message
import pyaudio


PORT     = 5050
UDP_PORT = 5051          # server's UDP relay port
SERVER   = "13.49.137.214"
FORMAT   = 'utf-8'
ADDR     = (SERVER, PORT)
DISCONNECT_MESSAGE = "!DISCONNECT"

# ─── Audio config ─────────────────────────────────────────────────────────────
CHUNK         = 1024
RATE          = 44100
FORMAT_AUDIO  = pyaudio.paInt16
CHANNELS      = 1

in_call       = False
call_partner  = None
call_peer_udp = None

p = pyaudio.PyAudio()

def send_audio():
    """Capture mic and stream to the server's UDP relay."""
    stream = p.open(format=FORMAT_AUDIO, channels=CHANNELS,
                    rate=RATE, input=True, frames_per_buffer=CHUNK)
    relay = (SERVER, UDP_PORT)
    while in_call:
        data = stream.read(CHUNK, exception_on_overflow=False)
        client_UDP.sendto(data, relay)
    stream.stop_stream()
    stream.close()

def receive_audio():
    """Receive relayed UDP audio and play it."""
    stream = p.open(format=FORMAT_AUDIO, channels=CHANNELS,
                    rate=RATE, output=True, frames_per_buffer=CHUNK)
    client_UDP.settimeout(1.0)
    while in_call:
        try:
            data, _ = client_UDP.recvfrom(CHUNK * 2)
            stream.write(data)
        except socket.timeout:
            continue
    stream.stop_stream()
    stream.close()
# ─────────────────────────────────────────────────────────────────────────────

# TCP socket
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

# UDP socket — bound so the server knows our UDP port
client_UDP = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_UDP.bind(("0.0.0.0", 0))
udp_port = client_UDP.getsockname()[1]

# ── login ─────────────────────────────────────────────────────────────────────
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

# Register our real public UDP address with the server
client_UDP.sendto(name.encode(FORMAT), (SERVER, UDP_PORT))

joined_groups = set()
pending_calls = {}   # caller_name -> their udp port (from /call notification)


# ── File helpers ──────────────────────────────────────────────────────────────
def tcp_send_file(target, filepath):
    if not os.path.exists(filepath):
        print(f"[FILE] File not found: {filepath}")
        return
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        data = f.read()
    print(f"[FILE] Sending '{filename}' to {target} ({len(data)} bytes)...")
    send_message(client, "POST", "/file",
                 {"FROM": name, "TARGET": target, "FILE-NAME": filename}, data)
    print(f"[FILE] Sent '{filename}' to {target}.")

def handle_incoming_file(msg):
    sender   = msg["headers"].get("FROM", "?")
    filename = msg["headers"].get("FILE-NAME", "received_file")
    data     = msg["body"]
    save_path = f"received_{filename}"
    with open(save_path, "wb") as f:
        f.write(data)
    print(f"[FILE] Received '{filename}' from {sender} — saved as '{save_path}'.")


# ── Server receive loop ───────────────────────────────────────────────────────
def receive():
    global in_call, call_partner, call_peer_udp
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
                sender  = msg["headers"].get("FROM", "?")
                target  = msg["headers"].get("TARGET", "")
                body    = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]
                tag     = f"group:{target}" if target in joined_groups else sender
                print(f"[{tag}] {sender}: {body}")

            elif method == "POST" and path == "/file":
                threading.Thread(target=handle_incoming_file, args=(msg,), daemon=True).start()

            elif method == "POST" and path == "/call":
                caller = msg["headers"].get("FROM")
                print(f"\n[CALL] Incoming call from {caller}. Type /accept {caller} or /reject {caller}")
                pending_calls[caller] = True

            elif method == "POST" and path == "/accept-call":
                # Caller receives this — call is live, start audio threads
                peer = msg["headers"].get("FROM")
                in_call = True
                call_partner = peer
                print(f"[CALL] {peer} accepted! Starting call...")
                threading.Thread(target=send_audio,    daemon=True).start()
                threading.Thread(target=receive_audio, daemon=True).start()

            elif method == "POST" and path == "/endcall":
                in_call = False
                call_partner = None
                print(f"\n[CALL] Call ended.")

        except Exception:
            break


threading.Thread(target=receive, daemon=True).start()

# ── Commands ──────────────────────────────────────────────────────────────────
print("\nCommands:")
print("  /join groupname          --- join or create a group")
print("  /leave groupname         --- leave a group")
print("  groupname: message       --- send to a group you've joined")
print("  username: message        --- send to a user")
print("  /file username filepath  --- send a file to a user via TCP")
print("  /call username           --- start a voice call")
print("  /accept username         --- accept an incoming call")
print("  /reject username         --- reject an incoming call")
print("  /endcall                 --- hang up")
print("  !DISCONNECT              --- logout and exit\n")

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
        parts = msg[6:].strip().split(" ", 1)
        if len(parts) != 2:
            print("Usage: /file username filepath")
        else:
            target, filepath = parts
            threading.Thread(target=tcp_send_file,
                             args=(target.lower(), filepath.strip()), daemon=True).start()

    elif msg.startswith("/call "):
        target = msg[6:].strip().lower()
        send_message(client, "POST", "/call",
                     {"FROM": name, "TARGET": target})

    elif msg.startswith("/accept "):
        caller = msg[8:].strip().lower()
        if caller in pending_calls:
            pending_calls.pop(caller)
            in_call = True
            call_partner = caller
            send_message(client, "POST", "/accept-call",
                         {"FROM": name, "TARGET": caller})
            threading.Thread(target=send_audio,    daemon=True).start()
            threading.Thread(target=receive_audio, daemon=True).start()
        else:
            print(f"[CALL] No pending call from {caller}.")

    elif msg.startswith("/reject "):
        caller = msg[8:].strip().lower()
        pending_calls.pop(caller, None)
        print(f"[CALL] Rejected call from {caller}.")

    elif msg == "/endcall":
        in_call = False
        send_message(client, "POST", "/endcall", {"FROM": name, "TARGET": call_partner or ""})
        call_partner = None
        print("[CALL] Call ended.")

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