import socket
import threading
from protocol import send_message, recv_message, build_udp_packet, parse_udp_packet

PORT = 5050
SERVER = "localhost"
FORMAT = 'utf-8'
ADDR = (SERVER, PORT)
DISCONNECT_MESSAGE = "!DISCONNECTED"
CHUNK_SIZE = 1024  # bytes per UDP packet

# ── UDP socket for file transfer ──────────────────────────────────────────────
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.bind(('', 0))
UDP_PORT = udp_sock.getsockname()[1]

# ── Event so receive() can hand /get-peer-udp responses to udp_send_file() ───
peer_udp_response = None
peer_udp_event    = threading.Event()

# ── Main TCP connection to server ─────────────────────────────────────────────
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

# ── LOGIN ─────────────────────────────────────────────────────────────────────
name     = input("Enter your username: ").lower()
password = input("Enter your password: ")

send_message(client, "POST", "/login", {
    "FROM":     name,
    "PASSWORD": password,
    "UDP-PORT": UDP_PORT
})

response = recv_message(client)
status   = response["path"]
info     = response["headers"].get("ERROR") or response["headers"].get("MESSAGE", "")
print(f"[Server]: {info}")

if "ERROR" in status:
    client.close()
    exit()

joined_groups = set()  # track groups this client has joined


# ── UDP FILE SEND ─────────────────────────────────────────────────────────────
def udp_send_file(target, filepath):
    """
    1. Ask server for target's UDP address via TCP
    2. Notify target via TCP that a file is coming
    3. Wait for target to send back a UDP READY signal
    4. Send file chunks directly to target via UDP
    """
    import os, time

    global peer_udp_response
    peer_udp_event.clear()

    # Step 1: get peer's UDP address from server
    send_message(client, "POST", "/get-peer-udp", {"FROM": name, "TARGET": target})
    peer_udp_event.wait(timeout=5)

    response = peer_udp_response
    if not response or "ERROR" in response["path"]:
        print(f"[Server]: {response['headers'].get('ERROR') if response else 'No response'}")
        return

    peer_ip   = response["headers"].get("PEER-IP")
    peer_port = int(response["headers"].get("PEER-PORT"))

    # Step 2: read and chunk the file
    with open(filepath, "rb") as f:
        data = f.read()

    filename = os.path.basename(filepath)
    chunks   = [data[i:i + CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]
    total    = len(chunks)

    # Step 3: notify recipient via TCP (server relays this)
    send_message(client, "POST", "/message", {
        "FROM":         name,
        "TARGET":       target,
        "CONTENT-TYPE": "file-incoming"
    }, f"FILE:{filename}:{total}")

    # Step 4: wait for recipient's UDP READY signal before sending
    print(f"[FILE] Waiting for {target} to be ready...")
    udp_sock.settimeout(10.0)
    try:
        while True:
            data_in, _ = udp_sock.recvfrom(64)
            if data_in == b"READY":
                break
    except socket.timeout:
        print(f"[FILE] {target} did not respond in time. Aborting.")
        udp_sock.settimeout(None)
        return
    udp_sock.settimeout(None)

    # Step 5: send all chunks directly via UDP
    print(f"[FILE] Sending '{filename}' ({total} chunks)...")
    for seq, chunk in enumerate(chunks):
        packet = build_udp_packet(name, seq, total, chunk)
        udp_sock.sendto(packet, (peer_ip, peer_port))
        time.sleep(0.001)  # small delay to avoid packet flood

    print(f"[FILE] Sent '{filename}' to {target} ({total} chunks).")


# ── UDP FILE RECEIVE ──────────────────────────────────────────────────────────
def udp_receive_file(sender, filename, total_chunks, sender_ip, sender_udp_port):
    """
    1. Send READY signal directly to sender via UDP
    2. Receive all chunks
    3. Reassemble and save
    """
    print(f"[FILE] Receiving '{filename}' from {sender} ({total_chunks} chunks)...")

    # Step 1: tell sender we're ready via UDP
    udp_sock.sendto(b"READY", (sender_ip, sender_udp_port))

    # Step 2: collect chunks
    received = {}
    udp_sock.settimeout(5.0)

    while len(received) < total_chunks:
        try:
            data, _ = udp_sock.recvfrom(65535)
            if data == b"READY":
                continue  # ignore stray READY signals
            packet = parse_udp_packet(data)
            if packet and packet["sender"] == sender:
                received[packet["seq"]] = packet["chunk"]
                if len(received) % 20 == 0:
                    print(f"[FILE] Progress: {len(received)}/{total_chunks}")
        except socket.timeout:
            print(f"[FILE] Timed out — received {len(received)}/{total_chunks} chunks.")
            break

    udp_sock.settimeout(None)

    # Step 3: reassemble and save
    if len(received) == total_chunks:
        file_data = b"".join(received[i] for i in sorted(received))
        with open(f"received_{filename}", "wb") as f:
            f.write(file_data)
        print(f"[FILE] Saved as 'received_{filename}'.")
    else:
        print(f"[FILE] Incomplete transfer — file not saved.")


# ── SERVER TCP RECEIVE LOOP ───────────────────────────────────────────────────
def receive():
    while True:
        try:
            msg = recv_message(client)
            if not msg:
                break

            method = msg["method"]
            path   = msg["path"]

            # Server status responses
            if method == "CHAT/1.0":
                # Hand /get-peer-udp responses to udp_send_file()
                if "PEER-IP" in msg["headers"]:
                    global peer_udp_response
                    peer_udp_response = msg
                    peer_udp_event.set()
                else:
                    info = msg["headers"].get("ERROR") or msg["headers"].get("MESSAGE", "")
                    if info:
                        print(f"[Server {path}]: {info}")

            # Incoming message from another user
            elif method == "POST" and path == "/message":
                sender       = msg["headers"].get("FROM", "?")
                target       = msg["headers"].get("TARGET", "")
                content_type = msg["headers"].get("CONTENT-TYPE", "text")
                body         = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]

                if content_type == "file-incoming":
                    # Server included sender's IP and UDP port in the forwarded message
                    sender_ip  = msg["headers"].get("SENDER-IP", "")
                    sender_udp = int(msg["headers"].get("SENDER-UDP", 0))
                    _, filename, total = body.split(":")
                    threading.Thread(
                        target=udp_receive_file,
                        args=(sender, filename, int(total), sender_ip, sender_udp),
                        daemon=True
                    ).start()
                else:
                    tag = f"group:{target}" if target in joined_groups else sender
                    print(f"[{tag}] {sender}: {body}")

        except Exception:
            break


threading.Thread(target=receive, daemon=True).start()

# ── MAIN INPUT LOOP ───────────────────────────────────────────────────────────
print("\nCommands:")
print("  /join groupname          → join or create a group")
print("  /leave groupname         → leave a group")
print("  groupname: message       → send to a group you've joined")
print("  username: message        → send to a user")
print("  /file username filepath  → send a file directly via UDP")
print("  !DISCONNECTED            → logout and exit\n")

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
                target=udp_send_file,
                args=(target.lower(), filepath.strip()),
                daemon=True
            ).start()

    elif ": " in msg:
        target, content = msg.split(": ", 1)
        target = target.strip().lower()

        if target in joined_groups:
            send_message(client, "POST", "/group-message", {
                "FROM":         name,
                "TARGET":       target,
                "CONTENT-TYPE": "text"
            }, content)
        else:
            send_message(client, "POST", "/message", {
                "FROM":         name,
                "TARGET":       target,
                "CONTENT-TYPE": "text"
            }, content)
    else:
        print("Format:  username: message   or   groupname: message")