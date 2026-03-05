import socket
import threading
from protocol import send_message, recv_message

PORT = 5050
SERVER = "192.168.120.160"
FORMAT = 'utf-8'
ADDR = (SERVER, PORT)
DISCONNECT_MESSAGE = "!DISCONNECTED"

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect(ADDR)

#  LOGIN 
name = input("Enter your username: ").lower()
password = input("Enter your password: ")

send_message(client, "POST", "/login", {"FROM": name, "PASSWORD": password})
response = recv_message(client)

status = response["path"]         # eorrr 200=ok 401 not okau
info = response["headers"].get("ERROR") or response["headers"].get("MESSAGE", "")
print(f"[Server]: {info}")

if "ERROR" in status:
    client.close()
    exit()


def receive():
    while True:
        try:
            msg = recv_message(client)
            if not msg:
                break

            method = msg["method"]
            path = msg["path"]

            # server status response error or not
            if method == "CHAT/1.0":
                info = msg["headers"].get("ERROR") or msg["headers"].get("MESSAGE", "")
                if info:
                    print(f"[Server {path}]: {info}")

            # sncoming message from another user
            elif method == "POST" and path == "/message":
                sender = msg["headers"].get("FROM", "?")
                target = msg["headers"].get("TARGET", "")
                body = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]
                tag = "group" if target == "group" else sender
                print(f"[{tag}] {sender}: {body}")

        except Exception as e:
            break


threading.Thread(target=receive, daemon=True).start()

print("\nCommands:")
print("  Name: your message    → send to a user")
print("  !DISCONNECTED         → logout and exit\n")

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

    elif msg.startswith("/leave "):
        group_name = msg[7:].strip().lower()
        send_message(client, "POST", "/leave", {"FROM": name, "TARGET": group_name})


    elif ": " in msg:
        target, content = msg.split(": ", 1)
        target = target.strip().lower()

        if target.startswith("group"):
            send_message(client, "POST", "/group-message", {
                "FROM": name,
                "TARGET": target,
                "CONTENT-TYPE": "text"
            }, content)
        else:
            send_message(client, "POST", "/message", {
                "FROM": name,
                "TARGET": target,
                "CONTENT-TYPE": "text"
            }, content)
    else:
        print("Format:  Name: your message   or   group: your message")