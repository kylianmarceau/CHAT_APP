# MAIN TCP SERVER
# Hosted on AWS — listens on all interfaces
# Handles: auth, text, group chat, file relay (TCP), and call signalling (UDP P2P)

import socket
import threading
from protocol import send_message, recv_message

PORT   = 5050
SERVER = "0.0.0.0"
ADDR   = (SERVER, PORT)
FORMAT = 'utf-8'

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

clients          = {}   # name -> TCP connection
client_udp_ports = {}   # name -> UDP port for audio calls
client_local_ips = {}   # name -> local IP (for same-network UDP P2P)
groups           = {}   # group name -> set of member names

users = {"tim": "1234", "kylian": "4567", "kp": "999"}  # hardcoded, replace with DB later


def handle_client(conn, addr):
    name = None
    try:
        # ── Authentication ────────────────────────────────────────────────────
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

        clients[name]           = conn
        client_udp_ports[name]  = msg["headers"].get("UDP-PORT", "")
        client_local_ips[name]  = msg["headers"].get("LOCAL-IP", conn.getpeername()[0])
        print(f"[+] {name} connected from {addr}")
        send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Welcome {name}! Login successful."})

        # ── Main message loop ─────────────────────────────────────────────────
        while True:
            msg = recv_message(conn)
            if not msg:
                break

            path   = msg["path"]
            sender = msg["headers"].get("FROM", "").lower()
            target = msg["headers"].get("TARGET", "").lower()
            body   = msg["body"]

            # Logout
            if path == "/logout":
                break

            # 1-to-1 text message — relayed through server via TCP
            elif path == "/message":
                if target in clients:
                    send_message(
                        clients[target], "POST", "/message",
                        {"FROM": sender, "TARGET": target,
                         "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")},
                        body
                    )
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Message delivered."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

            # File transfer — full binary body relayed through server via TCP
            elif path == "/file":
                if target in clients:
                    send_message(
                        clients[target], "POST", "/file",
                        {"FROM": sender, "TARGET": target,
                         "FILE-NAME": msg["headers"].get("FILE-NAME", "file")},
                        body
                    )
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"File sent to '{target}'."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

            # Join group
            elif path == "/join":
                if not target:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "No group specified."})
                    continue
                groups.setdefault(target, set()).add(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You joined group '{target}'."})

            # Leave group
            elif path == "/leave":
                if not target or target not in groups or sender not in groups[target]:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "You are not in that group."})
                    continue
                groups[target].remove(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You left group '{target}'."})

            # Group message
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
                            {"FROM": sender, "TARGET": target,
                             "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")},
                            body
                        )
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Message sent to group '{target}'."})

            # ── Call signalling ───────────────────────────────────────────────
            # Caller sends /call — server forwards the request to the target,
            # then both peers exchange UDP ports directly for audio P2P.

            elif path == "/call":
                if target not in clients:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})
                    continue

                caller_ip   = client_local_ips.get(sender, conn.getpeername()[0])
                caller_udp  = client_udp_ports.get(sender, "")
                target_ip   = client_local_ips.get(target, clients[target].getpeername()[0])
                target_udp  = client_udp_ports.get(target, "")

                if not caller_udp or not target_udp:
                    send_message(conn, "CHAT/1.0", "500 ERROR", {"ERROR": "UDP port unknown for one or both peers."})
                    continue

                # Notify target of incoming call — include caller's UDP details
                send_message(
                    clients[target], "POST", "/call",
                    {"FROM": sender, "CALLER-IP": caller_ip, "CALLER-UDP": caller_udp}
                )

                # Respond to caller with target's UDP details
                send_message(
                    conn, "CHAT/1.0", "200 OK",
                    {"MESSAGE": "Call initiated.", "PEER-IP": target_ip, "PEER-UDP": target_udp}
                )

            # Target accepts — server notifies caller to start streaming
            elif path == "/call-accept":
                if target in clients:
                    accepter_ip  = client_local_ips.get(sender, conn.getpeername()[0])
                    accepter_udp = client_udp_ports.get(sender, "")
                    send_message(
                        clients[target], "POST", "/call-accept",
                        {"FROM": sender, "PEER-IP": accepter_ip, "PEER-UDP": accepter_udp}
                    )
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Acceptance forwarded."})

            # Either peer ends the call — server notifies the other side
            elif path == "/endcall":
                if target in clients:
                    send_message(clients[target], "POST", "/endcall", {"FROM": sender})
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Call ended."})

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        if name and name in clients:
            del clients[name]
            client_udp_ports.pop(name, None)
            client_local_ips.pop(name, None)
            print(f"[-] {name} disconnected")
        conn.close()


def start():
    server.listen()
    print(f"[LISTENING] Server is listening on {SERVER}:{PORT}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")


print("[STARTING] Server is starting...")
start()