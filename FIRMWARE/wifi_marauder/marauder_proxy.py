import sys, threading, serial, time, re

PORT = "COM10"   # cambia si hace falta
BAUD = 115200

# Subcadenas "rápidas" a filtrar
SUBSTR_FILTERS = [
    "Failed to create settings file",
    "Could not parse json to load",
    "Settings SPIFFS Mount Failed",
    "SPIFFS: spiffs partition could not be found",
    "SD Card NOT Supported",
    "Failed to mount SD Card",
    "No core dump partition found",
]

# Patrones regex (más generales)
REGEX_FILTERS = [
    r"^Did not find setting named .+?\. Creating\.\.\.$",
    r"^Creating default settings file: settings\.json$",
    r"^E \(\d+\) psram: PSRAM ID read error: .*",
]

mute = True  # filtros activos por defecto

def should_suppress(line: str) -> bool:
    if not mute:
        return False
    for s in SUBSTR_FILTERS:
        if s in line:
            return True
    for pat in REGEX_FILTERS:
        if re.search(pat, line):
            return True
    return False

def reader(ser):
    buf = b""
    while True:
        try:
            chunk = ser.read(4096)
            if not chunk:
                time.sleep(0.01); continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                s = raw.decode(errors="ignore").rstrip("\r")
                if not should_suppress(s):
                    print(s, flush=True)
        except Exception as e:
            print(f"[reader error] {e}", file=sys.stderr)
            break

def show_help():
    print("Proxy cmds: /mute on|off   /filters   /raw <texto>   /help")

def main():
    global mute
    print(f"Conectando a {PORT} @ {BAUD}...")
    with serial.Serial(PORT, BAUD, timeout=0.05) as ser:
        t = threading.Thread(target=reader, args=(ser,), daemon=True)
        t.start()
        ser.write(b"\r\n")  # forzar prompt
        show_help()
        while True:
            try:
                cmd = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nSaliendo...")
                break

            if not cmd:
                ser.write(b"\r\n"); continue

            if cmd.startswith("/"):
                parts = cmd.split(" ", 1)
                c = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else ""

                if c == "/mute":
                    if arg.lower() in ("on", "1", "true"):
                        mute = True; print("[proxy] filtros ACTIVOS")
                    elif arg.lower() in ("off", "0", "false"):
                        mute = False; print("[proxy] filtros DESACTIVADOS")
                    else:
                        print("[proxy] uso: /mute on|off")
                    continue
                elif c == "/filters":
                    print("[proxy] Substr filters:")
                    for s in SUBSTR_FILTERS: print("  -", s)
                    print("[proxy] Regex filters:")
                    for rpat in REGEX_FILTERS: print("  -", rpat)
                    continue
                elif c == "/raw":
                    ser.write((arg + "\r\n").encode())
                    continue
                elif c == "/help":
                    show_help(); continue
                else:
                    print("[proxy] comando desconocido. /help"); continue

            # Comando normal hacia la CLI del ESP32
            ser.write((cmd + "\r\n").encode())

if __name__ == "__main__":
    main()
