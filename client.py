
import socket
import threading

HEADER = 64
PORT = 5050
DISCONNECT_MESSAGE = "!DISCONNECTED"
SERVER = "196.42.119.202"
FORMAT = 'utf-8'
ADDR = (SERVER, PORT)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

name = input("Enter your name")
client.send(name.encode(FORMAT))

def receive():
    while True:
        try:
            msg = client.recv(1024).decode(FORMAT)
            print(msg)
        except:
            break

threading.Thread(target=receive, daemon=True).start()

print("To message someone type:  Name: your message")
while True:
    msg = input()
    client.send(msg.encode(FORMAT))
    if msg == DISCONNECT_MESSAGE:
        break


