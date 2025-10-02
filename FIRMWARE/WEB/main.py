# WEB/main.py — Backend API (FastAPI) para info de chip y listado de binarios
# Endpoints: /ports, /chip-info (GET), /binaries (GET)
from typing import Dict, Any, List
import re
import os
from io import StringIO
from contextlib import redirect_stdout

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from serial.tools import list_ports
import esptool

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "BINARIES")

app = FastAPI(title="ESP Web Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringe si lo deseas
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- esptool helpers ----------------
def _run_esptool(args: List[str]) -> str:
    """Ejecuta esptool.main([...]) capturando stdout (esptool imprime en stdout)."""
    buf = StringIO()
    try:
        with redirect_stdout(buf):
            esptool.main(args)
    except SystemExit as e:
        code = int(getattr(e, "code", 0) or 0)
        if code != 0:
            text = buf.getvalue()
            raise HTTPException(500, detail=f"esptool error (args={args}):\n{text}")
    except Exception as e:
        text = buf.getvalue()
        raise HTTPException(500, detail=f"esptool exception (args={args}): {e}\n{text}")
    return buf.getvalue()

def _parse_chip_info(chip_txt: str, mac_txt: str, flash_txt: str) -> Dict[str, Any]:
    chip = None
    m = re.search(r"Chip is\s+(.+)", chip_txt)
    if m: chip = m.group(1).strip()

    features = None
    m = re.search(r"Features:\s+(.+)", chip_txt)
    if m: features = [s.strip() for s in m.group(1).split(",")]

    crystal_mhz = None
    m = re.search(r"Crystal is\s+(\d+(?:\.\d+)?)\s*MHz", chip_txt + mac_txt, re.I)
    if m:
        val = m.group(1)
        crystal_mhz = float(val) if "." in val else int(val)

    mac = None
    m = re.search(r"MAC:\s*([0-9A-Fa-f:]{17})", mac_txt)
    if m: mac = m.group(1).lower()

    flash_id = None
    m = re.search(r"(Flash ID|0x)[^\n]*0x([0-9A-Fa-f]+)", flash_txt)
    if m:
        flash_id = "0x" + m.group(2).lower()
    else:
        man = re.search(r"Manufacturer:\s*([0-9A-Fa-f]+)", flash_txt)
        dev = re.search(r"Device:\s*([0-9A-Fa-f]+)", flash_txt)
        if man and dev:
            flash_id = "0x" + (man.group(1) + dev.group(1)).lower()

    flash_size = None
    m = re.search(r"Detected flash size:\s*([\d\.]+)\s*([MG]B)", chip_txt + flash_txt, re.I)
    if m:
        qty, unit = m.group(1), m.group(2).upper()
        flash_size = f"{qty} {unit}"

    return {
        "chip": chip,
        "features": features,
        "crystal_mhz": crystal_mhz,
        "mac": mac,
        "flash_id": flash_id,
        "flash_size": flash_size,
    }

def _chip_info_via_cli(port: str, baud: int = 115200) -> Dict[str, Any]:
    base = ["--chip", "auto", "--port", port, "--baud", str(baud)]
    chip_txt  = _run_esptool(base + ["chip_id"])
    mac_txt   = _run_esptool(base + ["read_mac"])
    flash_txt = _run_esptool(base + ["flash_id"])
    return _parse_chip_info(chip_txt, mac_txt, flash_txt)

# ---------------- endpoints ----------------
@app.get("/")
def root():
    return {
        "ok": True,
        "endpoints": [
            "/ports",
            "GET /chip-info?port=COM6&baud=115200",
            "GET /binaries",
        ],
    }

@app.get("/ports")
def get_ports():
    """Lista COMs con metadatos (vid/pid) — se usa para mapear el puerto elegido en Web Serial."""
    out = []
    for p in list_ports.comports():
        out.append({
            "device": p.device,
            "name": p.name,
            "description": p.description,
            "hwid": p.hwid,
            "vid": p.vid,
            "pid": p.pid,
            "manufacturer": getattr(p, "manufacturer", None),
            "serial_number": getattr(p, "serial_number", None),
            "location": getattr(p, "location", None),
        })
    return {"ports": out}

@app.get("/chip-info")
def chip_info_get(
    port: str = Query(..., description="Ej. COM6"),
    baud: int = Query(115200, description="115200 recomendado para ROM")
):
    try:
        return _chip_info_via_cli(port, baud)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail=f"Error leyendo chip en {port}: {e}")

@app.get("/binaries")
def list_binaries():
    """Devuelve la lista de .bin disponibles en WEB/BINARIES, sin extensión (para el combo)."""
    try:
        if not os.path.isdir(BIN_DIR):
            return {"items": []}
        files = []
        for name in os.listdir(BIN_DIR):
            if name.lower().endswith(".bin"):
                base = os.path.splitext(name)[0]
                files.append({"name": base, "file": name})
        # orden alfabético
        files.sort(key=lambda x: x["name"].lower())
        return {"items": files}
    except Exception as e:
        raise HTTPException(500, detail=f"No se pudo listar BINARIES: {e}")

