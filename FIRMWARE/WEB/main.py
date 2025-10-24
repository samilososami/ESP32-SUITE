# WEB/main.py — Backend API (FastAPI) para ESP32 Web Flasher
from typing import Dict, Any, List
import re
import os
import json
import asyncio
import sys
from io import StringIO
from contextlib import redirect_stdout
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from serial.tools import list_ports
import esptool
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(BASE_DIR, "BINARIES")

app = FastAPI(title="ESP Web Flasher Backend")

# Configuración CORS más permisiva
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir archivos estáticos
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

# ---------------- WebSocket para logs en tiempo real ----------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_log(self, message: str, flash_id: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps({
                    "type": "log",
                    "flash_id": flash_id,
                    "message": message
                }))
            except Exception as e:
                print(f"Error enviando log: {e}")
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)

    async def send_progress(self, progress: int, flash_id: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps({
                    "type": "progress",
                    "flash_id": flash_id,
                    "progress": progress
                }))
            except Exception as e:
                print(f"Error enviando progreso: {e}")
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Mantener la conexión activa
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ---------------- esptool helpers ----------------
def _run_esptool(args: List[str]) -> str:
    """Ejecuta esptool.main([...]) capturando stdout."""
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
    if m:
        chip = m.group(1).strip()

    features = []
    m = re.search(r"Features:\s+(.+)", chip_txt)
    if m:
        features = [s.strip() for s in m.group(1).split(",")]

    crystal_mhz = None
    m = re.search(r"Crystal is\s+(\d+(?:\.\d+)?)\s*MHz", chip_txt + mac_txt, re.I)
    if m:
        val = m.group(1)
        crystal_mhz = float(val) if "." in val else int(val)
    else:
        # Fallback: buscar en todo el texto
        m = re.search(r"(\d+)\s*MHz.*crystal", chip_txt + mac_txt + flash_txt, re.I)
        if m:
            crystal_mhz = int(m.group(1))

    mac = None
    m = re.search(r"MAC:\s*([0-9A-Fa-f:]{17})", mac_txt)
    if m:
        mac = m.group(1).lower()
    else:
        # Fallback alternativo para MAC
        m = re.search(r"([0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2}:[0-9A-Fa-f]{2})", mac_txt)
        if m:
            mac = m.group(1).lower()

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
    else:
        # Fallback para tamaño de flash
        m = re.search(r"Flash size:\s*([\d\.]+)\s*([MG]B)", chip_txt + flash_txt, re.I)
        if m:
            qty, unit = m.group(1), m.group(2).upper()
            flash_size = f"{qty} {unit}"

    return {
        "chip": chip or "ESP32 (no detectado)",
        "features": features or ["No detectadas"],
        "crystal_mhz": crystal_mhz or 40,  # Valor por defecto para ESP32
        "mac": mac or "No detectada",
        "flash_id": flash_id or "No detectado",
        "flash_size": flash_size or "No detectado",
    }

def _chip_info_via_cli(port: str, baud: int = 115200) -> Dict[str, Any]:
    base = ["--chip", "auto", "--port", port, "--baud", str(baud)]
    chip_txt  = _run_esptool(base + ["chip_id"])
    mac_txt   = _run_esptool(base + ["read_mac"])
    flash_txt = _run_esptool(base + ["flash_id"])
    return _parse_chip_info(chip_txt, mac_txt, flash_txt)

# ---------------- Flash helpers ----------------
def _get_flash_offset(firmware_name: str) -> str:
    """Determina el offset de flasheo basado en el nombre del firmware."""
    firmware_lower = firmware_name.lower()

    if "micropython" in firmware_lower:
        return "0x1000"
    elif "wifi-marauder" in firmware_lower:
        return "0x10000"
    elif "wled_bootloader" in firmware_lower or "bootloader" in firmware_lower:
        return "0x0"
    elif "wled" in firmware_lower:
        return "0x10000"
    else:
        # Por defecto para firmware desconocido
        return "0x10000"

async def _flash_esp32_real(port: str, firmware: str, erase: bool, flash_id: str):
    """Ejecuta el proceso de flasheo REAL con esptool y captura de progreso."""
    firmware_path = os.path.join(BIN_DIR, firmware)

    if not os.path.exists(firmware_path):
        await manager.send_log(f"❌ ERROR: Firmware {firmware} no encontrado", flash_id)
        return False

    # Calcular tamaño del firmware
    firmware_size = os.path.getsize(firmware_path)
    await manager.send_log(f"📁 Firmware: {firmware} ({firmware_size / 1024 / 1024:.2f} MB)", flash_id)

    # Determinar offset basado en el nombre del firmware
    flash_offset = _get_flash_offset(firmware)
    await manager.send_log(f"🎯 Offset de flasheo: {flash_offset}", flash_id)

    # Construir comando esptool usando el módulo Python directamente
    cmd = [
        sys.executable, "-m", "esptool",
        "--port", port,
        "--baud", "460800",
        "write_flash",
        "--flash-size", "detect",
    ]

    if erase:
        cmd.append("--erase-all")
        await manager.send_log("🧹 Borrando flash antes de flashear...", flash_id)

    # Añadir offset y ruta del firmware
    cmd.extend([flash_offset, firmware_path])

    try:
        await manager.send_log(f"⚙️ Ejecutando: {' '.join(cmd)}", flash_id)
        await manager.send_log("🚀 Iniciando proceso de flasheo REAL...", flash_id)

        # Ejecutar esptool usando el módulo Python directamente
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )

        # Leer salida en tiempo real y capturar progreso
        buffer = ""
        last_progress = 0

        while True:
            chunk = await process.stdout.read(512)
            if not chunk:
                break

            output = chunk.decode('utf-8', errors='ignore')
            buffer += output

            # Procesar líneas completas
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()

                if line:
                    # Enviar línea como log
                    await manager.send_log(line, flash_id)

                    # Intentar extraer progreso de la línea
                    progress = _extract_progress_from_line_improved(line)
                    if progress is not None and progress > last_progress:
                        last_progress = progress
                        await manager.send_progress(progress, flash_id)

        # Esperar a que termine el proceso
        return_code = await process.wait()

        if return_code == 0:
            # Asegurar que llegue al 100%
            if last_progress < 100:
                await manager.send_progress(100, flash_id)
            
            # Enviar mensaje de éxito específico
            await manager.send_log("¡Flasheo completado exitosamente!", flash_id)
            
            return True
        else:
            await manager.send_log(f"❌ Error en el flasheo (código: {return_code})", flash_id)
            return False

    except Exception as e:
        await manager.send_log(f"❌ Excepción durante el flasheo: {str(e)}", flash_id)
        return False

def _extract_progress_from_line_improved(line: str) -> int:
    """Extrae el porcentaje de progreso de una línea de salida de esptool - MEJORADO."""
    # Patrones mejorados para detectar progreso en esptool
    patterns = [
        r'(\d+(?:\.\d+)?)\s*%',                          # 50.0 % o 50 %
        r'\[.*\]\s*(\d+(?:\.\d+)?)\s*%',                 # [ ] 50.0 %
        r'Writing at 0x[0-9a-f]+.*?\((\d+(?:\.\d+)?)\s*%\)',  # Writing at 0x10000... (50 %)
        r'Progress:\s*(\d+(?:\.\d+)?)\s*%',              # Progress: 50%
        r'\]\s*(\d+(?:\.\d+)?)\s*%',                     # ] 50.0 %
    ]

    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            progress_float = float(match.group(1))
            progress = int(round(progress_float))  # Redondear al entero más cercano
            return min(100, max(0, progress))  # Asegurar que esté entre 0-100

    return None

# ---------------- endpoints ----------------
@app.get("/")
async def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/ports")
async def get_ports():
    """Lista COMs con metadatos."""
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
async def chip_info_get(
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
async def list_binaries():
    """Devuelve la lista de .bin disponibles en WEB/BINARIES."""
    try:
        if not os.path.isdir(BIN_DIR):
            return {"items": []}
        files = []
        for name in os.listdir(BIN_DIR):
            if name.lower().endswith(".bin"):
                file_path = os.path.join(BIN_DIR, name)
                file_size = os.path.getsize(file_path)

                # Parsear nombre para extraer información
                name_without_ext = os.path.splitext(name)[0]
                flash_offset = _get_flash_offset(name)

                files.append({
                    "name": name,
                    "size": file_size,
                    "size_formatted": f"{file_size / 1024 / 1024:.2f} MB",
                    "flash_offset": flash_offset
                })
        # orden alfabético
        files.sort(key=lambda x: x["name"].lower())
        return {"items": files}
    except Exception as e:
        raise HTTPException(500, detail=f"No se pudo listar BINARIES: {e}")

@app.post("/flash")
async def flash_firmware(flash_data: dict):
    """Inicia el proceso de flasheo REAL."""
    try:
        port = flash_data.get("port")
        firmware = flash_data.get("firmware")
        erase = flash_data.get("erase", False)
        flash_id = flash_data.get("flash_id", "default")

        if not port or not firmware:
            raise HTTPException(400, detail="Puerto y firmware son requeridos")

        # Ejecutar flasheo REAL en segundo plano
        asyncio.create_task(_flash_esp32_real(port, firmware, erase, flash_id))

        return {"status": "started", "message": "Flasheo REAL iniciado"}

    except Exception as e:
        raise HTTPException(500, detail=f"Error iniciando flasheo: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5050, log_level="info")
