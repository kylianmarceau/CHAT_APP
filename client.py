import socket
import threading
from protocol import send_message, recv_message

HEADER = 64
PORT = 5050
DISCONNECT_MESSAGE = "!DISCONNECTED"
SERVER = "192.168.101.136"
FORMAT = 'utf-8'
ADDR = (SERVER, PORT)

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

name = input("Enter your name: ")

# --- LOGIN ---
send_message(client, "POST", "/login", {"FROM": name})
response = recv_message(client)
print(f"[Server]: {response['headers'].get('MESSAGE', '')}")

def receive():
    while True:
        try:
            msg = recv_message(client)
            if not msg:
                break
            sender = msg["headers"].get("FROM", "Server")
            body = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]
            # Show server status messages
            if msg["method"] == "CHAT/1.0":
                status = msg["path"]
                info = msg["headers"].get("ERROR") or msg["headers"].get("MESSAGE", "")
                if info:
                    print(f"[Server {status}]: {info}")
            else:
                print(f"[{sender}]: {body}")
        except:
            break

threading.Thread(target=receive, daemon=True).start()

print("To message someone:   Name: your message")
print("To message the group: group: your message")
print("To disconnect:        !DISCONNECTED")

while True:
    msg = input()

    if msg == DISCONNECT_MESSAGE:
        send_message(client, "POST", "/logout", {"FROM": name})
        break

    elif ": " in msg:
        target, content = msg.split(": ", 1)
        if target.lower() == "group":
            send_message(client, "POST", "/group-message", {
                "FROM": name,
                "CONTENT-TYPE": "text"
            }, content)
        else:
            send_message(client, "POST", "/message", {
                "FROM": name,
                "TARGET": target,
                "CONTENT-TYPE": "text"
            }, content)
    else:
        print("[hint] Format: Name: your message  or  group: your message")