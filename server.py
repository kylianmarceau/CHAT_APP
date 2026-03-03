
#MAIN TCP SERVER

import socket
import threading

PORT = 6767
SERVER = "196.42.116.252"
ADDR = (SERVER, PORT)


server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)

def handle_client(conn, addr):
    pass

def start():
    server.listen()
    while True:
        conn, addr = server.accept
        thread = threading.Thread(target = handle_client, args=(conn, addr))
        thread.start()
        print(f"[ACTIVE CONNECTIONS] {threading.activeCount() - 1 }")


print("[STARTING] server is starting .....")
start()
