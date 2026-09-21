import pytest
from voice_runtime.telephony.base import CallState
from voice_runtime.telephony.sim7600 import Sim7600Transport


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.commands: list[str] = []
        self.responses = {
            "ATD+15551234567;": [b"OK\r\n"],
            "ATH": [b"OK\r\n"],
            "AT+CLCC": [
                b'+CLCC: 1,0,0,0,0,"+15551234567",145\r\n',
                b"OK\r\n",
            ],
        }

    def write(self, data: bytes) -> None:
        command = data.decode().strip()
        self.commands.append(command)
        self.current = iter(self.responses[command])

    def readline(self) -> bytes:
        return next(self.current)

    def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_sim7600_dial_state_and_hangup() -> None:
    fake = FakeSerial()
    modem = Sim7600Transport("COM7", serial_factory=lambda *args, **kwargs: fake)

    await modem.dial("+15551234567")
    assert await modem.state() == CallState.ACTIVE
    await modem.hangup()

    assert fake.commands == ["ATD+15551234567;", "AT+CLCC", "ATH"]
