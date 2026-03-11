# PROTOCOL SPECIFICATION

FORMAT = 'utf-8'

def build_message(method, path, headers={}, body=""):
    
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

    return {"method": start_line[0] if len(start_line) > 1 else "","path": start_line[1] if len(start_line) > 1 else start_line[0],"headers": headers,"body": body}


def send_message(sock, method, path, headers={}, body=""):
    msg = build_message(method, path, headers, body)
    length = str(len(msg)).ljust(8).encode(FORMAT)
    sock.send(length + msg)


def recv_message(sock):
    raw_len = sock.recv(8)
    if not raw_len:
        return None
    total = int(raw_len.decode(FORMAT).strip())

    # read specified byte amount
    data = b""
    while len(data) < total:
        chunk = sock.recv(total - len(data))
        if not chunk:
            break
        data += chunk

    return parse_message(data)