import argparse
import asyncio
import json

from serial.tools import list_ports

from voice_runtime.telephony.sim7600 import Sim7600Modem


def list_serial_ports() -> list[dict[str, str | None]]:
    return [
        {"device": port.device, "description": port.description, "hwid": port.hwid}
        for port in list_ports.comports()
    ]


async def read_status(port: str, baudrate: int) -> dict[str, object]:
    modem = Sim7600Modem(port, baudrate)
    try:
        return {
            "modem": (await modem.status()).__dict__,
            "serial_ports": list_serial_ports(),
        }
    finally:
        await modem.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect SIM7600 modem and serial status")
    parser.add_argument("--modem-port", default="COM16")
    parser.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()
    print(
        json.dumps(asyncio.run(read_status(args.modem_port, args.baudrate)), default=str, indent=2)
    )
