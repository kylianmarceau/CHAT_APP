
#MAIN TCP SERVER

import socket
import threading
import json
from protocol import send_message, recv_message
from database import init_db, check_user, save_message, get_conversation, get_recent_contacts, get_group_conversation, add_user


HEADER = 64
PORT = 5050
SERVER = "13.49.137.214" # AWS ipv4 adress to connect roemotely
ADDR = (SERVER, PORT)
FORMAT = 'utf-8'
DISCONNECT_MESSAGE = "!DISCONNECTED"

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(ADDR)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

clients          = {}   # maps the username to tcp connection
client_udp_ports = {}  
client_local_ips = {}   
groups           = {}   


def handle_client(conn, addr):
    """relays all requests coming from clients and reponds accordly"""
    
    name = None
    try:
        # auth
        msg    = recv_message(conn)
        action = msg["headers"].get("ACTION", "login")
        name   = msg["headers"].get("FROM", "").lower()
        password = msg["headers"].get("PASSWORD", "")

        if action == "register":
            success = add_user(name, password) # succesfful register = add user to database
            if success:
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Account created! You can now log in."})
            else:
                send_message(conn, "CHAT/1.0", "409 ERROR", {"ERROR": "Username already taken."})
            conn.close()
            return

        # login
        result = check_user(name, password)
        if result == "not_found":
            send_message(conn, "CHAT/1.0", "401 ERROR", {"ERROR": "Username incorrect."})
            conn.close()
            return
        if result == "wrong_pass":
            send_message(conn, "CHAT/1.0", "401 ERROR", {"ERROR": "Password incorrect."})
            conn.close()
            return
        if name in clients:
            send_message(conn, "CHAT/1.0", "409 ERROR", {"ERROR": "User already logged in."})
            conn.close()
            return

        clients[name]= conn
        client_udp_ports[name]= msg["headers"].get("UDP-PORT", "")
        client_local_ips[name] =msg["headers"].get("LOCAL-IP", conn.getpeername()[0])
        print(f"[+] {name} connected from {addr}")
        send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Welcome {name}! Login successful."})
        

        #message loop Loops forever waiting for the next message from this client
        while True:
            msg = recv_message(conn)
            if not msg:
                break
 
            path   = msg["path"]
            sender = msg["headers"].get("FROM", "").lower()
            target = msg["headers"].get("TARGET", "").lower()
            body   = msg["body"]
 
            # logout
            if path == "/logout":
                break
 
            # one to one messaging
            elif path == "/message":
                content = body.decode(FORMAT) if isinstance(body, bytes) else body
                if target in clients:# check if recipient is even connected if not send error not connected
                    send_message(clients[target], "POST", "/message",{"FROM": sender, "TARGET": target,"CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")},body)
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Message delivered."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})
                save_message(sender, target, content, "text") # from newly implemented database, save history
 
            # file transfer
            elif path == "/file":
                filename = msg["headers"].get("FILE-NAME", "file")
                if target in clients:
                    send_message(clients[target], "POST", "/file",{"FROM": sender, "TARGET": target, "FILE-NAME": filename},body)
                    send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"File sent to '{target}'."})
                else:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})
                save_message(sender, target, f"[file: {filename}]", "file")
 
            # join group
            elif path == "/join":
                if not target:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "No group specified."})
                    continue
                groups.setdefault(target, set()).add(sender) # setdefault(target, set()) — creates the group if it doesn't exist yet, then adds the sender to it
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You joined group '{target}'."})
 
            # leave the group
            elif path == "/leave":
                if not target or target not in groups or sender not in groups[target]:
                    send_message(conn, "CHAT/1.0", "400 ERROR", {"ERROR": "You are not in that group."})
                    continue
                groups[target].remove(sender)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"You left group '{target}'."})
 
            # send group message
            elif path == "/group-message":
                if not target or target not in groups:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"Group '{target}' does not exist."})
                    continue
                if sender not in groups[target]:
                    send_message(conn, "CHAT/1.0", "403 ERROR", {"ERROR": f"You are not a member of '{target}'."})
                    continue
                content = body.decode(FORMAT) if isinstance(body, bytes) else body
                for member in groups[target]:
                    if member != sender and member in clients:
                        send_message(clients[member], "POST", "/message",{"FROM": sender, "TARGET": target,"CONTENT-TYPE": msg["headers"].get("CONTENT-TYPE", "text")},body)
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": f"Message sent to group '{target}'."})
                save_message(sender, target, content, "group")
 
            # load conversation history( from the data base)
            elif path == "/history":
                history = get_conversation(sender, target)
                payload = json.dumps(history)
                send_message(conn, "CHAT/1.0", "200 OK",{"MESSAGE": "History loaded.", "RESULT-COUNT": len(history)},payload)
 
            # load group conversation history
            elif path == "/group-history":
                history = get_group_conversation(target)
                payload = json.dumps(history)
                send_message(conn, "CHAT/1.0", "200 OK",{"MESSAGE": "Group history loaded.", "RESULT-COUNT": len(history)},payload)
 
            # load the recent contacts, for gui 
            elif path == "/contacts":
                contacts = get_recent_contacts(sender)
                payload  = json.dumps(contacts)
                send_message(conn, "CHAT/1.0", "200 OK",{"MESSAGE": "Contacts loaded.", "RESULT-COUNT": len(contacts)},payload)
 
            # signalling for calls 
            elif path == "/call":
                if target not in clients:
                    send_message(conn, "CHAT/1.0", "404 ERROR", {"ERROR": f"'{target}' is not online."})
                    continue
 
                caller_ip  =client_local_ips.get(sender, conn.getpeername()[0])
                caller_udp =client_udp_ports.get(sender, "")
                target_ip = client_local_ips.get(target, clients[target].getpeername()[0])
                target_udp=client_udp_ports.get(target, "")
 
                if not caller_udp or not target_udp:
                    send_message(conn, "CHAT/1.0", "500 ERROR", {"ERROR": "UDP port unknown for one or both peers."})
                    continue
 
                send_message(clients[target], "POST", "/call",{"FROM": sender, "CALLER-IP": caller_ip, "CALLER-UDP": caller_udp})
                send_message(conn, "CHAT/1.0", "200 OK",{"MESSAGE": "Call initiated.", "PEER-IP": target_ip, "PEER-UDP": target_udp})
 
            elif path == "/call-accept":
                if target in clients:
                    accepter_ip  = client_local_ips.get(sender, conn.getpeername()[0])
                    accepter_udp = client_udp_ports.get(sender, "")
                    send_message(clients[target], "POST", "/call-accept",{"FROM": sender, "PEER-IP": accepter_ip, "PEER-UDP": accepter_udp})
                send_message(conn, "CHAT/1.0", "200 OK", {"MESSAGE": "Acceptance forwarded."})
 
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


# main server launch --  use start()
def start():
    """
    Start the server and accept incoming client connections indefinitely.
 
    Each accepted connection is handed off to handle_client() running in
    its own daemon thread, allowing multiple clients to be served concurrently.
    The main thread remains in the accept loop waiting for new connections.
    """
    server.listen()
    print(f"[LISTENING] SERVER IS LISTENING ON {SERVER}")
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target = handle_client, args=(conn, addr))
        thread.start()
        print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1 }")


print("[STARTING] server is starting .....")
start()
