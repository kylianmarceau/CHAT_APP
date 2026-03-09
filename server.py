
# MAIN TCP SERVER 

import socket
import threading
from protocol import send_message, recv_message

PORT = 5050
SERVER = "localhost"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

clients = {}          
client_udp_ports = {} 
groups = {}           

users = {"tim": "1234", "kylian": "4567", "kp": "999"}  # hardcoded for now can use databse later on


def handle_client(conn, addr):
    name = None
    try:
        # log in w/ protocol
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

        clients[name]          = conn
        client_udp_ports[name] = msg["headers"].get("UDP-PORT", "")
        print(f"[+] {name} connected from {addr}")
        send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Welcome {name}! Login successful."})

        while True:
            msg = recv_message(conn)
            if not msg:
                break

            path   = msg["path"]
            sender = msg["headers"].get("FROM", "").lower()
            target = msg["headers"].get("TARGET", "").lower()
            body   = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]

            # log out 
            if path == "/logout":
                break

            # 1 to 1 message -- through server
            elif path == "/message":
                if target in clients:
                    send_message(clients[target], "POST", "/message", {"FROM":         sender,"TARGET":       target,"CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text"),"SENDER-IP":    conn.getpeername()[0],"SENDER-UDP":   client_udp_ports.get(sender, "")}, body)
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Message delivered."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

            # to join group
            elif path == "/join":
                if not target:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "No group specified."})
                    continue
                if target not in groups:
                    groups[target] = set()
                groups[target].add(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You joined group '{target}'."})

            # to leave group
            elif path == "/leave":
                if not target or target not in groups or sender not in groups[target]:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "You are not in that group."})
                    continue
                groups[target].remove(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You left group '{target}'."})

            # send message on group
            elif path == "/group-message":
                if not target or target not in groups:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"Group '{target}' does not exist."})
                    continue
                if sender not in groups[target]:
                    send_message(conn, "CHAT/1.0", "403 ERROR", {"ERROR": f"You are not a member of '{target}'."})
                    continue
                for member in groups[target]:
                    if member != sender and member in clients:
                        send_message(clients[member], "POST", "/message", {"FROM":         sender,"TARGET":       target,"CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")}, body)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Message sent to group '{target}'."})


            # UDP media trasnfer. need to signal to server and get IP (SIGNALIGN)            
            elif path == "/get-peer-udp":
                if target in clients:
                    peer_ip   = clients[target].getpeername()[0]
                    peer_port = client_udp_ports.get(target, "")
                    if peer_port:
                        send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE":   "Peer found.","PEER-IP":   peer_ip,"PEER-PORT": peer_port})

                    else:
                        send_message(conn, "CHAT/1.0", "404 ERROR", {
                            "ERROR": f"'{target}' UDP port unknown."
                        })
                        
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        if name and name in clients:
            del clients[name]
            del client_udp_ports[name]
            print(f"[-] {name} disconnected")
        conn.close()


def start():
    server.listen()
    print(f"[LISTENING] Server is listening on {SERVER}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")


print("[STARTING] Server is starting...")
start()