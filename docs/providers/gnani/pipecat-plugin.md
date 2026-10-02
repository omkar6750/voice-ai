> ## Documentation Index
> Fetch the complete documentation index at: https://docs.gnani.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Pipecat Plugin

> Use Gnani STT and TTS inside Pipecat voice agent pipelines for Indian languages.

## Overview

`pipecat-gnani` is a Pipecat service integration that wraps the Gnani STT and TTS APIs into Pipecat's standard `SegmentedSTTService`, `STTService`, `TTSService`, and `InterruptibleTTSService` base classes. Drop the services into any Pipecat pipeline and get high-accuracy Indian-language transcription and low-latency synthesis without managing WebSocket connections yourself.

```text theme={null}
gnani-vachana (>=0.7.3)  ← Core SDK on PyPI (import as `gnani`)
        ↑
pipecat-gnani            ← This package (Pipecat service adapters)
  ├── STT: REST + WebSocket
  └── TTS: REST + SSE + WebSocket
        ↑
Your Pipecat voice agent
```

All connection logic, authentication, and audio format handling live in the core SDK. The plugin is purely an adapter layer. This integration is maintained by [Gnani.ai](https://gnani.ai/).

Tested with **Pipecat v1.5.0**.

***

## Installation

```bash theme={null}
pip install pipecat-gnani
```

Or with [uv](https://docs.astral.sh/uv/):

```bash theme={null}
uv add pipecat-gnani
```

This also installs [`gnani-vachana`](https://pypi.org/project/gnani-vachana/) (>= 0.7.3) as a dependency. The Python import package name remains `gnani`.

**Requirements:** Python 3.10+

***

## Prerequisites

You need a Gnani API key. [Gnani APIs](https://app.gnani.ai/voice)

```bash theme={null}
export GNANI_API_KEY="your-api-key"
```

| Variable | Purpose |
| - | - |
| `GNANI_API_KEY` | API key for Gnani STT and TTS |
| `GROQ_API_KEY` | API key for the Groq LLM in the foundational example |

***

## Services

This plugin provides five service classes. Choose based on your use case:

| Service | Type | Transport | Base Class | Best for |
| - | - | - | - | - |
| `GnaniHttpSTTService` | STT | REST POST | `SegmentedSTTService` | File-based transcription via `POST /stt/v3`. Requires VAD in pipeline. |
| `GnaniSTTService` | STT | WebSocket | `STTService` | Live conversations, real-time agents |
| `GnaniHttpTTSService` | TTS | REST POST | `TTSService` | Batch synthesis, non-streaming pipelines |
| `GnaniSSETTSService` | TTS | SSE | `TTSService` | Streaming synthesis with lower latency than REST |
| `GnaniTTSService` | TTS | WebSocket | `InterruptibleTTSService` | Conversational agents with interruption support |

***

## Quick Start

### Pipeline snippet

The snippet below shows the core `Pipeline([...])` wiring used in the foundational example. See [`examples/foundational/agent.py`](https://github.com/Gnani-AI-Mintlify/pipecat-gnani/blob/main/examples/foundational/agent.py) for the full runnable version.

```python theme={null}
import os

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.groq.llm import GroqLLMService
from pipecat.transcriptions.language import Language
from pipecat_gnani import GnaniSTTService, GnaniTTSService

# transport = ...  #  see examples/foundational/agent.py

stt = GnaniSTTService(
    api_key=os.environ["GNANI_API_KEY"],
    settings=GnaniSTTService.Settings(language=Language.HI_IN),
)

tts = GnaniTTSService(
    api_key=os.environ["GNANI_API_KEY"],
    settings=GnaniTTSService.Settings(voice="Pranav"),
)

llm = GroqLLMService(
    api_key=os.environ["GROQ_API_KEY"],
    settings=GroqLLMService.Settings(
        model="llama-3.1-8b-instant",
    ),
)

context = LLMContext()
aggregators = LLMContextAggregatorPair(
    context,
    user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
)

pipeline = Pipeline(
    [
        transport.input(),
        stt,
        aggregators.user(),
        llm,
        tts,
        transport.output(),
        aggregators.assistant(),
    ]
)

task = PipelineTask(
    pipeline,
    params=PipelineParams(enable_metrics=True),
)
```

Swap service classes in `agent.py` for REST or SSE variants — WebSocket STT + TTS is the default for lowest latency and interruption support.

### Speech-to-Text (REST)

```python theme={null}
from pipecat_gnani import GnaniHttpSTTService
from pipecat.transcriptions.language import Language

stt = GnaniHttpSTTService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniHttpSTTService.Settings(
        language=Language.HI_IN,
    ),
)
```

### Speech-to-Text (Streaming WebSocket)

```python theme={null}
from pipecat_gnani import GnaniSTTService
from pipecat.transcriptions.language import Language

stt = GnaniSTTService(
    api_key="your-api-key",
    settings=GnaniSTTService.Settings(
        language=Language.HI_IN,
    ),
)
```

### Text-to-Speech (REST)

```python theme={null}
from pipecat_gnani import GnaniHttpTTSService

tts = GnaniHttpTTSService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniHttpTTSService.Settings(
        voice="Pranav",
    ),
)
```

### Text-to-Speech (SSE Streaming)

```python theme={null}
from pipecat_gnani import GnaniSSETTSService

tts = GnaniSSETTSService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniSSETTSService.Settings(
        voice="Pranav",
    ),
)
```

### Text-to-Speech (WebSocket Streaming)

```python theme={null}
from pipecat_gnani import GnaniTTSService

tts = GnaniTTSService(
    api_key="your-api-key",
    settings=GnaniTTSService.Settings(
        voice="Pranav",
    ),
)
```

***

## STT — `GnaniHttpSTTService` (REST)

File-based transcription via REST. Extends Pipecat's `SegmentedSTTService`.

* Calls `POST /stt/v3`
* Requires VAD in the pipeline to segment audio
* Requires an active `aiohttp.ClientSession` passed at construction time

```python theme={null}
from pipecat_gnani import GnaniHttpSTTService
from pipecat.transcriptions.language import Language

stt = GnaniHttpSTTService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniHttpSTTService.Settings(
        language=Language.HI_IN,
    ),
)
```

### Settings

| Parameter | Type | Default | Description |
| - | - | - | - |
| `language` | `Language` | `Language.EN_IN` | Language enum for transcription. See [Supported Languages](#supported-languages). |

***

## STT — `GnaniSTTService` (WebSocket)

Real-time streaming speech-to-text via WebSocket with VAD events. Extends Pipecat's `STTService`.

* Connects to `wss://api.vachana.ai/stt/v3/stream`
* Sends raw PCM audio in 1,024-byte frames
* Emits `TranscriptionFrame` (final) and `InterimTranscriptionFrame` when the API sets `is_final: false` (today Gnani sends final transcripts only)
* Supports 8 kHz and 16 kHz sample rates

```python theme={null}
from pipecat_gnani import GnaniSTTService
from pipecat.transcriptions.language import Language

stt = GnaniSTTService(
    api_key="your-api-key",
    settings=GnaniSTTService.Settings(
        language=Language.HI_IN,
        sample_rate=16000,            # 8000 or 16000
    ),
)
```

### Streaming PCM Specification

All streaming audio must be sent as **raw PCM binary frames** — no container format (WAV, MP3) mid-stream.

| Property | 16 kHz | 8 kHz |
| - | - | - |
| Encoding | PCM signed 16-bit little-endian | PCM signed 16-bit little-endian |
| Sample Rate | 16,000 Hz | 8,000 Hz |
| Channels | 1 (mono) | 1 (mono) |
| Samples per chunk | 512 | 512 |
| **Bytes per frame** | **1,024 bytes** (512 samples × 2 bytes) | **1,024 bytes** (512 samples × 2 bytes) |
| Frame duration | 32 ms | 64 ms |

Frames must be sent at **real-time cadence**. See [STT Realtime — PCM Specification](/api/STT/stt-websocket#pcm-specification) for full details.

### Settings

| Parameter | Type | Default | Description |
| - | - | - | - |
| `language` | `Language` | `Language.EN_IN` | Language enum for transcription. See [Supported Languages](#supported-languages). |
| `sample_rate` | `int` | `16000` | Audio sample rate in Hz. Accepted values: `8000`, `16000`. |

***

## TTS — `GnaniHttpTTSService` (REST)

REST-based text-to-speech for non-streaming use cases. Returns the complete audio in a single response.

* Calls `POST /api/v1/tts/inference`
* Requires an active `aiohttp.ClientSession` passed at construction time
* Suitable for batch synthesis or pipelines where streaming is not needed

```python theme={null}
import aiohttp
from pipecat_gnani import GnaniHttpTTSService

async def build_pipeline():
    async with aiohttp.ClientSession() as session:
        tts = GnaniHttpTTSService(
            api_key="your-api-key",
            aiohttp_session=session,
            settings=GnaniHttpTTSService.Settings(
                voice="Pranav",
            ),
        )
```

### Settings

| Parameter | Type | Default | Description |
| - | - | - | - |
| `voice` | `string` | `"Pranav"` | Voice ID. See [Available Voices](/api/TTS/available-voices). |
| `sample_rate` | `int` | `16000` | Output sample rate in Hz. |

***

## TTS — `GnaniSSETTSService` (SSE)

Streaming text-to-speech via Server-Sent Events. Lower latency than REST.

* Calls `POST /api/v1/tts/sse`
* Requires an active `aiohttp.ClientSession` passed at construction time
* Streams audio chunks as synthesis progresses

```python theme={null}
from pipecat_gnani import GnaniSSETTSService

tts = GnaniSSETTSService(
    api_key="your-api-key",
    aiohttp_session=session,
    settings=GnaniSSETTSService.Settings(
        voice="Pranav",
    ),
)
```

### Settings

| Parameter | Type | Default | Description |
| - | - | - | - |
| `voice` | `string` | `"Pranav"` | Voice ID. See [Available Voices](/api/TTS/available-voices). |
| `sample_rate` | `int` | `16000` | Output sample rate in Hz. |

***

## TTS — `GnaniTTSService` (WebSocket, recommended)

Streaming text-to-speech via WebSocket. Extends Pipecat's `InterruptibleTTSService`, giving your agent built-in interruption (barge-in) support — when the user speaks over the agent, synthesis stops cleanly.

* Connects to `wss://api.vachana.ai/api/v1/tts`
* Streams audio chunks in real-time as synthesis progresses
* Ideal for live conversational agents where latency and barge-in handling matter
* `TTSTextFrame`s are emitted by the Pipecat base class after each synthesis request

```python theme={null}
from pipecat_gnani import GnaniTTSService

tts = GnaniTTSService(
    api_key="your-api-key",
    settings=GnaniTTSService.Settings(
        voice="Pranav",
    ),
)
```

### Settings

| Parameter | Type | Default | Description |
| - | - | - | - |
| `voice` | `string` | `"Pranav"` | Voice ID. See [Available Voices](/api/TTS/available-voices). |
| `sample_rate` | `int` | `16000` | Output sample rate in Hz. |

***

## Available Voices

To see the available voices, [click here](/api/TTS/available-voices).

***

## Supported Languages

### STT Languages (Speech-to-Text)

STT uses BCP-47 locale codes (e.g. `hi-IN`, `bn-IN`). For the full list, see [STT — Supported Languages](/api/STT/speech-to-text#supported-languages).

### TTS Languages (Text-to-Speech)

TTS uses the same BCP-47 `-IN` suffixed codes as STT (e.g. `hi-IN`, `en-IN`, `ta-IN`). See [TTS REST — Request Parameters](/api/TTS/tts-inference#request-parameters) and the [Voice Catalog](/api/TTS/available-voices).

<Note>
  Use the `Language` enum from `pipecat.transcriptions.language` for STT services (`GnaniSTTService`, `GnaniHttpSTTService`). TTS voice selection primarily drives language for synthesis.
</Note>

***

## Further Reading

* [STT REST API](/api/STT/speech-to-text) — file-based transcription reference
* [STT Realtime API](/api/STT/stt-websocket) — WebSocket protocol reference
* [TTS REST API](/api/TTS/tts-inference) — synchronous synthesis reference
* [TTS Streaming (SSE)](/api/TTS/tts-sse) — SSE synthesis reference
* [TTS Realtime API](/api/TTS/tts-websocket) — WebSocket TTS reference
* [`gnani-vachana` on PyPI](https://pypi.org/project/gnani-vachana/) — core SDK
* [`pipecat-gnani` on PyPI](https://pypi.org/project/pipecat-gnani/) — this plugin
* [Pipecat Docs](https://docs.pipecat.ai/) — Pipecat framework reference


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.