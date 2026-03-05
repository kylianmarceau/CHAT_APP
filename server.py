import socket
import threading
from protocol import send_message, recv_message

HEADER = 64
PORT = 5050
SERVER = "196.42.116.80"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECTED"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

clients = {}

users = {"tim": "1234", "kylian": "4567", "kp": "999"} #HARD CODE FOR NOW< DATABASE LATER ON
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
            body = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]

            # LOGOUT
            if path == "/logout":
                break

            # ONE-TO-ONE MESSAGE 
            elif path == "/message":
                if target in clients:
                    send_message(clients[target], "POST", "/message", {
                        "FROM": sender,
                        "TARGET": target,
                        "CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")
                    }, body)
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Message delivered."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})

            

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        if name and name in clients:
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