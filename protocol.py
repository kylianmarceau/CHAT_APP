# PROTOCOL SPECIFICATION

FORMAT = 'utf-8'

# Supported CONTENT-TYPE values for file transfer (matches Stage 1 spec)
CONTENT_TYPES = {
    ".txt":  "text/plain",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".mp4":  "video/mp4",
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
    ".pdf":  "application/pdf",
}

def get_content_type(filename):
    """Return the CONTENT-TYPE string for a given filename."""
    import os
    ext = os.path.splitext(filename)[1].lower()
    return CONTENT_TYPES.get(ext, "application/octet-stream")

def build_message(method, path, headers={}, body=""):
    """Build an HTTP-like CHAT protocol message."""
    if isinstance(body, str):
        body_bytes = body.encode(FORMAT)
    else:
        body_bytes = body  # already bytes (for files/images)

    start_line = f"{method} {path} CHAT/1.0\r\n"
    headers["CONTENT-LENGTH"] = len(body_bytes)

    header_lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    head = (start_line + header_lines + "\r\n").encode(FORMAT)

    return head + body_bytes


def parse_message(raw_bytes):
    """Parse a raw CHAT protocol message into a dict."""
    if b"\r\n\r\n" in raw_bytes:
        head, body = raw_bytes.split(b"\r\n\r\n", 1)
    else:
        head = raw_bytes
        body = b""

    lines = head.decode(FORMAT).split("\r\n")
    start_line = lines[0].split(" ")

    headers = {}
    for line in lines[1:]:
        if ": " in line:
            k, v = line.split(": ", 1)
            headers[k.upper()] = v

    content_length = int(headers.get("CONTENT-LENGTH", 0))
    body = body[:content_length]

    return {
        "method": start_line[0] if len(start_line) > 1 else "",
        "path": start_line[1] if len(start_line) > 1 else start_line[0],
        "headers": headers,
        "body": body
    }


def send_message(sock, method, path, headers={}, body=""):
    """Build and send a message over a socket."""
    msg = build_message(method, path, headers, body)
    # Send total length first (8 bytes) so receiver knows how much to read
    length = str(len(msg)).ljust(8).encode(FORMAT)
    sock.sendall(length + msg)


def recv_message(sock):
    """Receive and parse a message from a socket."""
    # Read exactly 8 bytes for the length prefix (recv may return fewer)
    raw_len = b""
    while len(raw_len) < 8:
        chunk = sock.recv(8 - len(raw_len))
        if not chunk:
            return None
        raw_len += chunk
    total = int(raw_len.decode(FORMAT).strip())

    # Read exactly that many bytes
    data = b""
    while len(data) < total:
        chunk = sock.recv(total - len(data))
        if not chunk:
            break
        data += chunk

    return parse_message(data)