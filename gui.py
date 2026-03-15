# GUI CLIENT 
# run python3 gui.py directly (server must be launched first)

import socket, threading, os, time, tkinter as tk
from tkinter import filedialog
from protocol import send_message, recv_message, build_audio_packet, parse_audio_packet

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── Network / Audio ───────────────────────────────────────────────────────────
PORT, SERVER, FORMAT = 5050, "13.49.137.214", "utf-8"

CHUNK = 1024; RATE = 44100; CHANNELS = 1
try:
    import pyaudio
    AUDIO_FMT    = pyaudio.paInt16
    audio_engine = pyaudio.PyAudio()
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False; audio_engine = None; AUDIO_FMT = None

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = "#000000"
SURFACE     = "#1c1c1e"
BUBBLE_ME   = "#3797f0"
BUBBLE_THEM = "#262626"
DIVIDER     = "#1c1c1e"
HOVER       = "#111111"
BLUE        = "#3797f0"
PINK        = "#e1306c"
ONLINE_CLR  = "#3ddc84"
TEXT        = "#ffffff"
TEXT_SUB    = "#8e8e8e"

AV_COLORS = ["#3797f0","#e1306c","#f77737","#833ab4","#3ddc84","#ffd600","#00b4d8","#f72585"]
def av_color(n): return AV_COLORS[abs(hash(n)) % len(AV_COLORS)]

# ── Fonts ─────────────────────────────────────────────────────────────────────
try:
    import tkinter.font as tkf
    FF = "SF Pro Text" if tkf.Font(family="SF Pro Text",size=13).actual("family") in ("SF Pro Text",".AppleSystemUIFont") else "Helvetica Neue"
except: FF = "Helvetica Neue"
def F(s, bold=False): return (FF, s+1, "bold") if bold else (FF, s+1)

# ── Widget helpers ─────────────────────────────────────────────────────────────

def avatar(parent, size, name, bg=BG, online=False):
    c = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0, cursor="hand2")
    r = size // 2
    c.create_oval(2, 2, size-2, size-2, fill=av_color(name), outline="")
    c.create_text(r, r, text=(name[0].upper() if name else "?"), font=F(max(9,size//3),True), fill="white")
    if online:
        d = size//5; ox = oy = size-d-1
        c.create_oval(ox-d,oy-d,ox+d,oy+d, fill=ONLINE_CLR, outline=bg, width=2)
    return c

def pill_entry(parent, placeholder="", show=None):
    frame = tk.Frame(parent, bg=SURFACE, highlightthickness=1, highlightbackground=DIVIDER, bd=0)
    e = tk.Entry(frame, font=F(14), fg=TEXT, bg=SURFACE, insertbackground=TEXT,
                 relief="flat", bd=0, highlightthickness=0)
    if show: e.config(show=show)
    e.pack(fill="x", expand=True, padx=14, pady=9)
    if placeholder:
        e.insert(0, placeholder); e.config(fg=TEXT_SUB)
        e.bind("<FocusIn>",  lambda _: (e.delete(0,"end"), e.config(fg=TEXT, show=show or "")) if e.get()==placeholder else None)
        e.bind("<FocusOut>", lambda _: (e.insert(0,placeholder), e.config(fg=TEXT_SUB, show="")) if not e.get() else None)
    e._ph = placeholder
    return frame, e

def btn(parent, text, cmd, primary=True, small=False):
    return tk.Button(parent, text=text, font=F(11 if small else 13),
                     fg=TEXT, bg=BLUE if primary else SURFACE,
                     activebackground=BLUE, activeforeground=TEXT,
                     relief="flat", bd=0, cursor="hand2",
                     padx=10 if small else 16, pady=6 if small else 10, command=cmd)

def hdiv(parent): tk.Frame(parent, bg=DIVIDER, height=1).pack(fill="x")

def icon_lbl(parent, text, cmd, size=19):
    l = tk.Label(parent, text=text, font=F(size), fg=TEXT, bg=BG, cursor="hand2")
    l.bind("<Button-1>", lambda _: cmd())
    return l


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN / REGISTER
# ══════════════════════════════════════════════════════════════════════════════

class LoginScreen(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ChatApp"); self.result = None
        sh = self.winfo_screenheight()
        h = int(sh * 0.82); w = int(h * 9 / 16)
        self.geometry(f"{w}x{h}"); self.resizable(False, False)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._mode = "login"   # "login" or "register"
        self._build()

    # ── Build / rebuild UI ────────────────────────────────────────────────────
    def _build(self):
        for w in self.winfo_children(): w.destroy()

        is_reg = self._mode == "register"

        # Logo
        logo = tk.Frame(self, bg=BG); logo.pack(pady=(50 if is_reg else 70, 0))
        c = tk.Canvas(logo, width=60, height=60, bg=BG, highlightthickness=0); c.pack()
        for i in range(30, 0, -1):
            t = i / 30
            c.create_oval(30-i, 30-i, 30+i, 30+i,
                          fill=f"#{int(240*t+131*(1-t)):02x}{int(148*t+58*(1-t)):02x}{int(51*t+180*(1-t)):02x}",
                          outline="")
        c.create_text(30, 30, text="✦", font=F(22, True), fill="white")
        tk.Label(logo, text="ChatApp", font=F(20, True), fg=TEXT, bg=BG).pack(pady=(10, 0))
        tk.Label(logo,
                 text="Create an account" if is_reg else "Sign in to continue",
                 font=F(11), fg=TEXT_SUB, bg=BG).pack(pady=(4, 0))

        # Form
        form = tk.Frame(self, bg=BG); form.pack(fill="x", padx=40, pady=24)
        uf, self.u = pill_entry(form, "Username"); uf.pack(fill="x", pady=(0, 10))

        pf, self.p = pill_entry(form, "Password"); pf.pack(fill="x", pady=(0, 10 if is_reg else 16))
        self.p.config(show="")
        self.p.bind("<FocusIn>",  lambda _: (self.p.delete(0, "end"), self.p.config(fg=TEXT, show="●")) if self.p.get() == "Password" else None)
        self.p.bind("<FocusOut>", lambda _: (self.p.config(show=""), self.p.insert(0, "Password"), self.p.config(fg=TEXT_SUB)) if not self.p.get() else None)

        # Confirm password — only shown in register mode
        self.c2 = None
        if is_reg:
            cf, self.c2 = pill_entry(form, "Confirm password"); cf.pack(fill="x", pady=(0, 16))
            self.c2.config(show="")
            self.c2.bind("<FocusIn>",  lambda _: (self.c2.delete(0, "end"), self.c2.config(fg=TEXT, show="●")) if self.c2.get() == "Confirm password" else None)
            self.c2.bind("<FocusOut>", lambda _: (self.c2.config(show=""), self.c2.insert(0, "Confirm password"), self.c2.config(fg=TEXT_SUB)) if not self.c2.get() else None)

        # Primary action button
        btn_text = "Create account" if is_reg else "Log in"
        btn_cmd  = self._try_register if is_reg else self._try_login
        tk.Button(form, text=btn_text, font=F(14, True), fg="white", bg=BLUE,
                  activebackground="#2d86d9", activeforeground="white",
                  relief="flat", bd=0, cursor="hand2", pady=11,
                  command=btn_cmd).pack(fill="x", pady=(0, 12))

        # OR divider
        d = tk.Frame(form, bg=BG); d.pack(fill="x", pady=(0, 10))
        tk.Frame(d, bg=DIVIDER, height=1).pack(side="left", fill="x", expand=True, pady=7)
        tk.Label(d, text="  OR  ", font=F(12), fg=TEXT_SUB, bg=BG).pack(side="left")
        tk.Frame(d, bg=DIVIDER, height=1).pack(side="left", fill="x", expand=True, pady=7)

        # Toggle link
        switch_text = "Already have an account?  Log in" if is_reg else "Don't have an account?  Sign up"
        switch_lbl  = tk.Label(form, text=switch_text, font=F(12), fg=BLUE, bg=BG, cursor="hand2")
        switch_lbl.pack(pady=(0, 6))
        switch_lbl.bind("<Button-1>", lambda _: self._toggle_mode())

        # Error label
        self.err = tk.StringVar()
        tk.Label(form, textvariable=self.err, font=F(12), fg=PINK, bg=BG, wraplength=260).pack()

        # Keyboard shortcut
        last_entry = self.c2 if is_reg else self.p
        last_entry.bind("<Return>", lambda _: btn_cmd())
        self.u.focus_set()

    def _toggle_mode(self):
        self._mode = "register" if self._mode == "login" else "login"
        self._build()

    # ── Shared connection helper ──────────────────────────────────────────────
    def _connect_and_send(self, name, pw, action):
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect((SERVER, PORT))
        except:
            self.err.set("Can't reach server."); return
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); udp.bind(("", 0))
        udp_port = udp.getsockname()[1]
        tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); tmp.connect(("8.8.8.8", 80))
        local_ip = tmp.getsockname()[0]; tmp.close()
        send_message(conn, "POST", action,
                     {"FROM": name, "PASSWORD": pw, "UDP-PORT": udp_port, "LOCAL-IP": local_ip})
        resp = recv_message(conn)
        if not resp or not str(resp.get("path", "")).upper().startswith("200"):
            self.err.set((resp or {}).get("headers", {}).get("ERROR", f"{action[1:].capitalize()} failed.") if resp else "No response.")
            conn.close(); return
        self.result = (name, conn, udp, udp_port, local_ip)
        self.destroy()

    def _try_login(self):
        name, pw = self.u.get().strip().lower(), self.p.get().strip()
        if not name or name == "username" or not pw or pw == "password":
            self.err.set("Please fill in all fields."); return
        self._connect_and_send(name, pw, "/login")

    def _try_register(self):
        name = self.u.get().strip().lower()
        pw   = self.p.get().strip()
        pw2  = self.c2.get().strip() if self.c2 else ""
        if not name or name == "username" or not pw or pw == "password":
            self.err.set("Please fill in all fields."); return
        if not pw2 or pw2 == "confirm password":
            self.err.set("Please confirm your password."); return
        if pw != pw2:
            self.err.set("Passwords do not match."); return
        self._connect_and_send(name, pw, "/register")


# ══════════════════════════════════════════════════════════════════════════════
#  CREATE GROUP (in-window, 2-step)
# ══════════════════════════════════════════════════════════════════════════════

class CreateGroupDialog(tk.Frame):
    def __init__(self, parent, on_create):
        super().__init__(parent, bg=BG)
        self.on_create = on_create; self.members = []; self.group_name = ""
        self.app = getattr(parent, "master", None)
        self.pack(fill="both", expand=True); self._step1()

    def _nav(self, title, left_text="✕", left_cmd=None, right_text=None, right_cmd=None):
        self._clear()
        def _close():
            self.destroy()
            if self.app: self.app._build_ui()
        nav = tk.Frame(self, bg=BG); nav.pack(fill="x", padx=16, pady=(14,0))
        lbl = tk.Label(nav, text=left_text, font=F(18), fg=TEXT, bg=BG, cursor="hand2")
        lbl.pack(side="left"); lbl.bind("<Button-1>", lambda _: (left_cmd or _close)())
        tk.Label(nav, text=title, font=F(16,True), fg=TEXT, bg=BG).pack(side="left", expand=True)
        if right_text:
            r = tk.Label(nav, text=right_text, font=F(15,True), fg=BLUE, bg=BG, cursor="hand2")
            r.pack(side="right"); r.bind("<Button-1>", lambda _: right_cmd())
        hdiv(self)

    def _step1(self):
        self._nav("New group", right_text="Next", right_cmd=self._go_step2)
        f = tk.Frame(self, bg=BG); f.pack(fill="x", padx=20, pady=20)
        tk.Label(f, text="Name", font=F(12), fg=TEXT_SUB, bg=BG).pack(anchor="w")
        ff, self.name_e = pill_entry(f); ff.pack(fill="x", pady=(6,0))
        self.err1 = tk.StringVar()
        tk.Label(f, textvariable=self.err1, font=F(11), fg=PINK, bg=BG).pack(anchor="w", pady=(4,0))
        self.name_e.bind("<Return>", lambda _: self._go_step2()); self.name_e.focus_set()

    def _go_step2(self):
        g = self.name_e.get().strip().lower()
        if not g: self.err1.set("Enter a name."); return
        self.group_name = g; self._step2()

    def _step2(self):
        self._nav("Add people", left_text="←", left_cmd=self._step1, right_text="Create", right_cmd=self._confirm)
        add_row = tk.Frame(self, bg=BG); add_row.pack(fill="x", padx=16, pady=(12,0))
        sf, self.m_entry = pill_entry(add_row, "Search"); sf.pack(side="left", fill="x", expand=True)
        btn(add_row, "+ Add", self._add_member, small=True).pack(side="left", padx=(8,0))
        self.m_entry.bind("<Return>", lambda _: self._add_member())
        self.err2 = tk.StringVar()
        tk.Label(self, textvariable=self.err2, font=F(11), fg=PINK, bg=BG).pack(anchor="w", padx=20, pady=(4,0))
        tk.Label(self, text="ADDED", font=F(10), fg=TEXT_SUB, bg=BG).pack(anchor="w", padx=20, pady=(12,4))
        self.list_frame = tk.Frame(self, bg=BG); self.list_frame.pack(fill="both", expand=True, padx=16)
        self._render_members(); self.m_entry.focus_set()

    def _add_member(self):
        m = self.m_entry.get().strip().lower()
        if not m or m=="search": self.err2.set("Enter a username."); return
        if m in self.members: self.err2.set(f"'{m}' already added."); return
        self.members.append(m); self.err2.set(""); self.m_entry.delete(0,"end"); self._render_members()

    def _render_members(self):
        for w in self.list_frame.winfo_children(): w.destroy()
        if not self.members:
            tk.Label(self.list_frame, text="No one added yet", font=F(12), fg=TEXT_SUB, bg=BG).pack(pady=16); return
        for m in self.members:
            row = tk.Frame(self.list_frame, bg=BG); row.pack(fill="x", pady=6)
            avatar(row, 40, m, bg=BG).pack(side="left", padx=(0,12))
            tk.Label(row, text=m, font=F(14,True), fg=TEXT, bg=BG).pack(side="left")
            rm = tk.Label(row, text="✕", font=F(12), fg=TEXT_SUB, bg=BG, cursor="hand2")
            rm.pack(side="right"); rm.bind("<Button-1>", lambda _, n=m: (self.members.remove(n), self._render_members()))

    def _confirm(self):
        if not self.members: self.err2.set("Add at least one person."); return
        self.on_create(self.group_name, list(self.members)); self.destroy()

    def _clear(self):
        for w in self.winfo_children(): w.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN CHAT APP
# ══════════════════════════════════════════════════════════════════════════════

class ChatApp(tk.Tk):
    W, H = 480, 900  # overridden at runtime from screen height

    def __init__(self, name, conn, udp_sock, udp_port, local_ip):
        super().__init__()
        self.name = name; self.conn = conn
        self.udp_sock = udp_sock; self.udp_port = udp_port; self.local_ip = local_ip
        self.active_chat = None; self.chat_history = {}
        self.joined_groups = {}; self.contacts = {}
        self.pending_call = None; self.in_call = False
        self.call_peer = None; self.call_stop = threading.Event()

        self.title("CHATAPP")
        sh = self.winfo_screenheight()
        self.H = int(sh * 0.82); self.W = int(self.H * 9 / 16)
        self.geometry(f"{self.W}x{self.H}")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.container = tk.Frame(self, bg=BG)
        self.container.pack(fill="both", expand=True)
        self._build_ui()
        threading.Thread(target=self._recv_loop, daemon=True).start()
        # Load recent contacts from server on login
        self._pending_history = "contacts"
        send_message(self.conn, "POST", "/contacts", {"FROM": self.name})

    # ── Inbox ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        for w in self.container.winfo_children(): w.destroy()
        self.sidebar = tk.Frame(self.container, bg=BG); self.sidebar.pack(fill="both", expand=True)
        self.right = None; sb = self.sidebar

        top = tk.Frame(sb, bg=BG); top.pack(fill="x", padx=20, pady=(18,10))
        nr = tk.Frame(top, bg=BG); nr.pack(side="left")
        tk.Label(nr, text=self.name, font=F(17,True), fg=TEXT, bg=BG).pack(side="left")
        tk.Label(nr, text=" 🔒", font=F(12), fg=TEXT, bg=BG).pack(side="left")
        icons = tk.Frame(top, bg=BG); icons.pack(side="right")
        icon_lbl(icons, "👥", self._open_create_group).pack(side="left", padx=(0,14))
        icon_lbl(icons, "✏", self._open_new_dm_dialog).pack(side="left")

        sf = tk.Frame(sb, bg=SURFACE); sf.pack(fill="x", padx=16, pady=(0,4))
        tk.Label(sf, text="🔍", font=F(13), fg=TEXT_SUB, bg=SURFACE).pack(side="left", padx=(12,4), pady=8)
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *_: self._refresh_sidebar())
        se = tk.Entry(sf, textvariable=self.search_var, font=F(13), fg=TEXT_SUB,
                      bg=SURFACE, insertbackground=TEXT, relief="flat", bd=0, highlightthickness=0)
        se.insert(0,"Search")
        se.bind("<FocusIn>",  lambda _: (se.delete(0,"end"), se.config(fg=TEXT)) if se.get()=="Search" else None)
        se.bind("<FocusOut>", lambda _: (se.insert(0,"Search"), se.config(fg=TEXT_SUB)) if not se.get() else None)
        se.pack(side="left", fill="x", expand=True, pady=8)

        tab_bar = tk.Frame(sb, bg=BG); tab_bar.pack(fill="x", pady=(8,0))
        self.tab_var = tk.StringVar(value="Messages")
        for label in ("Messages","Groups","Requests"):
            tk.Radiobutton(tab_bar, text=label, variable=self.tab_var, value=label,
                           font=F(13,True), fg=TEXT if label=="Messages" else TEXT_SUB,
                           bg=BG, selectcolor=BG, activebackground=BG, indicatoron=False,
                           relief="flat", bd=0, highlightthickness=0, padx=20, pady=10,
                           cursor="hand2",
                           command=lambda l=label: (self.tab_var.set(l), self._refresh_sidebar())
                           ).pack(side="left")
        hdiv(sb)

        self.list_canvas = tk.Canvas(sb, bg=BG, highlightthickness=0)
        self.list_canvas.pack(fill="both", expand=True)
        self.list_frame = tk.Frame(self.list_canvas, bg=BG)
        self.list_canvas.create_window((0,0), window=self.list_frame, anchor="nw", tags="lf")
        self.list_frame.bind("<Configure>", lambda _: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfig("lf", width=e.width))
        self.list_canvas.bind("<MouseWheel>", lambda e: self.list_canvas.yview_scroll(-1*(e.delta//120),"units"))
        self._refresh_sidebar()

    def _refresh_sidebar(self):
        for w in self.list_frame.winfo_children(): w.destroy()
        tab = self.tab_var.get(); q = self.search_var.get().lower()
        if q == "search": q = ""
        for name, info in list(self.contacts.items()):
            is_grp = name in self.joined_groups
            if tab=="Messages" and is_grp: continue
            if tab=="Groups" and not is_grp: continue
            if q and q not in name.lower(): continue
            self._render_row(name, is_grp, info)

    def _render_row(self, chat_name, is_grp, info):
        unread = info.get("unread",0); online = info.get("online",False)
        history = self.chat_history.get(chat_name,[])
        preview = ""
        if history:
            s, t, ts, mt = history[-1]
            if mt=="file": preview = "📷 Photo" if any(t.lower().endswith(x) for x in (".jpg",".jpeg",".png",".gif")) else "📎 File"
            elif mt not in ("system","invite"): preview = (t[:38]+"…") if len(t)>38 else t

        bg0 = HOVER if chat_name==self.active_chat else BG
        row = tk.Frame(self.list_frame, bg=bg0, cursor="hand2"); row.pack(fill="x")
        inner = tk.Frame(row, bg=bg0); inner.pack(fill="x", padx=16, pady=9)
        av = avatar(inner, 56, chat_name, bg=bg0, online=online and not is_grp)
        av.pack(side="left", padx=(0,12))
        txt = tk.Frame(inner, bg=bg0); txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text=("👥 " if is_grp else "")+chat_name,
                 font=F(14,bool(unread)), fg=TEXT, bg=bg0, anchor="w").pack(fill="x")
        if preview:
            tk.Label(txt, text=preview, font=F(12), fg=TEXT if unread else TEXT_SUB, bg=bg0, anchor="w").pack(fill="x")
        right = tk.Frame(inner, bg=bg0); right.pack(side="right")
        if history: tk.Label(right, text=history[-1][2], font=F(10), fg=TEXT_SUB, bg=bg0).pack(anchor="e")
        if unread:
            dot = tk.Canvas(right, width=20, height=20, bg=bg0, highlightthickness=0)
            dot.create_oval(2,2,18,18, fill=BLUE, outline="")
            dot.create_text(10,10, text=str(unread), font=F(10), fill="white"); dot.pack(anchor="e", pady=(2,0))

        all_w = [row, inner, av, txt, right] + list(txt.winfo_children()) + list(right.winfo_children())
        def _enter(_):
            if chat_name != self.active_chat: [w.config(bg=HOVER) for w in all_w if hasattr(w,"config")]; av.config(bg=HOVER)
        def _leave(_):
            if chat_name != self.active_chat: [w.config(bg=BG) for w in all_w if hasattr(w,"config")]; av.config(bg=BG)
        for w in all_w:
            w.bind("<Enter>",_enter); w.bind("<Leave>",_leave)
            w.bind("<Button-1>", lambda _, c=chat_name: self._open_chat(c))

    # ── Chat pane ─────────────────────────────────────────────────────────────

    def _open_chat(self, chat_name):
        self.active_chat = chat_name
        self.contacts.setdefault(chat_name,{"online":False,"unread":0})
        self.contacts[chat_name]["unread"] = 0
        self.chat_history.setdefault(chat_name,[])
        self._refresh_sidebar()
        for w in self.container.winfo_children(): w.destroy()
        self.right = tk.Frame(self.container, bg=BG); self.right.pack(fill="both", expand=True)
        self._build_chat_pane(chat_name)
        # Request history from server if not loaded yet
        is_grp = chat_name in self.joined_groups
        if not self.chat_history.get(chat_name):
            if is_grp:
                self._pending_history = f"group:{chat_name}"
                send_message(self.conn, "POST", "/group-history", {"FROM": self.name, "TARGET": chat_name})
            else:
                self._pending_history = f"dm:{chat_name}"
                send_message(self.conn, "POST", "/history", {"FROM": self.name, "TARGET": chat_name})

    def _back_to_inbox(self): self.active_chat = None; self._build_ui()

    def _build_chat_pane(self, chat_name):
        for w in self.right.winfo_children(): w.destroy()
        is_grp = chat_name in self.joined_groups

        top = tk.Frame(self.right, bg=BG); top.pack(fill="x")
        icon_lbl(top, "←", self._back_to_inbox, size=18).pack(side="left", padx=(12,6), pady=10)
        avatar(top, 38, chat_name, bg=BG,
               online=self.contacts.get(chat_name,{}).get("online",False) and not is_grp
               ).pack(side="left", padx=(6,10), pady=10)
        meta = tk.Frame(top, bg=BG); meta.pack(side="left", pady=10)
        tk.Label(meta, text=("👥 " if is_grp else "")+chat_name, font=F(14,True), fg=TEXT, bg=BG).pack(anchor="w")
        if is_grp:
            members = self.joined_groups.get(chat_name,[])
            tk.Label(meta, text=", ".join(members) if members else "Tap to add members", font=F(11), fg=TEXT_SUB, bg=BG).pack(anchor="w")
        else:
            online = self.contacts.get(chat_name,{}).get("online",False)
            tk.Label(meta, text="Active now" if online else "CHAT", font=F(11), fg=TEXT_SUB, bg=BG).pack(anchor="w")

        act = tk.Frame(top, bg=BG); act.pack(side="right", padx=16)
        if is_grp:
            icon_lbl(act, "＋", lambda: self._open_add_member_dialog(chat_name)).pack(side="left", padx=(0,18))
        else:
            icon_lbl(act, "📞", lambda: self._do_call(chat_name)).pack(side="left", padx=(0,18))
            icon_lbl(act, "📹", lambda: None).pack(side="left", padx=(0,18))
        icon_lbl(act, "ⓘ", lambda: None).pack(side="left")
        hdiv(self.right)

        self.call_banner = tk.Frame(self.right, bg="#162616")
        tk.Label(self.call_banner, text="🔴  In call", font=F(13), fg="#7fff7f", bg="#162616").pack(side="left", padx=16, pady=8)
        btn(self.call_banner, "End call", lambda: self._do_endcall(chat_name), primary=False).pack(side="right", padx=16, pady=6)
        if self.in_call: self.call_banner.pack(fill="x")

        msg_outer = tk.Frame(self.right, bg=BG); msg_outer.pack(fill="both", expand=True)
        self.msg_canvas = tk.Canvas(msg_outer, bg=BG, highlightthickness=0)
        vsb = tk.Scrollbar(msg_outer, orient="vertical", command=self.msg_canvas.yview, bg=BG, troughcolor=BG, width=4)
        vsb.pack(side="right", fill="y"); self.msg_canvas.configure(yscrollcommand=vsb.set)
        self.msg_canvas.pack(fill="both", expand=True)
        self.msg_canvas.bind("<MouseWheel>", lambda e: self.msg_canvas.yview_scroll(-1*(e.delta//120),"units"))
        self.msg_frame = tk.Frame(self.msg_canvas, bg=BG)
        self.msg_canvas.create_window((0,0), window=self.msg_frame, anchor="nw", tags="mf")
        self.msg_frame.bind("<Configure>", lambda _: self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all")))
        self.msg_canvas.bind("<Configure>", lambda e: self.msg_canvas.itemconfig("mf", width=e.width))

        input_row = tk.Frame(self.right, bg=BG); input_row.pack(fill="x", side="bottom", padx=16, pady=12)
        icon_lbl(input_row, "📷", lambda: self._do_file(chat_name), size=22).pack(side="left", padx=(0,10))
        pill = tk.Frame(input_row, bg=SURFACE, highlightthickness=1, highlightbackground=DIVIDER)
        pill.pack(side="left", fill="x", expand=True, ipady=4)
        self.msg_input = tk.Entry(pill, font=F(14), fg=TEXT_SUB, bg=SURFACE,
                                  insertbackground=TEXT, relief="flat", bd=0, highlightthickness=0)
        self.msg_input.pack(side="left", fill="x", expand=True, padx=14, pady=6)
        self.msg_input.insert(0,"Message…")
        self.msg_input.bind("<FocusIn>",  lambda _: (self.msg_input.delete(0,"end"), self.msg_input.config(fg=TEXT)) if self.msg_input.get()=="Message…" else None)
        self.msg_input.bind("<FocusOut>", lambda _: (self.msg_input.insert(0,"Message…"), self.msg_input.config(fg=TEXT_SUB)) if not self.msg_input.get() else None)
        self.msg_input.bind("<Return>",   lambda _: self._send_message())
        tk.Label(pill, text="😊", font=F(18), fg=TEXT_SUB, bg=SURFACE).pack(side="right", padx=8)
        sc = tk.Canvas(input_row, width=34, height=34, bg=BG, highlightthickness=0, cursor="hand2")
        sc.pack(side="right", padx=(10,0))
        sc.create_oval(2,2,32,32, fill=BLUE, outline=BLUE)
        sc.create_text(17,17, text="➤", fill="white", font=F(16,True))
        sc.bind("<Button-1>", lambda _: self._send_message())
        self.msg_input.focus_set(); self._render_history(chat_name)

    # ── Bubble rendering ──────────────────────────────────────────────────────

    def _render_history(self, chat_name):
        if not hasattr(self,"msg_frame"): return
        for w in self.msg_frame.winfo_children(): w.destroy()
        history = self.chat_history.get(chat_name,[]); prev = None
        for i, (sender, text, ts, mtype) in enumerate(history):
            is_last = i==len(history)-1 or history[i+1][0]!=sender
            self._bubble(sender, text, ts, mtype, show_avatar=is_last,
                         show_sender=(sender!=prev and sender!=self.name and chat_name in self.joined_groups))
            prev = sender
        self._scroll_bottom()

    def _bubble(self, sender, text, ts, mtype, show_avatar=True, show_sender=False):
        if not hasattr(self,"msg_frame"): return
        is_me = sender == self.name
        outer = tk.Frame(self.msg_frame, bg=BG); outer.pack(fill="x", padx=12, pady=1)

        if mtype == "system":
            tk.Label(outer, text=text, font=F(10), fg=TEXT_SUB, bg=BG).pack(anchor="center", pady=4); return

        if mtype == "invite":
            group_name = text; already = group_name in self.joined_groups
            card = tk.Frame(outer, bg=SURFACE, highlightthickness=1, highlightbackground="#2e4a7a")
            card.pack(anchor="w", padx=(50,60), pady=6)
            top_r = tk.Frame(card, bg=SURFACE); top_r.pack(fill="x", padx=14, pady=(12,6))
            avatar(top_r, 38, group_name, bg=SURFACE).pack(side="left", padx=(0,10))
            inf = tk.Frame(top_r, bg=SURFACE); inf.pack(side="left")
            tk.Label(inf, text=f"#{group_name}", font=F(13,True), fg=TEXT, bg=SURFACE).pack(anchor="w")
            tk.Label(inf, text=f"{sender} invited you", font=F(11), fg=TEXT_SUB, bg=SURFACE).pack(anchor="w")
            br = tk.Frame(card, bg=SURFACE); br.pack(fill="x", padx=14, pady=(4,12))
            if already:
                tk.Label(br, text="✓ Already joined", font=F(12), fg=ONLINE_CLR, bg=SURFACE).pack(side="left")
            else:
                btn(br, "Join group", lambda gn=group_name: self._join_group_from_invite(gn), small=True).pack(side="left")
            tk.Label(outer, text=ts, font=F(10), fg=TEXT_SUB, bg=BG).pack(anchor="w", padx=50); return

        row = tk.Frame(outer, bg=BG); row.pack(fill="x", anchor="e" if is_me else "w")
        if not is_me:
            av_frame = tk.Frame(row, bg=BG, width=36); av_frame.pack(side="left", anchor="s", padx=(0,6))
            if show_avatar: avatar(av_frame, 28, sender, bg=BG).pack()
        bf = tk.Frame(row, bg=BG); bf.pack(side="right" if is_me else "left", anchor="e" if is_me else "w")
        if show_sender:
            tk.Label(bf, text=sender, font=F(10), fg=TEXT_SUB, bg=BG).pack(anchor="w", padx=14, pady=(0,2))

        bbg = BUBBLE_ME if is_me else BUBBLE_THEM
        if mtype == "file":
            parts = text.split("||",1); filepath=parts[0]; filename=parts[1] if len(parts)>1 else parts[0]
            is_img = os.path.splitext(filename)[1].lower() in (".jpg",".jpeg",".png",".gif",".webp",".bmp")
            if is_img and PIL_AVAILABLE and os.path.exists(filepath):
                try:
                    img = Image.open(filepath); img.thumbnail((260,300))
                    photo = ImageTk.PhotoImage(img)
                    lbl = tk.Label(bf, image=photo, bg=bbg, cursor="hand2", bd=0, relief="flat")
                    lbl.image = photo; lbl.pack(anchor="e" if is_me else "w")
                    def open_img(_, p=filepath):
                        import subprocess, sys
                        if sys.platform=="darwin": subprocess.Popen(["open",p])
                        elif sys.platform=="win32": os.startfile(p)
                        else: subprocess.Popen(["xdg-open",p])
                    lbl.bind("<Button-1>", open_img); return
                except: pass
            tk.Label(bf, text="📎 "+filename, font=F(12), fg=TEXT, bg=bbg, padx=14, pady=10
                     ).pack(anchor="e" if is_me else "w")
        else:
            tk.Label(bf, text=text, font=F(14), fg=TEXT, bg=bbg,
                     padx=14, pady=9, wraplength=280, justify="left", anchor="w"
                     ).pack(anchor="e" if is_me else "w")
        if show_avatar:
            tk.Label(outer, text=ts, font=F(10), fg=TEXT_SUB, bg=BG
                     ).pack(anchor="e" if is_me else "w", padx=50 if not is_me else 10)

    def _add_message(self, chat_name, sender, text, mtype="text"):
        self.chat_history.setdefault(chat_name,[])
        self.chat_history[chat_name].append((sender, text, time.strftime("%H:%M"), mtype))
        if chat_name == self.active_chat:
            self._render_history(chat_name)
        else:
            self.contacts.setdefault(chat_name,{"online":False,"unread":0})
            self.contacts[chat_name]["unread"] += 1; self._refresh_sidebar()

    def _scroll_bottom(self):
        self.after(80, lambda: self.msg_canvas.yview_moveto(1.0) if hasattr(self,"msg_canvas") else None)

    def _join_group_from_invite(self, group_name):
        send_message(self.conn,"POST","/join",{"FROM":self.name,"TARGET":group_name})
        self.joined_groups[group_name]=[]; self.contacts[group_name]={"online":True,"unread":0}
        self.chat_history.setdefault(group_name,[])
        self._refresh_sidebar()
        if self.active_chat: self._render_history(self.active_chat)
        self._open_chat(group_name)

    # ── Network actions ───────────────────────────────────────────────────────

    def _send_message(self):
        if not self.active_chat or not hasattr(self,"msg_input"): return
        text = self.msg_input.get().strip()
        if not text or text=="Message…": return
        self.msg_input.delete(0,"end")
        path = "/group-message" if self.active_chat in self.joined_groups else "/message"
        send_message(self.conn,"POST",path,{"FROM":self.name,"TARGET":self.active_chat,"CONTENT-TYPE":"text"},text)
        self._add_message(self.active_chat, self.name, text)

    def _do_file(self, target):
        path = filedialog.askopenfilename(title="Send photo or file")
        if path: threading.Thread(target=self._send_file, args=(target,path), daemon=True).start()

    def _send_file(self, target, filepath):
        filename = os.path.basename(filepath)
        with open(filepath,"rb") as f: data = f.read()
        if target in self.joined_groups:
            for m in self.joined_groups.get(target,[]): send_message(self.conn,"POST","/file",{"FROM":self.name,"TARGET":m,"FILE-NAME":filename},data)
        else:
            send_message(self.conn,"POST","/file",{"FROM":self.name,"TARGET":target,"FILE-NAME":filename},data)
        self.after(0, self._add_message, target, self.name, f"{filepath}||{filename}", "file")

    def _do_call(self, target):
        if not AUDIO_AVAILABLE: self._add_message(target,"System","pyaudio not installed — calls unavailable","system"); return
        if self.in_call: self._add_message(target,"System","Already in a call","system"); return
        send_message(self.conn,"POST","/call",{"FROM":self.name,"TARGET":target})
        self._add_message(target,"System",f"Calling {target}…","system")

    def _do_endcall(self, target):
        send_message(self.conn,"POST","/endcall",{"FROM":self.name,"TARGET":target}); self._end_audio_call()

    def _start_audio_call(self, peer_ip, peer_udp):
        self.in_call=True; self.call_peer=(peer_ip,peer_udp); self.call_stop.clear()
        threading.Thread(target=self._audio_send, args=(peer_ip,peer_udp), daemon=True).start()
        threading.Thread(target=self._audio_recv, daemon=True).start()
        if hasattr(self,"call_banner"): self.call_banner.pack(fill="x")

    def _end_audio_call(self):
        self.call_stop.set(); self.in_call=False; self.call_peer=None
        if hasattr(self,"call_banner"): self.call_banner.pack_forget()

    def _audio_send(self, peer_ip, peer_udp):
        stream = audio_engine.open(format=AUDIO_FMT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
        seq = 0
        while not self.call_stop.is_set():
            try:
                chunk = stream.read(CHUNK, exception_on_overflow=False)
                self.udp_sock.sendto(build_audio_packet(self.name,seq,chunk),(peer_ip,peer_udp)); seq+=1
            except: break
        stream.stop_stream(); stream.close()

    def _audio_recv(self):
        stream = audio_engine.open(format=AUDIO_FMT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)
        self.udp_sock.settimeout(1.0)
        while not self.call_stop.is_set():
            try:
                data,_ = self.udp_sock.recvfrom(65535); pkt = parse_audio_packet(data)
                if pkt: stream.write(pkt["chunk"])
            except socket.timeout: continue
            except: break
        self.udp_sock.settimeout(None); stream.stop_stream(); stream.close()

    # ── Group management ──────────────────────────────────────────────────────

    def _open_create_group(self):
        for w in self.container.winfo_children(): w.destroy()
        self.right = None; CreateGroupDialog(self.container, self._create_group)

    def _create_group(self, group_name, members):
        send_message(self.conn,"POST","/join",{"FROM":self.name,"TARGET":group_name})
        self.joined_groups[group_name]=list(members); self.contacts[group_name]={"online":True,"unread":0}
        self.chat_history.setdefault(group_name,[])
        for m in members:
            send_message(self.conn,"POST","/message",{"FROM":self.name,"TARGET":m,"CONTENT-TYPE":"text"},f"📢 You've been added to group '{group_name}'.")
        self._refresh_sidebar(); self._open_chat(group_name)
        self._add_message(group_name,"System",f"Group '{group_name}' created  ·  {', '.join(members)}","system")

    def _open_add_member_dialog(self, group_name):
        overlay = tk.Frame(self.right, bg=BG)
        overlay.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)
        nav = tk.Frame(overlay, bg=BG); nav.pack(fill="x", padx=16, pady=(14,0))
        x = tk.Label(nav, text="✕", font=F(18), fg=TEXT, bg=BG, cursor="hand2"); x.pack(side="left")
        x.bind("<Button-1>", lambda _: overlay.destroy())
        tk.Label(nav, text=f"Add to #{group_name}", font=F(15,True), fg=TEXT, bg=BG).pack(side="left", expand=True)
        hdiv(overlay)
        f = tk.Frame(overlay, bg=BG); f.pack(fill="x", padx=20, pady=16)
        ff, entry = pill_entry(f,"Username"); ff.pack(fill="x", pady=(0,8))
        err = tk.StringVar()
        tk.Label(f, textvariable=err, font=F(11), fg=PINK, bg=BG).pack(anchor="w")
        def do_add():
            m = entry.get().strip().lower()
            if not m or m=="username": err.set("Enter a username."); return
            if m in self.joined_groups.get(group_name,[]): err.set(f"'{m}' already in group."); return
            self.joined_groups.setdefault(group_name,[]).append(m)
            send_message(self.conn,"POST","/message",{"FROM":self.name,"TARGET":m,"CONTENT-TYPE":"text"},f"📢 You've been added to group '{group_name}'.")
            self._add_message(group_name,"System",f"{m} was added to the group.","system")
            self._build_chat_pane(group_name); overlay.destroy()
        btn(f,"Add",do_add).pack(fill="x",pady=(10,0))
        entry.bind("<Return>", lambda _: do_add()); entry.focus_set()

    def _open_new_dm_dialog(self):
        overlay = tk.Frame(self.container, bg=BG); overlay.pack(fill="both", expand=True)
        nav = tk.Frame(overlay, bg=BG); nav.pack(fill="x", padx=16, pady=(14,0))
        x = tk.Label(nav, text="✕", font=F(18), fg=TEXT, bg=BG, cursor="hand2"); x.pack(side="left")
        x.bind("<Button-1>", lambda _: (overlay.destroy(), self._build_ui()))
        tk.Label(nav, text="New message", font=F(15,True), fg=TEXT, bg=BG).pack(side="left", expand=True)
        hdiv(overlay)
        f = tk.Frame(overlay, bg=BG); f.pack(fill="x", padx=20, pady=16)
        tk.Label(f, text="To:", font=F(13), fg=TEXT_SUB, bg=BG).pack(anchor="w", pady=(0,6))
        ff, entry = pill_entry(f); ff.pack(fill="x", pady=(0,16))
        def do_open():
            t = entry.get().strip().lower()
            if t:
                self.contacts.setdefault(t,{"online":False,"unread":0}); self.chat_history.setdefault(t,[])
                overlay.destroy(); self._open_chat(t)
        btn(f,"Chat",do_open).pack(fill="x")
        entry.bind("<Return>", lambda _: do_open()); entry.focus_set()

    def _show_incoming_call_dialog(self, caller, caller_ip, caller_udp):
        overlay = tk.Frame(self.container, bg=BG); overlay.pack(fill="both", expand=True)
        tk.Label(overlay, text="📞  Incoming call", font=F(16,True), fg=TEXT, bg=BG).pack(pady=(40,8))
        tk.Label(overlay, text=f"from  {caller}", font=F(14), fg=TEXT_SUB, bg=BG).pack(pady=(0,26))
        btns = tk.Frame(overlay, bg=BG); btns.pack()
        def accept():
            send_message(self.conn,"POST","/call-accept",{"FROM":self.name,"TARGET":caller})
            if AUDIO_AVAILABLE: self._start_audio_call(caller_ip, caller_udp)
            self.pending_call=None; self.contacts.setdefault(caller,{"online":True,"unread":0})
            self._add_message(caller,"System",f"Call with {caller} started.","system"); overlay.destroy()
        def reject():
            send_message(self.conn,"POST","/endcall",{"FROM":self.name,"TARGET":caller})
            self.pending_call=None; overlay.destroy()
        btn(btns,"Accept",accept).pack(side="left",padx=10)
        btn(btns,"Decline",reject,primary=False).pack(side="left",padx=10)

    # ── Receive loop ──────────────────────────────────────────────────────────

    def _recv_loop(self):
        while True:
            try:
                msg = recv_message(self.conn)
                if not msg: break
                self.after(0, self._handle_msg, msg)
            except: break

    def _handle_msg(self, msg):
        import json as _json
        method=msg["method"]; path=msg["path"]
        if method == "CHAT/1.0":
            info = msg["headers"].get("ERROR") or msg["headers"].get("MESSAGE","")
            if "PEER-IP" in msg["headers"] and "PEER-UDP" in msg["headers"] and not self.in_call:
                if AUDIO_AVAILABLE: self._start_audio_call(msg["headers"]["PEER-IP"], int(msg["headers"]["PEER-UDP"]))
                if self.active_chat: self._add_message(self.active_chat,"System","Call connected.","system")
            elif hasattr(self, "_pending_history") and self._pending_history and "200" in str(path):
                raw = msg["body"].decode(FORMAT) if isinstance(msg["body"], bytes) else msg["body"]
                pending = self._pending_history
                self._pending_history = None
                if pending == "contacts":
                    contacts = _json.loads(raw) if raw else []
                    for c in contacts:
                        self.contacts.setdefault(c, {"online": False, "unread": 0})
                        self.chat_history.setdefault(c, [])
                    self._refresh_sidebar()
                elif pending.startswith("dm:"):
                    target = pending[3:]
                    history = _json.loads(raw) if raw else []
                    for m in history:
                        ts = m["sent_at"][11:16]  # just HH:MM
                        self.chat_history.setdefault(target, []).append(
                            (m["sender"], m["content"], ts, m.get("msg_type","text"))
                        )
                    if self.active_chat == target:
                        self._build_chat_pane(target)
                elif pending.startswith("group:"):
                    grp = pending[6:]
                    history = _json.loads(raw) if raw else []
                    for m in history:
                        ts = m["sent_at"][11:16]
                        self.chat_history.setdefault(grp, []).append(
                            (m["sender"], m["content"], ts, m.get("msg_type","text"))
                        )
                    if self.active_chat == grp:
                        self._build_chat_pane(grp)
            elif info and "delivered" not in info.lower() and "forwarded" not in info.lower() and "loaded" not in info.lower():
                chat = self.active_chat or "__system__"
                self.contacts.setdefault(chat,{"online":False,"unread":0}); self.chat_history.setdefault(chat,[])
                self._add_message(chat,"System",info,"system")
        elif method=="POST" and path=="/message":
            import re
            sender=msg["headers"].get("FROM","?"); target=msg["headers"].get("TARGET","")
            body = msg["body"].decode(FORMAT) if isinstance(msg["body"],bytes) else msg["body"]
            chat = target if target in self.joined_groups else sender
            self.contacts.setdefault(chat,{"online":True,"unread":0}); self.chat_history.setdefault(chat,[])
            inv = re.search(r"added to group '([^']+)'", body)
            self._add_message(chat, sender, inv.group(1) if inv else body, "invite" if inv else "text")
        elif method=="POST" and path=="/file":
            sender=msg["headers"].get("FROM","?"); filename=msg["headers"].get("FILE-NAME","file")
            save_path = os.path.join(os.path.expanduser("~"),"Downloads",f"received_{filename}")
            os.makedirs(os.path.dirname(save_path),exist_ok=True)
            with open(save_path,"wb") as f: f.write(msg["body"])
            self.contacts.setdefault(sender,{"online":True,"unread":0})
            self._add_message(sender,sender,f"{save_path}||{filename}","file")
        elif method=="POST" and path=="/call":
            caller=msg["headers"].get("FROM","?"); caller_ip=msg["headers"].get("CALLER-IP")
            caller_udp=int(msg["headers"].get("CALLER-UDP",0))
            self.pending_call=(caller,caller_ip,caller_udp)
            self.contacts.setdefault(caller,{"online":True,"unread":0})
            self._show_incoming_call_dialog(caller,caller_ip,caller_udp)
        elif method=="POST" and path=="/call-accept":
            if AUDIO_AVAILABLE: self._start_audio_call(msg["headers"].get("PEER-IP"),int(msg["headers"].get("PEER-UDP",0)))
            if self.active_chat: self._add_message(self.active_chat,"System","Call accepted.","system")
        elif method=="POST" and path=="/endcall":
            caller=msg["headers"].get("FROM","?"); self._end_audio_call()
            self.contacts.setdefault(caller,{"online":True,"unread":0})
            self._add_message(caller,"System",f"{caller} ended the call.","system")

    def on_close(self):
        try: send_message(self.conn,"POST","/logout",{"FROM":self.name}); self.conn.close()
        except: pass
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    login = LoginScreen(); login.mainloop()
    if not login.result: return
    app = ChatApp(*login.result)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

if __name__ == "__main__":
    main()