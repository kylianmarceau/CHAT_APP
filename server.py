import socket
import threading
from protocol import send_message, recv_message

HEADER = 64
PORT = 5050
SERVER = "192.168.101.136"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECTED"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

clients = {}

def handle_client(conn, addr):
    # --- LOGIN ---
    msg = recv_message(conn)
    name = msg["headers"].get("FROM", "")
    clients[name] = conn
    print(f"[+] {name} connected")

    # Send success response
    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Login successful"})

    while True:
        try:
            msg = recv_message(conn)
            if not msg:
                break

            path = msg["path"]
            sender = msg["headers"].get("FROM", "")
            target = msg["headers"].get("TARGET", "")
            body = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]

            # --- LOGOUT ---
            if path == "/logout":
                break

            # --- ONE-TO-ONE MESSAGE ---
            elif path == "/message":
                if target in clients:
                    send_message(clients[target], "POST", "/message", {
                        "FROM": sender,
                        "TARGET": target,
                        "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")
                    }, body)
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE-ID": "OK"})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"{target} is not online."})

            # --- GROUP MESSAGE ---
            elif path == "/group-message":
                for member_name, member_conn in clients.items():
                    if member_name != sender:
                        send_message(member_conn, "POST", "/message", {
                            "FROM": sender,
                            "TARGET": "group",
                            "CONTENT-TYPE": "text"
                        }, body)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE-ID": "OK"})

        except Exception as e:
            print(f"[ERROR] {e}")
            break

    del clients[name]
    conn.close()
    print(f"[-] {name} disconnected")


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