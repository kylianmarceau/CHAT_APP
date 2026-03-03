
#MAIN TCP SERVER

import socket
import threading

HEADER = 64
PORT = 5050
SERVER = "196.42.116.252"
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECTED"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

clients = {}

def recv_msg(conn):
    msg_length = conn.recv(HEADER).decode(FORMAT)
    if msg_length:
        msg_length = int(msg_length.strip())
        return conn.recv(msg_length).decode(FORMAT)
    return None

def handle_client(conn, addr):
    name = conn.recv(1024).decode(FORMAT)
    clients[name] = conn
    print(f"[+] {name} connected")

    while True:
        try:
            msg = conn.recv(1024).decode(FORMAT)
            if not msg or msg == DISCONNECT_MESSAGE:
                break

            # Format: "Recipient: message"
            recipient, content = msg.split(": ", 1)
            if recipient in clients:
                clients[recipient].send(f"[{name}]: {content}".encode(FORMAT))
            else:
                conn.send(f"[Server]: {recipient} is not online.".encode(FORMAT))
        except:
            break

    del clients[name]
    conn.close()
    print(f"[-] {name} disconnected")


def start():
    server.listen()
    print(f"[LISTENING] SERVER IS LISTENING ON {SERVER}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target = handle_client, args=(conn, addr))
        thread.start()
        print(f"[ACTIVE CONNECTIONS] {threading.activeCount() - 1 }")


print("[STARTING] server is starting .....")
start()
