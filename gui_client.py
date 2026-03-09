import socket
import threading
import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from protocol import send_message, recv_message, build_udp_packet, parse_udp_packet


PORT = 5050
SERVER = "localhost"
FORMAT = "utf-8"
ADDR = (SERVER, PORT)
DISCONNECT_MESSAGE = "!DISCONNECT"
CHUNK_SIZE = 1024


class ChatClientGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Chat App")
        self.root.geometry("900x600")

        try:
            self.root.tk.call("source", os.path.join(os.path.dirname(__file__), "azure.tcl"))
            self.root.tk.call("set_theme", "dark")
        except Exception:
            style = ttk.Style(self.root)
            style.theme_use("clam")

        self.client: socket.socket | None = None
        self.udp_sock: socket.socket | None = None
        self.udp_port: int | None = None
        self.name: str | None = None

        self.joined_groups: set[str] = set()

        self.peer_udp_response = None
        self.peer_udp_event = threading.Event()

        self._build_login_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_login_ui(self) -> None:
        for w in self.root.winfo_children():
            w.destroy()

        container = ttk.Frame(self.root, padding=40)
        container.pack(expand=True)

        title = ttk.Label(container, text="Chat Login", font=("Helvetica", 24, "bold"))
        title.grid(row=0, column=0, columnspan=2, pady=(0, 30))

        user_label = ttk.Label(container, text="Username")
        user_label.grid(row=1, column=0, sticky="e", pady=5, padx=(0, 10))
        self.username_var = tk.StringVar()
        user_entry = ttk.Entry(container, textvariable=self.username_var, width=30)
        user_entry.grid(row=1, column=1, sticky="w", pady=5)

        pass_label = ttk.Label(container, text="Password")
        pass_label.grid(row=2, column=0, sticky="e", pady=5, padx=(0, 10))
        self.password_var = tk.StringVar()
        pass_entry = ttk.Entry(container, textvariable=self.password_var, show="•", width=30)
        pass_entry.grid(row=2, column=1, sticky="w", pady=5)

        login_btn = ttk.Button(container, text="Login", command=self.handle_login, width=20)
        login_btn.grid(row=3, column=0, columnspan=2, pady=(20, 0))

        container.columnconfigure(0, weight=0)
        container.columnconfigure(1, weight=1)

        user_entry.focus_set()
        self.root.bind("<Return>", lambda _event: self.handle_login())

    def _build_chat_ui(self) -> None:
        for w in self.root.winfo_children():
            w.destroy()

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=3)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)

        header = ttk.Frame(main)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text=f"Logged in as {self.name}", font=("Helvetica", 14, "bold"))
        title.grid(row=0, column=0, sticky="w")

        logout_btn = ttk.Button(header, text="Logout", command=self.logout)
        logout_btn.grid(row=0, column=1, sticky="e")

        chat_frame = ttk.Frame(main)
        chat_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        chat_frame.rowconfigure(0, weight=1)
        chat_frame.columnconfigure(0, weight=1)

        self.chat_text = tk.Text(
            chat_frame,
            wrap="word",
            state="disabled",
            bg="#111111",
            fg="#f5f5f5",
            insertbackground="#ffffff",
        )
        chat_scroll = ttk.Scrollbar(chat_frame, command=self.chat_text.yview)
        self.chat_text.configure(yscrollcommand=chat_scroll.set)

        self.chat_text.grid(row=0, column=0, sticky="nsew")
        chat_scroll.grid(row=0, column=1, sticky="ns")

        input_frame = ttk.Frame(main)
        input_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        input_frame.columnconfigure(1, weight=1)

        to_label = ttk.Label(input_frame, text="To")
        to_label.grid(row=0, column=0, sticky="w")
        self.to_var = tk.StringVar()
        to_entry = ttk.Entry(input_frame, textvariable=self.to_var)
        to_entry.grid(row=0, column=1, sticky="ew", padx=(5, 5))

        join_btn = ttk.Button(input_frame, text="Join group", command=self.join_group)
        join_btn.grid(row=0, column=2, padx=(5, 0))
        leave_btn = ttk.Button(input_frame, text="Leave group", command=self.leave_group)
        leave_btn.grid(row=0, column=3, padx=(5, 0))

        msg_label = ttk.Label(input_frame, text="Message")
        msg_label.grid(row=1, column=0, sticky="nw", pady=(10, 0))
        self.msg_entry = tk.Text(input_frame, height=3, wrap="word")
        self.msg_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(10, 0))

        send_btn = ttk.Button(input_frame, text="Send", command=self.send_message_text)
        send_btn.grid(row=1, column=3, sticky="nsew", padx=(5, 0), pady=(10, 0))

        attach_btn = ttk.Button(input_frame, text="Send File…", command=self.send_file)
        attach_btn.grid(row=2, column=3, sticky="e", padx=(5, 0), pady=(10, 0))

        side = ttk.Frame(main)
        side.grid(row=1, column=1, rowspan=2, sticky="nsew")
        side.rowconfigure(1, weight=1)
        side.columnconfigure(0, weight=1)

        groups_label = ttk.Label(side, text="Joined groups", font=("Helvetica", 11, "bold"))
        groups_label.grid(row=0, column=0, sticky="w")

        self.groups_list = tk.Listbox(side, height=8)
        self.groups_list.grid(row=1, column=0, sticky="nsew", pady=(5, 0))

        self.msg_entry.bind("<Control-Return>", lambda _e: self.send_message_text())
        self.msg_entry.bind("<Command-Return>", lambda _e: self.send_message_text())

    def append_chat(self, text: str) -> None:
        def _append() -> None:
            self.chat_text.configure(state="normal")
            self.chat_text.insert("end", text + "\n")
            self.chat_text.see("end")
            self.chat_text.configure(state="disabled")

        self.root.after(0, _append)

    def refresh_groups_list(self) -> None:
        def _refresh() -> None:
            self.groups_list.delete(0, "end")
            for g in sorted(self.joined_groups):
                self.groups_list.insert("end", g)

        self.root.after(0, _refresh)

    def handle_login(self) -> None:
        username = self.username_var.get().strip().lower()
        password = self.password_var.get().strip()

        if not username or not password:
            messagebox.showwarning("Missing info", "Please enter username and password.")
            return

        try:
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect(ADDR)

            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.bind(("", 0))
            self.udp_port = self.udp_sock.getsockname()[1]

            send_message(
                self.client,
                "POST",
                "/login",
                {"FROM": username, "PASSWORD": password, "UDP-PORT": self.udp_port},
            )

            response = recv_message(self.client)
            status = response["path"]
            info = response["headers"].get("ERROR") or response["headers"].get("MESSAGE", "")

            if "ERROR" in status:
                messagebox.showerror("Login failed", info or "Unknown error.")
                self.client.close()
                self.client = None
                if self.udp_sock:
                    self.udp_sock.close()
                    self.udp_sock = None
                return

            self.name = username
            self.joined_groups = set()

            self._build_chat_ui()
            self.append_chat(f"[Server]: {info or 'Login successful.'}")

            threading.Thread(target=self.receive_loop, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Connection error", str(exc))
            if self.client:
                self.client.close()
                self.client = None
            if self.udp_sock:
                self.udp_sock.close()
                self.udp_sock = None

    def logout(self) -> None:
        try:
            if self.client and self.name:
                send_message(self.client, "POST", "/logout", {"FROM": self.name})
        except Exception:
            pass

        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass

        self.client = None
        self.udp_sock = None
        self.name = None
        self.joined_groups = set()

        self._build_login_ui()

    def on_close(self) -> None:
        self.logout()
        self.root.destroy()

    def join_group(self) -> None:
        if not self.client or not self.name:
            return
        target = self.to_var.get().strip().lower()
        if not target:
            messagebox.showinfo("Group", "Enter a group name in the 'To' field.")
            return
        send_message(self.client, "POST", "/join", {"FROM": self.name, "TARGET": target})
        self.joined_groups.add(target)
        self.refresh_groups_list()

    def leave_group(self) -> None:
        if not self.client or not self.name:
            return
        target = self.to_var.get().strip().lower()
        if not target:
            messagebox.showinfo("Group", "Enter a group name in the 'To' field.")
            return
        send_message(self.client, "POST", "/leave", {"FROM": self.name, "TARGET": target})
        self.joined_groups.discard(target)
        self.refresh_groups_list()

    def send_message_text(self) -> None:
        if not self.client or not self.name:
            return

        target = self.to_var.get().strip().lower()
        content = self.msg_entry.get("1.0", "end").strip()

        if not target:
            messagebox.showinfo("Missing target", "Enter a username or group name in the 'To' field.")
            return
        if not content:
            return

        if target in self.joined_groups:
            send_message(
                self.client,
                "POST",
                "/group-message",
                {"FROM": self.name, "TARGET": target, "CONTENT-TYPE": "text"},
                content,
            )
            tag = f"group:{target}"
        else:
            send_message(
                self.client,
                "POST",
                "/message",
                {"FROM": self.name, "TARGET": target, "CONTENT-TYPE": "text"},
                content,
            )
            tag = target

        self.append_chat(f"[{tag}] {self.name}: {content}")
        self.msg_entry.delete("1.0", "end")

    def send_file(self) -> None:
        if not self.client or not self.name or not self.udp_sock:
            return

        target = self.to_var.get().strip().lower()
        if not target:
            messagebox.showinfo("Missing target", "Enter a username in the 'To' field to send a file.")
            return

        filepath = filedialog.askopenfilename()
        if not filepath:
            return

        threading.Thread(
            target=self._udp_send_file_thread,
            args=(target, filepath),
            daemon=True,
        ).start()

    def _udp_send_file_thread(self, target: str, filepath: str) -> None:
        if not self.client or not self.udp_sock or not self.name:
            return

        self.peer_udp_event.clear()

        send_message(self.client, "POST", "/get-peer-udp", {"FROM": self.name, "TARGET": target})
        self.peer_udp_event.wait(timeout=5)

        response = self.peer_udp_response
        if not response or "ERROR" in response["path"]:
            error = response["headers"].get("ERROR") if response else "No response from server."
            self.append_chat(f"[Server]: {error}")
            return

        peer_ip = response["headers"].get("PEER-IP")
        peer_port = int(response["headers"].get("PEER-PORT"))

        with open(filepath, "rb") as f:
            data = f.read()

        filename = os.path.basename(filepath)
        chunks = [data[i : i + CHUNK_SIZE] for i in range(0, len(data), CHUNK_SIZE)]
        total = len(chunks)

        send_message(
            self.client,
            "POST",
            "/message",
            {
                "FROM": self.name,
                "TARGET": target,
                "CONTENT-TYPE": "file-incoming",
                "SENDER-IP": self.client.getsockname()[0],
                "SENDER-UDP": self.udp_port,
            },
            f"FILE:{filename}:{total}",
        )

        self.append_chat(f"[FILE] Waiting for {target} to be ready...")
        self.udp_sock.settimeout(10.0)
        try:
            while True:
                data_in, _ = self.udp_sock.recvfrom(64)
                if data_in == b"READY":
                    break
        except socket.timeout:
            self.append_chat(f"[FILE] {target} did not respond in time. Aborting.")
            self.udp_sock.settimeout(None)
            return
        self.udp_sock.settimeout(None)

        self.append_chat(f"[FILE] Sending '{filename}' ({total} chunks)...")
        for seq, chunk in enumerate(chunks):
            packet = build_udp_packet(self.name, seq, total, chunk)
            self.udp_sock.sendto(packet, (peer_ip, peer_port))
            time.sleep(0.001)

        self.append_chat(f"[FILE] Sent '{filename}' to {target} ({total} chunks).")

    def _udp_receive_file(self, sender: str, filename: str, total_chunks: int, sender_ip: str, sender_udp_port: int) -> None:
        if not self.udp_sock:
            return

        self.append_chat(f"[FILE] Receiving '{filename}' from {sender} ({total_chunks} chunks)...")

        self.udp_sock.sendto(b"READY", (sender_ip, sender_udp_port))

        received: dict[int, bytes] = {}
        self.udp_sock.settimeout(5.0)

        while len(received) < total_chunks:
            try:
                data, _ = self.udp_sock.recvfrom(65535)
                if data == b"READY":
                    continue
                packet = parse_udp_packet(data)
                if packet and packet["sender"] == sender:
                    received[packet["seq"]] = packet["chunk"]
                    if len(received) % 20 == 0:
                        self.append_chat(f"[FILE] Progress: {len(received)}/{total_chunks}")
            except socket.timeout:
                self.append_chat(f"[FILE] Timed out — received {len(received)}/{total_chunks} chunks.")
                break

        self.udp_sock.settimeout(None)

        if len(received) == total_chunks:
            file_data = b"".join(received[i] for i in sorted(received))
            out_name = f"received_{filename}"
            with open(out_name, "wb") as f:
                f.write(file_data)
            self.append_chat(f"[FILE] Saved as '{out_name}'.")
        else:
            self.append_chat("[FILE] Incomplete transfer — file not saved.")

    def receive_loop(self) -> None:
        while self.client:
            try:
                msg = recv_message(self.client)
                if not msg:
                    break

                method = msg["method"]
                path = msg["path"]

                if method == "CHAT/1.0":
                    if "PEER-IP" in msg["headers"]:
                        self.peer_udp_response = msg
                        self.peer_udp_event.set()
                    else:
                        info = msg["headers"].get("ERROR") or msg["headers"].get("MESSAGE", "")
                        if info:
                            self.append_chat(f"[Server {path}]: {info}")

                elif method == "POST" and path == "/message":
                    sender = msg["headers"].get("FROM", "?")
                    target = msg["headers"].get("TARGET", "")
                    content_type = msg["headers"].get("CONTENT-TYPE", "text")
                    body = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]

                    if content_type == "file-incoming":
                        sender_ip = msg["headers"].get("SENDER-IP", "")
                        sender_udp = int(msg["headers"].get("SENDER-UDP", 0))
                        _, filename, total = body.split(":")
                        threading.Thread(
                            target=self._udp_receive_file,
                            args=(sender, filename, int(total), sender_ip, sender_udp),
                            daemon=True,
                        ).start()
                    else:
                        tag = f"group:{target}" if target in self.joined_groups else sender
                        self.append_chat(f"[{tag}] {sender}: {body}")
            except Exception:
                break


def main() -> None:
    root = tk.Tk()
    ChatClientGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

