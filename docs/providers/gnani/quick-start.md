> ## Documentation Index
> Fetch the complete documentation index at: https://docs.gnani.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Quick Start

> Make your first speech-to-text, text-to-speech or voice-cloned TTS API request in minutes.

## Prerequisites

Before you begin, ensure you have:

* A valid API key (sign up on the [Gnani API platform](https://app.gnani.ai/voice/) to generate API keys)
* cURL installed, or an API client such as Postman

<Tabs>
  <Tab title="Speech-to-Text (STT)">
    <Tabs>
      <Tab title="REST">
        Use a test audio file that meets these requirements:

        * Format: WAV, MP3, OGG, FLAC, AAC, or M4A
        * Sample rate: 8 kHz to 44.1 kHz
        * Maximum duration: 60 seconds

        ### Your First Speech-to-Text Request

        Minimal example to transcribe a Hindi audio file:

        ```bash theme={null}
        curl -X POST https://api.vachana.ai/stt/v3 \
          -H 'Content-Type: multipart/form-data' \
          -H 'X-API-Key-ID: <API_KEY>' \
          -F audio_file='@/path/to/your/audio.wav' \
          -F language_code=hi-IN
        ```

        **Replace these values:**

        * `<API_KEY>`: Your Gnani Prisma v2.5 API key
        * `/path/to/your/audio.wav`: Path to your audio file
        * `hi-IN`: Language code (see [Language Codes](/api/STT/speech-to-text#language-codes))

        ### Expected STT Response

        On success, you'll receive a JSON response like:

        ```json theme={null}
        {
          "success": true,
          "request_id": "019fd17d-1106-7265-88ab-3ed12d029292",
          "transcript": "नमस्ते, आप कैसे हैं?",
          "model": "gnani-prisma-v2.5"
        }
        ```
      </Tab>

      <Tab title="Realtime">
        Stream live audio over WebSocket. See [STT Realtime](/api/STT/stt-websocket) for the full protocol, headers, and PCM requirements.

        **Endpoint**

        ```text theme={null}
        wss://api.vachana.ai/stt/v3/stream
        ```

        **Required headers**

        | Header | Value |
        | - | - |
        | `x-api-key-id` | Your API key |
        | `lang_code` | BCP-47 code (e.g. `hi-IN`) |

        Send **binary PCM frames** only (16-bit mono, 8 or 16 kHz, 1024 bytes per frame). The server returns JSON transcript events:

        ```json theme={null}
        {
          "type": "transcript",
          "text": "Hello, how are you today?",
          "segment_id": "seg_abc123",
          "latency": 320
        }
        ```
      </Tab>
    </Tabs>
  </Tab>

  <Tab title="Text-to-Speech (TTS)">
    <Tip>
      Timbre v2.5 is now the recommended TTS model. Migrate from Timbre v2.0 to continue receiving the latest improvements. Timbre v2.0 will be deprecated soon.
    </Tip>

    <Tabs>
      <Tab title="REST">
        Have your input text ready. Choose a voice from the [Voice Catalog](/api/TTS/available-voices).

        ### Your First Text-to-Speech Call

        Minimal example for REST TTS (synchronous audio). This endpoint returns the full synthesized audio as a binary response.

        ```bash theme={null}
        curl -X POST https://api.vachana.ai/api/v1/tts/inference \
          -H 'Content-Type: application/json' \
          -H 'X-API-Key-ID: <API_KEY>' \
          -d '{
                "text": "नमस्ते, आप कैसे हैं?",
                "voice": "Nalini",
                "model": "timbre-v2.5",
                "language": "hi-IN",
                "speed": 1.0,
                "audio_config": {
                  "sample_rate": 48000,
                  "num_channels": 1,
                  "sample_width": 2,
                  "encoding": "linear_pcm",
                  "container": "wav"
                }
              }' \
          --output response.wav
        ```

        ### Expected TTS Response

        A successful request will return a `200 OK` HTTP status. The response body will contain raw binary audio data representing the synthesized text, adhering to the format specified in your `audio_config`.

        ```http theme={null}
        HTTP/1.1 200 OK
        Content-Type: audio/wav

        <binary audio data>
        ```
      </Tab>

      <Tab title="Streaming">
        This endpoint streams synthesized audio using Server-Sent Events (SSE). Audio is generated and delivered incrementally as it becomes available.

        ### Your First Streaming Call

        ```bash theme={null}
        curl -X POST https://api.vachana.ai/api/v1/tts/sse \
          -H 'Content-Type: application/json' \
          -H 'X-API-Key-ID: <API_KEY>' \
          -d '{
                "text": "नमस्ते, आप कैसे हैं?",
                "voice": "Nalini",
                "model": "timbre-v2.5",
                "language": "hi-IN",
                "speed": 1.0,
                "audio_config": {
                  "sample_rate": 48000,
                  "encoding": "linear_pcm",
                  "container": "wav"
                }
              }'
        ```

        ### Expected SSE Response

        A successful request will return a `200 OK` HTTP status. The response body will contain a stream of server-sent events. Each chunk contains base64 encoded audio fragments.

        ```http theme={null}
        HTTP/1.1 200 OK
        Content-Type: text/event-stream

        event: start
        data: {"status": "streaming_started", "text": "नमस्ते, आप कैसे हैं?"}

        event: chunk
        data: {"chunk_index": 1, "audio": "<base64-encoded audio>", "is_final": false}

        event: complete
        data: {"chunk_index": 2, "audio": "", "is_final": true}
        ```
      </Tab>

      <Tab title="Realtime">
        Connect over WebSocket for lowest latency. See [TTS Realtime](/api/TTS/tts-websocket) for message types and `audio_config` options.

        **Endpoint**

        ```text theme={null}
        wss://api.vachana.ai/api/v1/tts
        ```

        Send a JSON payload after connecting (include `X-API-Key-ID` in the upgrade headers):

        ```json theme={null}
        {
          "text": "नमस्ते, आप कैसे हैं?",
          "voice": "Nalini",
          "model": "timbre-v2.5",
          "language": "hi-IN",
          "audio_config": {
            "sample_rate": 48000,
            "encoding": "linear_pcm",
            "container": "wav"
          }
        }
        ```

        The server streams JSON messages with base64 audio chunks (`start`, then `audio`, then `complete`).
      </Tab>
    </Tabs>
  </Tab>

  <Tab title="Voice Cloning (VC)">
    Voice cloning works in two steps:

    1. **Generate embeddings** — upload a reference audio file to get a `speaker_embedding`
    2. **Synthesize** — pass the embedding with your text to any VC TTS endpoint

    ### Step 1: Generate Voice Embeddings

    Upload a reference audio file (WAV/MP3, ideally 5–30 seconds of clear speech):

    ```bash theme={null}
    curl -X POST https://api.vachana.ai/api/v1/tts/voice-clone/embeddings \
      -H 'X-API-Key-ID: <API_KEY>' \
      -F audio_file='@/path/to/reference.wav'
    ```

    **Replace these values:**

    * `<API_KEY>`: Your Gnani API key
    * `/path/to/reference.wav`: Path to your reference audio file

    ### Expected Embeddings Response

    ```json theme={null}
    {
      "embedding": "<embedding-string>",
      "shape": [1, 768],
      "dtype": "torch.bfloat16"
    }
    ```

    ### Step 2: Synthesize with Your Cloned Voice

    <Tabs>
      <Tab title="REST">
        Pass the `speaker_embedding` from Step 1 to synthesize audio in your cloned voice:

        ```bash theme={null}
        curl -X POST https://api.vachana.ai/api/v1/tts/inference \
          -H 'Content-Type: application/json' \
          -H 'X-API-Key-ID: <API_KEY>' \
          -d '{
                "text": "नमस्ते, आप कैसे हैं?",
                "model": "vachana-vc-v1",
                "audio_config": {
                  "sample_rate": 44100,
                  "num_channels": 1,
                  "sample_width": 2,
                  "encoding": "linear_pcm",
                  "container": "wav"
                },
                "speaker_embedding": {
                  "embedding": "<your-embedding-string>",
                  "shape": [1, 768],
                  "dtype": "torch.bfloat16"
                }
              }' \
          --output cloned_voice.wav
        ```

        A successful request returns a `200 OK` with raw binary audio data in the specified format.
      </Tab>

      <Tab title="Streaming">
        Stream cloned voice audio progressively via Server-Sent Events:

        ```bash theme={null}
        curl -X POST https://api.vachana.ai/api/v1/tts/sse \
          -H 'Content-Type: application/json' \
          -H 'X-API-Key-ID: <API_KEY>' \
          -d '{
                "text": "नमस्ते, आप कैसे हैं?",
                "model": "vachana-vc-v1",
                "speaker_embedding": {
                  "embedding": "<your-embedding-string>",
                  "shape": [1, 768],
                  "dtype": "torch.bfloat16"
                }
              }'
        ```

        The response streams base64-encoded audio chunks as server-sent events, identical in format to the TTS SSE response.
      </Tab>

      <Tab title="Realtime">
        For the lowest latency, stream text and receive cloned voice audio over a WebSocket:

        ```javascript theme={null}
        const ws = new WebSocket("wss://api.vachana.ai/api/v1/tts", {
          headers: {
            "Content-Type": "application/json",
            "X-API-Key-ID": "<API_KEY>",
          },
        });

        ws.on("open", () => {
          ws.send(JSON.stringify({
            text: "नमस्ते, आप कैसे हैं?",
            model: "vachana-vc-v1",
            audio_config: { sample_rate: 44100, encoding: "linear_pcm" },
            speaker_embedding: {
              embedding: "<your-embedding-string>",
              shape: [1, 768],
              dtype: "torch.bfloat16",
            },
          }));
        });

        ws.on("message", (data) => {
          // Handle binary PCM audio chunks
        });
        ```

        The server streams binary PCM audio chunks over the WebSocket connection.
      </Tab>
    </Tabs>
  </Tab>
</Tabs>

***

## Next Steps

* **Speech-to-Text**: [STT REST](/api/STT/speech-to-text) and [STT Realtime](/api/STT/stt-websocket)
* **Text-to-Speech**: [REST](/api/TTS/tts-inference), [Streaming (SSE)](/api/TTS/tts-sse), and [Realtime](/api/TTS/tts-websocket)
* **Voice Cloning**: [VC Embeddings](/api/VC/voice-clone-embeddings), [REST](/api/VC/vc-inference), [Streaming](/api/VC/vc-sse), and [Realtime](/api/VC/vc-websocket)
* **Batch transcription**: [Batch STT Introduction](/api/STTBatch/Introduction)


This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.