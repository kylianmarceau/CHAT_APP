# CLIENT
# TCP for all messaging, file transfer, and call signalling (via server)
# UDP P2P for real-time audio during calls

import socket
import threading
import os
import json

from protocol import (
    send_message, recv_message,
    build_audio_packet, parse_audio_packet
)

# ── Config ────────────────────────────────────────────────────────────────────
PORT               = 5050
SERVER             = "127.0.0.1"   # AWS server IP
FORMAT             = 'utf-8'
ADDR               = (SERVER, PORT)
DISCONNECT_MESSAGE = "!DISCONNECT"

# Audio settings (requires pyaudio — install with: pip install pyaudio)
CHUNK       = 1024   # audio frames per UDP packet
RATE        = 44100  # sample rate Hz
CHANNELS    = 1      # mono
AUDIO_FMT   = None   # set after pyaudio import

try:
    import pyaudio
    AUDIO_FMT = pyaudio.paInt16
    audio = pyaudio.PyAudio()
    AUDIO_AVAILABLE = True
except ImportError:
    print("[WARN] pyaudio not installed — audio calls unavailable. Run: pip install pyaudio")
    AUDIO_AVAILABLE = False

# ── UDP socket (for audio P2P) ────────────────────────────────────────────────
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.bind(('', 0))
UDP_PORT = udp_sock.getsockname()[1]

# ── TCP socket ────────────────────────────────────────────────────────────────
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

# ── Login / Register ──────────────────────────────────────────────────────────

# get local IP by connecting a dummy UDP socket
_tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_tmp.connect(("8.8.8.8", 80))
LOCAL_IP = _tmp.getsockname()[0]
_tmp.close()

print("Welcome to ChatApp!")
print("  1. Login")
print("  2. Register")
choice = input("Choose (1 or 2): ").strip()

name     = input("Enter your username: ").lower().strip()
password = input("Enter your password: ").strip()

if choice == "2":
    # Send register request, server adds user to DB and closes connection
    send_message(client, "POST", "/register",
                 {"ACTION": "register", "FROM": name, "PASSWORD": password})
    response = recv_message(client)
    status = response["path"]
    info   = response["headers"].get("ERROR") or response["headers"].get("MESSAGE", "")
    print(f"[Server]: {info}")
    if "ERROR" in status:
        client.close()
        exit()
    # Reconnect for actual login
    client.close()
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(ADDR)
    print("Registered! Logging you in...")

# Login (runs for both new registered users and existing users)
send_message(client, "POST", "/login",
             {"ACTION": "login", "FROM": name, "PASSWORD": password,
              "UDP-PORT": UDP_PORT, "LOCAL-IP": LOCAL_IP})

response = recv_message(client)
status   = response["path"]
info     = response["headers"].get("ERROR") or response["headers"].get("MESSAGE", "")
print(f"[Server]: {info}")

if "ERROR" in status:
    client.close()
    exit()

joined_groups = set()

# Call state
in_call        = False
call_peer_addr = None   # (ip, udp_port) of the other side
call_stop      = threading.Event()
pending_call   = None   # (caller, caller_ip, caller_udp) of an incoming call
pending_history = None


# ── FILE TRANSFER (TCP via server) ────────────────────────────────────────────

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


# ── AUDIO CALL (UDP P2P) ──────────────────────────────────────────────────────

def audio_send_loop(peer_ip, peer_udp):
    """Capture mic and stream audio chunks via UDP directly to peer."""
    stream = audio.open(format=AUDIO_FMT, channels=CHANNELS,
                        rate=RATE, input=True, frames_per_buffer=CHUNK)
    seq = 0
    print("[CALL] Streaming audio...")
    while not call_stop.is_set():
        try:
            chunk = stream.read(CHUNK, exception_on_overflow=False)
            packet = build_audio_packet(name, seq, chunk)
            udp_sock.sendto(packet, (peer_ip, peer_udp))
            seq += 1
        except Exception:
            break
    stream.stop_stream()
    stream.close()


def audio_recv_loop():
    """Receive UDP audio chunks from peer and play them."""
    stream = audio.open(format=AUDIO_FMT, channels=CHANNELS,
                        rate=RATE, output=True, frames_per_buffer=CHUNK)
    udp_sock.settimeout(1.0)
    print("[CALL] Receiving audio...")
    while not call_stop.is_set():
        try:
            data, _ = udp_sock.recvfrom(65535)
            packet = parse_audio_packet(data)
            if packet:
                stream.write(packet["chunk"])
        except socket.timeout:
            continue
        except Exception:
            break
    udp_sock.settimeout(None)
    stream.stop_stream()
    stream.close()


def start_audio_call(peer_ip, peer_udp):
    """Start send and receive threads for the audio call."""
    global in_call, call_peer_addr
    in_call        = True
    call_peer_addr = (peer_ip, peer_udp)
    call_stop.clear()
    threading.Thread(target=audio_send_loop, args=(peer_ip, peer_udp), daemon=True).start()
    threading.Thread(target=audio_recv_loop, daemon=True).start()


def end_audio_call():
    """Stop audio threads."""
    global in_call, call_peer_addr
    call_stop.set()
    in_call        = False
    call_peer_addr = None
    print("[CALL] Call ended.")

# ── ADDITION: History helpers (called by UI when contact is clicked) ──────────
 
def load_conversation(target):
    global pending_history
    pending_history = f"dm:{target}"
    send_message(client, "POST", "/history", {"FROM": name, "TARGET": target})
 
 
def load_group_conversation(group_name):
    global pending_history
    pending_history = f"group:{group_name}"
    send_message(client, "POST", "/group-history", {"FROM": name, "TARGET": group_name})
 
 
def load_recent_contacts():
    global pending_history
    pending_history = "contacts"
    send_message(client, "POST", "/contacts", {"FROM": name})

# ── TCP RECEIVE LOOP ──────────────────────────────────────────────────────────

def receive():
    global pending_history, pending_call

    while True:
        try:
            msg = recv_message(client)
            if not msg:
                break

            method  = msg["method"]
            path    = msg["path"]
            headers = msg["headers"]
            body    = msg["body"]

            if method == "CHAT/1.0":

                # History / contacts response
                if pending_history and "200" in path:
                    raw = body.decode(FORMAT) if isinstance(body, bytes) else body

                    if pending_history.startswith("dm:"):
                        target = pending_history[3:]
                        history = json.loads(raw) if raw else []
                        if not history:
                            print(f"[HISTORY] No messages with {target}.")
                        else:
                            print(f"[HISTORY] Conversation with {target}:")
                            for m in history:
                                print(f"  [{m['sent_at']}] {m['sender']}: {m['content']}")

                    elif pending_history.startswith("group:"):
                        group_name = pending_history[6:]
                        history = json.loads(raw) if raw else []
                        if not history:
                            print(f"[HISTORY] No messages in group '{group_name}'.")
                        else:
                            print(f"[HISTORY] Group '{group_name}':")
                            for m in history:
                                print(f"  [{m['sent_at']}] {m['sender']}: {m['content']}")

                    elif pending_history == "contacts":
                        contacts = json.loads(raw) if raw else []
                        if not contacts:
                            print("[CONTACTS] No recent contacts.")
                        else:
                            print("[CONTACTS] Recent contacts:", ", ".join(contacts))

                    pending_history = None

                # Call connected
                elif "PEER-IP" in headers and "PEER-UDP" in headers and not in_call:
                    peer_ip  = headers["PEER-IP"]
                    peer_udp = int(headers["PEER-UDP"])
                    print("[CALL] Call connected. Starting audio...")
                    if AUDIO_AVAILABLE:
                        start_audio_call(peer_ip, peer_udp)

                # Only print errors, suppress delivery confirmations
                else:
                    info = headers.get("ERROR", "")
                    if info:
                        print(f"[Server {path}]: {info}")

            elif method == "POST" and path == "/message":
                sender = headers.get("FROM", "?")
                target = headers.get("TARGET", "")
                text   = body.decode(FORMAT) if isinstance(body, bytes) else body
                tag    = f"group:{target}" if target in joined_groups else sender
                print(f"[{tag}] {sender}: {text}")

            elif method == "POST" and path == "/file":
                threading.Thread(target=handle_incoming_file, args=(msg,), daemon=True).start()

            elif method == "POST" and path == "/call":
                caller     = headers.get("FROM", "?")
                caller_ip  = headers.get("CALLER-IP")
                caller_udp = int(headers.get("CALLER-UDP", 0))
                print(f"\n[CALL] Incoming call from {caller}. Type '/accept {caller}' or '/reject {caller}'.")
                pending_call = (caller, caller_ip, caller_udp)

            elif method == "POST" and path == "/call-accept":
                peer_ip  = headers.get("PEER-IP")
                peer_udp = int(headers.get("PEER-UDP", 0))
                print("[CALL] Call accepted. Starting audio...")
                if AUDIO_AVAILABLE:
                    start_audio_call(peer_ip, peer_udp)

            elif method == "POST" and path == "/endcall":
                caller = headers.get("FROM", "?")
                print(f"[CALL] {caller} ended the call.")
                end_audio_call()

        except Exception:
            break


threading.Thread(target=receive, daemon=True).start()

# ── COMMAND INTERFACE ─────────────────────────────────────────────────────────

print("\nCommands:")
print("  /join groupname           --- join or create a group")
print("  /leave groupname          --- leave a group")
print("  /history username         --- load chat history with a user")
print("  /ghistory groupname       --- load chat history for a group")
print("  /contacts                 --- show your recent contacts")
print("  groupname: message        --- send to a group you've joined")
print("  username: message         --- send to a user")
print("  /file username filepath   --- send a file via TCP")
print("  /call username            --- start an audio call (UDP P2P)")
print("  /accept username          --- accept an incoming call")
print("  /reject username          --- reject an incoming call")
print("  /endcall username         --- end an ongoing call")
print("  !DISCONNECT               --- logout and exit\n")

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

    elif msg.startswith("/history "):
        target = msg[9:].strip().lower()
        load_conversation(target)
 
    elif msg.startswith("/ghistory "):
        group_name = msg[10:].strip().lower()
        load_group_conversation(group_name)
 
    elif msg.strip() == "/contacts":
        load_recent_contacts()
 

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
        if not AUDIO_AVAILABLE:
            print("[CALL] pyaudio not installed — cannot make calls.")
        elif in_call:
            print("[CALL] Already in a call.")
        else:
            send_message(client, "POST", "/call", {"FROM": name, "TARGET": target})
            print(f"[CALL] Calling {target}... waiting for them to accept.")

    elif msg.startswith("/accept "):
        caller = msg[8:].strip().lower()
        if pending_call and pending_call[0] == caller:
            _, caller_ip, caller_udp = pending_call
            send_message(client, "POST", "/call-accept", {"FROM": name, "TARGET": caller})
            print(f"[CALL] Accepted call from {caller}. Starting audio...")
            if AUDIO_AVAILABLE:
                start_audio_call(caller_ip, caller_udp)
            pending_call = None
        else:
            print(f"[CALL] No incoming call from {caller}.")

    elif msg.startswith("/reject "):
        caller = msg[8:].strip().lower()
        send_message(client, "POST", "/endcall", {"FROM": name, "TARGET": caller})
        pending_call = None
        print(f"[CALL] Rejected call from {caller}.")

    elif msg.startswith("/endcall "):
        target = msg[9:].strip().lower()
        send_message(client, "POST", "/endcall", {"FROM": name, "TARGET": target})
        end_audio_call()

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