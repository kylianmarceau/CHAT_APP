# MAIN TCP SERVER
# hosting server on aws

import socket
import threading
from protocol import send_message, recv_message

PORT     = 5050
UDP_PORT = 5051
SERVER   = "0.0.0.0"
ADDR     = (SERVER, PORT)
FORMAT   = 'utf-8'

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

# UDP relay socket
udp_server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_server.bind(("0.0.0.0", UDP_PORT))

clients      = {}   # name -> TCP conn
groups       = {}   # group_name -> set of member names
udp_peers    = {}   # (ip, port) -> (ip, port)  — bidirectional relay map
pending_udp  = {}   # caller_name -> (caller_ip, caller_udp_port)
udp_registry = {}   # name -> (ip, port) — real public UDP address learned from first packet

users = {"tim": "1234", "kylian": "4567", "kp": "999"}  # hardcoded for now


# ─── UDP RELAY THREAD ────────────────────────────────────────────────────────
def udp_relay():
    """Forward every UDP packet to the registered peer."""
    print(f"[UDP] Relay listening on port {UDP_PORT}")
    while True:
        try:
            data, addr = udp_server.recvfrom(4096)

            # Registration packet — client sends their username as bytes right after login
            try:
                possible_name = data.decode(FORMAT).strip()
                if possible_name in users:
                    udp_registry[possible_name] = addr
                    print(f"[UDP] Registered {possible_name} -> {addr}")
                    continue
            except Exception:
                pass

            # Normal audio relay
            peer = udp_peers.get(addr)
            if peer:
                udp_server.sendto(data, peer)

        except Exception as e:
            print(f"[UDP ERROR] {e}")

threading.Thread(target=udp_relay, daemon=True).start()
# ─────────────────────────────────────────────────────────────────────────────


def handle_client(conn, addr):
    name = None
    try:
        # ── login ──────────────────────────────────────────────────────────
        msg      = recv_message(conn)
        name     = msg["headers"].get("FROM", "").lower()
        password = msg["headers"].get("PASSWORD", "")

        if name not in users:
            send_message(conn, "CHAT/1.0", "401 ERROR", {"ERROR": "Username incorrect."})
            conn.close()
            return
        if users[name] != password:
            send_message(conn, "CHAT/1.0", "401 ERROR", {"ERROR": "Password incorrect."})
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

            path   = msg["path"]
            sender = msg["headers"].get("FROM", "").lower()
            target = msg["headers"].get("TARGET", "").lower()
            body   = msg["body"]

            # ── logout ─────────────────────────────────────────────────────
            if path == "/logout":
                break

            # ── 1-to-1 message ─────────────────────────────────────────────
            elif path == "/message":
                if target in clients:
                    send_message(
                        clients[target], "POST", "/message",
                        {
                            "FROM":         sender,
                            "TARGET":       target,
                            "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text"),
                        },
                        body
                    )
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Message delivered."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

            # ── file transfer ───────────────────────────────────────────────
            elif path == "/file":
                if target in clients:
                    send_message(
                        clients[target], "POST", "/file",
                        {
                            "FROM":      sender,
                            "TARGET":    target,
                            "FILE-NAME": msg["headers"].get("FILE-NAME", "file"),
                        },
                        body
                    )
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"File sent to '{target}'."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

            # ── join group ─────────────────────────────────────────────────
            elif path == "/join":
                if not target:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "No group specified."})
                    continue
                if target not in groups:
                    groups[target] = set()
                groups[target].add(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You joined group '{target}'."})

            # ── leave group ────────────────────────────────────────────────
            elif path == "/leave":
                if not target or target not in groups or sender not in groups[target]:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "You are not in that group."})
                    continue
                groups[target].remove(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You left group '{target}'."})

            # ── group message ───────────────────────────────────────────────
            elif path == "/group-message":
                if not target or target not in groups:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"Group '{target}' does not exist."})
                    continue
                if sender not in groups[target]:
                    send_message(conn, "CHAT/1.0", "403 ERROR", {"ERROR": f"You are not a member of '{target}'."})
                    continue
                for member in groups[target]:
                    if member != sender and member in clients:
                        send_message(
                            clients[member], "POST", "/message",
                            {
                                "FROM":         sender,
                                "TARGET":       target,
                                "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text"),
                            },
                            body
                        )
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Message sent to group '{target}'."})

            # ── /call — look up caller's registered UDP addr, forward to target ──
            elif path == "/call":
                if target in clients:
                    caller_addr = udp_registry.get(sender)
                    if not caller_addr:
                        send_message(conn, "CHAT/1.0", "400 ERROR",
                                     {"ERROR": "UDP not registered yet. Try again in a moment."})
                        continue
                    pending_udp[sender] = caller_addr
                    send_message(clients[target], "POST", "/call", {"FROM": sender})
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Calling {target}..."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"{target} is not online."})

            # ── /accept-call — wire up UDP relay, notify caller ────────────
            elif path == "/accept-call":
                if target in clients:
                    callee_addr = udp_registry.get(sender)
                    caller_addr = pending_udp.pop(target, None)

                    if caller_addr and callee_addr:
                        udp_peers[caller_addr] = callee_addr
                        udp_peers[callee_addr] = caller_addr
                        print(f"[UDP] Relay: {caller_addr} <-> {callee_addr}")
                    else:
                        print(f"[WARN] Could not set up relay: caller_addr={caller_addr}, callee_addr={callee_addr}")

                    send_message(clients[target], "POST", "/accept-call", {"FROM": sender})
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Call accepted."})

            # ── /endcall — clean up relay + notify peer ────────────────────
            elif path == "/endcall":
                # Remove UDP relay entries for this caller
                caller_addr = udp_registry.get(sender)
                if caller_addr and caller_addr in udp_peers:
                    peer_addr = udp_peers.pop(caller_addr, None)
                    if peer_addr:
                        udp_peers.pop(peer_addr, None)

                if target and target in clients:
                    send_message(clients[target], "POST", "/endcall", {"FROM": sender})

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        if name:
            clients.pop(name, None)
            udp_registry.pop(name, None)
            print(f"[-] {name} disconnected")
        conn.close()


def start():
    server.listen()
    print(f"[LISTENING] TCP server listening on port {PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")


print("[STARTING] Server is starting...")
start()