> ## Documentation Index
> Fetch the complete documentation index at: https://docs.together.ai/llms.txt
> Use this file to discover all available pages before exploring further.

> Learn how to use the text-to-speech functionality supported by Together AI.

# Text-to-Speech

Together AI provides comprehensive text-to-speech capabilities with multiple models and delivery methods. This guide covers everything from basic audio generation to real-time streaming via WebSockets.

## Quick Start

Here's how to get started with basic text-to-speech:

<CodeGroup>
  ```python Python theme={null}
  from together import Together

  client = Together()

  speech_file_path = "speech.mp3"

  response = client.audio.speech.create(
      model="canopylabs/orpheus-3b-0.1-ft",
      input="Today is a wonderful day to build something people love!",
      voice="tara",
      response_format="mp3",
  )

  response.stream_to_file(speech_file_path)
  ```

  ```python Python(v2) theme={null}
  from together import Together

  client = Together()

  speech_file_path = "speech.mp3"

  response = client.audio.speech.with_streaming_response.create(
      model="canopylabs/orpheus-3b-0.1-ft",
      input="Today is a wonderful day to build something people love!",
      voice="tara",
      response_format="mp3",
  )

  with response as stream:
      stream.stream_to_file(speech_file_path)
  ```

  ```typescript TypeScript theme={null}
  import Together from 'together-ai';

  const together = new Together();

  async function generateAudio() {
    const res = await together.audio.create({
      input: 'Hello, how are you today?',
      voice: 'tara',
      response_format: 'mp3',
      sample_rate: 44100,
      stream: false,
      model: 'canopylabs/orpheus-3b-0.1-ft',
    });

    if (res.body) {
      console.log(res.body);
      const nodeStream = Readable.from(res.body as ReadableStream);
      const fileStream = createWriteStream('./speech.mp3');

      nodeStream.pipe(fileStream);
    }
  }

  generateAudio();
  ```

  ```curl cURL theme={null}
  curl -X POST "https://api.together.xyz/v1/audio/speech" \
       -H "Authorization: Bearer $TOGETHER_API_KEY" \
       -H "Content-Type: application/json" \
       -d '{
         "model": "canopylabs/orpheus-3b-0.1-ft",
         "input": "The quick brown fox jumps over the lazy dog",
         "voice": "tara",
         "response_format": "mp3"
       }' \
       --output speech.mp3
  ```
</CodeGroup>

This will output a `speech.mp3` file.

## Available Models

Together AI supports multiple text-to-speech models:

| Organization | Model Name                                   | Model String for API         | API Endpoint Support       |
| :----------- | :------------------------------------------- | :--------------------------- | :------------------------- |
| Canopy Labs  | Orpheus 3B                                   | canopylabs/orpheus-3b-0.1-ft | Rest, Streaming, WebSocket |
| Kokoro       | Kokoro                                       | hexgrad/Kokoro-82M           | Rest, Streaming, WebSocket |
| Cartesia     | Cartesia Sonic 2                             | cartesia/sonic-2             | Rest                       |
| Cartesia     | Cartesia Sonic                               | cartesia/sonic               | Rest                       |
| Rime         | Arcana v2 *(Dedicated Endpoint only)*        | rime-labs/rime-arcana-v2     | Rest, Streaming, WebSocket |
| Minimax      | Speech 2.6 Turbo *(Dedicated Endpoint only)* | minimax/speech-2.6-turbo     | Rest, Streaming, WebSocket |
| Rime         | Mist v2 *(Dedicated Endpoint only)*          | rime-labs/rime-mist-v2       | Rest, Streaming, WebSocket |

<Note>
  * Orpheus and Kokoro models support real-time WebSocket streaming for lowest latency applications.
  * To use Cartesia models, you need to be at Build Tier 2 or higher.
</Note>

## Parameters

| Parameter        | Type   | Required | Description                                                                                                                      |
| :--------------- | :----- | :------- | :------------------------------------------------------------------------------------------------------------------------------- |
| model            | string | Yes      | The TTS model to use                                                                                                             |
| input            | string | Yes      | The text to generate audio for                                                                                                   |
| voice            | string | Yes      | The voice to use for generation. See [Voices](#voices) section                                                                   |
| response\_format | string | No       | Output format: `mp3`, `wav`, `raw` (PCM), `mulaw` (μ-law). Minimax model also supports `opus`, `aac`, and `flac`. Default: `wav` |

For the full set of parameters refer to the API reference for [/audio/speech](/reference/audio-speech).

## Streaming Audio

For real-time applications where Time-To-First-Byte (TTFB) is critical, use streaming mode:

<CodeGroup>
  ```python Python theme={null}
  from together import Together

  client = Together()

  response = client.audio.speech.create(
      model="canopylabs/orpheus-3b-0.1-ft",
      input="The quick brown fox jumps over the lazy dog",
      voice="tara",
      stream=True,
      response_format="raw",  # Required for streaming
      response_encoding="pcm_s16le",  # 16-bit PCM for clean audio
  )

  # Save the streamed audio to a file
  response.stream_to_file("speech_streaming.wav", response_format="wav")
  ```

  ```python Python(v2) theme={null}
  from together import Together

  client = Together()

  response = client.audio.speech.with_streaming_response.create(
      model="canopylabs/orpheus-3b-0.1-ft",
      input="The quick brown fox jumps over the lazy dog",
      voice="tara",
      stream=True,
      response_format="raw",  # Required for streaming
      response_encoding="pcm_s16le",  # 16-bit PCM for clean audio
  )

  # Save the streamed audio to a file
  with response as stream:
      stream.stream_to_file("speech_streaming.wav", response_format="wav")
  ```

  ```typescript TypeScript theme={null}
  import Together from 'together-ai';

  const together = new Together();

  async function streamAudio() {
    const response = await together.audio.speech.create({
      model: 'canopylabs/orpheus-3b-0.1-ft',
      input: 'The quick brown fox jumps over the lazy dog',
      voice: 'tara',
      stream: true,
      response_format: 'raw',  // Required for streaming
      response_encoding: 'pcm_s16le'  // 16-bit PCM for clean audio
    });

    // Process streaming chunks
    const chunks = [];
    for await (const chunk of response) {
      chunks.push(chunk);
    }

    console.log('Streaming complete!');
  }

  streamAudio();
  ```

  ```curl cURL theme={null}
  curl -X POST "https://api.together.xyz/v1/audio/speech" \
       -H "Authorization: Bearer $TOGETHER_API_KEY" \
       -H "Content-Type: application/json" \
       -d '{
         "model": "canopylabs/orpheus-3b-0.1-ft",
         "input": "The quick brown fox jumps over the lazy dog",
         "voice": "tara",
         "stream": true
       }'
  ```
</CodeGroup>

**Streaming Response Format:**

When `stream: true`, the API returns a stream of events:

**Delta Event:**

```json  theme={null}
{
  "type": "delta",
  "audio": "base64-encoded-audio-data"
}
```

**Completion Event:**

```json  theme={null}
{
  "type": "done"
}
```

**Note:** When streaming is enabled, only `raw` (PCM) format is supported. For non-streaming, you can use `mp3`, `wav`, or `raw`.

## WebSocket API

For the lowest latency and most interactive applications, use the WebSocket API. This allows you to stream text input and receive audio chunks in real-time.

<Warning>
  The WebSocket API is currently only available via raw WebSocket connections. SDK support coming soon.
</Warning>

**Establishing a Connection**

Connect to: `wss://api.together.xyz/v1/audio/speech/websocket`

**Authentication:**

* Include your API key as a query parameter: `?api_key=YOUR_API_KEY`
* Or use the `Authorization` header when establishing the WebSocket connection

**Client → Server Messages**

**1. Append Text to Buffer**

```json  theme={null}
{
  "type": "input_text_buffer.append",
  "text": "Hello, this is a test sentence."
}
```

Appends text to the input buffer. Text is buffered until sentence completion or maximum length is reached.

**2. Commit Buffer**

```json  theme={null}
{
  "type": "input_text_buffer.commit"
}
```

Forces processing of all buffered text. Use this at the end of your input stream.

**3. Clear Buffer**

```json  theme={null}
{
  "type": "input_text_buffer.clear"
}
```

Clears all buffered text without processing (except text already being processed by the model).

**4. Update Session Parameters**

```json  theme={null}
{
  "type": "tts_session.updated",
  "session": {
    "voice": "new_voice_id"
  }
}
```

Updates TTS session settings like voice in real-time.

**Server → Client Messages**

**Session Created**

```json  theme={null}
{
  "event_id": "uuid-string",
  "type": "session.created",
  "session": {
    "id": "session-uuid",
    "object": "realtime.tts.session",
    "modalities": ["text", "audio"],
    "model": "canopylabs/orpheus-3b-0.1-ft",
    "voice": "tara"
  }
}
```

**Text Received Acknowledgment**

```json  theme={null}
{
  "type": "conversation.item.input_text.received",
  "text": "Hello, this is a test sentence."
}
```

**Audio Delta (Streaming Chunks)**

```json  theme={null}
{
  "type": "conversation.item.audio_output.delta",
  "item_id": "tts_1",
  "delta": "base64-encoded-audio-chunk"
}
```

**Audio Complete**

```json  theme={null}
{
  "type": "conversation.item.audio_output.done",
  "item_id": "tts_1"
}
```

**TTS Error**

```json  theme={null}
{
  "type": "conversation.item.tts.failed",
  "error": {
    "message": "Error description",
    "type": "error_type",
    "code": "error_code"
  }
}
```

**WebSocket Example**

<CodeGroup>
  ```python Python theme={null}
  import asyncio
  import websockets
  import json
  import base64
  import os


  async def generate_speech():
      api_key = os.environ.get("TOGETHER_API_KEY")
      url = "wss://api.together.ai/v1/audio/speech/websocket?model=hexgrad/Kokoro-82M&voice=af_alloy"

      headers = {"Authorization": f"Bearer {api_key}"}

      async with websockets.connect(url, additional_headers=headers) as ws:
          # Wait for session created
          session_msg = await ws.recv()
          session_data = json.loads(session_msg)
          print(f"Session created: {session_data['session']['id']}")

          # Send text for TTS
          text_chunks = [
              "Hello, this is a test.",
              "This is the second sentence.",
              "And this is the final one.",
          ]

          async def send_text():
              for chunk in text_chunks:
                  await ws.send(
                      json.dumps(
                          {"type": "input_text_buffer.append", "text": chunk}
                      )
                  )
                  await asyncio.sleep(0.5)  # Simulate typing

              # Commit to process any remaining text
              await ws.send(json.dumps({"type": "input_text_buffer.commit"}))

          async def receive_audio():
              audio_data = bytearray()
              async for message in ws:
                  data = json.loads(message)

                  if data["type"] == "conversation.item.input_text.received":
                      print(f"Text received: {data['text']}")
                  elif data["type"] == "conversation.item.audio_output.delta":
                      # Decode base64 audio chunk
                      audio_chunk = base64.b64decode(data["delta"])
                      audio_data.extend(audio_chunk)
                      print(f"Received audio chunk for item {data['item_id']}")
                  elif data["type"] == "conversation.item.audio_output.done":
                      print(
                          f"Audio generation complete for item {data['item_id']}"
                      )
                  elif data["type"] == "conversation.item.tts.failed":
                      error = data.get("error", {})
                      print(f"Error: {error.get('message')}")
                      break

              # Save the audio to a file
              with open("output.wav", "wb") as f:
                  f.write(audio_data)
              print("Audio saved to output.wav")

          # Run send and receive concurrently
          await asyncio.gather(send_text(), receive_audio())


  asyncio.run(generate_speech())
  ```

  ```typescript TypeScript theme={null}
  import WebSocket from 'ws';
  import fs from 'fs';

  const apiKey = process.env.TOGETHER_API_KEY;
  const url = 'wss://api.together.ai/v1/audio/speech/websocket?model=hexgrad/Kokoro-82M&voice=af_alloy';

  const ws = new WebSocket(url, {
    headers: {
      'Authorization': `Bearer ${apiKey}`
    }
  });

  const audioData: Buffer[] = [];

  ws.on('open', () => {
    console.log('WebSocket connection established!');
  });

  ws.on('message', (data) => {
    const message = JSON.parse(data.toString());

    if (message.type === 'session.created') {
      console.log(`Session created: ${message.session.id}`);
      
      // Send text chunks
      const textChunks = [
        "Hello, this is a test.",
        "This is the second sentence.",
        "And this is the final one."
      ];

      textChunks.forEach((text, index) => {
        setTimeout(() => {
          ws.send(JSON.stringify({
            type: 'input_text_buffer.append',
            text: text
          }));
        }, index * 500);
      });

      // Commit after all chunks
      setTimeout(() => {
        ws.send(JSON.stringify({
          type: 'input_text_buffer.commit'
        }));
      }, textChunks.length * 500 + 100);

    } else if (message.type === 'conversation.item.input_text.received') {
      console.log(`Text received: ${message.text}`);
    } else if (message.type === 'conversation.item.audio_output.delta') {
      // Decode base64 audio chunk
      const audioChunk = Buffer.from(message.delta, 'base64');
      audioData.push(audioChunk);
      console.log(`Received audio chunk for item ${message.item_id}`);
    } else if (message.type === 'conversation.item.audio_output.done') {
      console.log(`Audio generation complete for item ${message.item_id}`);
    } else if (message.type === 'conversation.item.tts.failed') {
      const errorMessage = message.error?.message ?? 'Unknown error';
      console.error(`Error: ${errorMessage}`);
      ws.close();
    }
  });

  ws.on('close', () => {
    // Save the audio to a file
    if (audioData.length > 0) {
      const completeAudio = Buffer.concat(audioData);
      fs.writeFileSync('output.wav', completeAudio);
      console.log('Audio saved to output.wav');
    }
  });

  ws.on('error', (error) => {
    console.error('WebSocket error:', error);
  });
  ```
</CodeGroup>

**WebSocket Parameters**

When establishing a WebSocket connection, you can configure:

| Parameter            | Type    | Description                                                 |
| :------------------- | :------ | :---------------------------------------------------------- |
| model\_id            | string  | The TTS model to use                                        |
| voice                | string  | The voice for generation                                    |
| response\_format     | string  | Audio format: `mp3`, `opus`, `aac`, `flac`, `wav`, or `pcm` |
| speed                | float   | Playback speed (default: 1.0)                               |
| max\_partial\_length | integer | Character buffer length before triggering TTS generation    |

## Output Raw Bytes

If you want to extract out raw audio bytes use the settings below:

<CodeGroup>
  ```python Python theme={null}
  import requests
  import os

  url = "https://api.together.xyz/v1/audio/speech"
  api_key = os.environ.get("TOGETHER_API_KEY")

  headers = {"Authorization": f"Bearer {api_key}"}

  data = {
      "input": "This is a test of raw PCM audio output.",
      "voice": "tara",
      "response_format": "raw",
      "response_encoding": "pcm_f32le",
      "sample_rate": 44100,
      "stream": False,
      "model": "canopylabs/orpheus-3b-0.1-ft",
  }

  response = requests.post(url, headers=headers, json=data)

  with open("output_raw.pcm", "wb") as f:
      f.write(response.content)

  print(f"✅ Raw PCM audio saved to output_raw.pcm")
  print(f"   Size: {len(response.content)} bytes")
  ```

  ```typescript TypeScript theme={null}
  import Together from 'together-ai';

  const together = new Together();

  async function generateRawBytes() {
    const res = await together.audio.create({
      input: 'Hello, how are you today?',
      voice: 'tara',
      response_format: 'raw',
      response_encoding: 'pcm_f32le',
      sample_rate: 44100,
      stream: false,
      model: 'canopylabs/orpheus-3b-0.1-ft',
    });

    console.log(res.body);
  }

  generateRawBytes();
  ```

  ```curl cURL theme={null}
  curl --location 'https://api.together.xyz/v1/audio/speech' \
  --header 'Content-Type: application/json' \
  --header 'Authorization: Bearer $TOGETHER_API_KEY' \
  --output test2.pcm \
  --data '{
      "input": "Hello, this is a test of the text to speech system.",
      "voice": "tara",
      "response_format": "raw",
      "response_encoding": "pcm_f32le",
      "sample_rate": 44100,
      "stream": false,
      "model": "canopylabs/orpheus-3b-0.1-ft"
  }'
  ```
</CodeGroup>

This will output a raw bytes `test2.pcm` file.

## Response Formats

Together AI supports multiple audio formats:

| Format | Extension | Description                                                           | Streaming Support |
| :----- | :-------- | :-------------------------------------------------------------------- | :---------------- |
| wav    | .wav      | Uncompressed audio (larger file size)                                 | No                |
| mp3    | .mp3      | Compressed audio (smaller file size)                                  | No                |
| raw    | .pcm      | Raw PCM audio data                                                    | Yes               |
| mulaw  | .ulaw     | Uses logarithmic compression to optimize speech quality for telephony | Yes               |

## Best Practices

**Choosing the Right Delivery Method**

* **Basic HTTP API:** Best for batch processing or when you need complete audio files
* **Streaming HTTP API:** Best for real-time applications where TTFB matters
* **WebSocket API:** Best for interactive applications requiring lowest latency (chatbots, live assistants)

**Performance Tips**

* Use streaming when you need the fastest time-to-first-byte
* Use WebSocket API for conversational applications
* Buffer text appropriately - sentence boundaries work best for natural speech
* Use the `max_partial_length` parameter in WebSocket to control buffer behavior
* Consider using `raw` (PCM) format for lowest latency, then encode client-side if needed

**Voice Selection**

* Test different voices to find the best match for your application
* Some voices are better suited for specific content types (narration vs conversation)
* Use the Voices API to discover all available options

**Next Steps**

* Explore our [API Reference](/reference/audio-speech) for detailed parameter documentation
* Learn about [Speech-to-Text](/docs/speech-to-text) for the reverse operation
* Check out our [PDF to Podcast guide](/docs/open-notebooklm-pdf-to-podcast) for a complete example

## Supported Voices

Different models support different voices. Use the Voices API to discover available voices for each model.

**Voices API**

<CodeGroup>
  ```python Python theme={null}
  from together import Together

  client = Together()

  # List all available voices
  response = client.audio.voices.list()

  for model_voices in response.data:
      print(f"Model: {model_voices.model}")
      for voice in model_voices.voices:
          print(f"  - Voice: {voice['name']}")
  ```

  ```python Python(v2) theme={null}
  from together import Together

  client = Together()

  # List all available voices
  response = client.audio.voices.list()

  for model_voices in response.data:
      print(f"Model: {model_voices.model}")
      for voice in model_voices.voices:
          print(f"  - Voice: {voice.name}")
  ```

  ```typescript TypeScript theme={null}
  import fetch from 'node-fetch';

  async function getVoices() {
    const apiKey = process.env.TOGETHER_API_KEY;
    const model = 'canopylabs/orpheus-3b-0.1-ft';
    const url = `https://api.together.xyz/v1/voices?model=${model}`;

    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${apiKey}`
      }
    });

    const data = await response.json();
    
    console.log(`Available voices for ${model}:`);
    console.log('='.repeat(50));
    
    // List available voices
    for (const voice of data.voices || []) {
      console.log(voice.name || 'Unknown voice');
    }
  }

  getVoices();
  ```

  ```curl cURL theme={null}
  curl -X GET "https://api.together.xyz/v1/voices?model=canopylabs/orpheus-3b-0.1-ft" \
       -H "Authorization: Bearer $TOGETHER_API_KEY"
  ```
</CodeGroup>

**Available Voices**

**Orpheus Model:**

Sample voices include:

```text Text theme={null}
`tara`
`leah`
`jess`
`leo`
`dan`
`mia`
`zac`
`zoe`
```

For a complete list, query the `/v1/voices` endpoint or see the [Kokoro voice documentation](https://github.com/remsky/Kokoro-FastAPI).

**Kokoro Model:**

```text Text theme={null}
af_heart
af_alloy
af_aoede
af_bella
af_jessica
af_kore
af_nicole
af_nova
af_river
af_sarah
af_sky
am_adam
am_echo
am_eric
am_fenrir
am_liam
am_michael
am_onyx
am_puck
am_santa
bf_alice
bf_emma
bf_isabella
bf_lily
bm_daniel
bm_fable
bm_george
bm_lewis
jf_alpha
jf_gongitsune
jf_nezumi
jf_tebukuro
jm_kumo
zf_xiaobei
zf_xiaoni
zf_xiaoxiao
zf_xiaoyi
zm_yunjian
zm_yunxi
zm_yunxia
zm_yunyang
ef_dora
em_alex
em_santa
ff_siwis
hf_alpha
hf_beta
hm_omega
hm_psi
if_sara
im_nicola
pf_dora
pm_alex
pm_santa
```

**Cartesia Models:**

All valid voice model strings:

```text Text theme={null}
'german conversational woman',
'nonfiction man',
'friendly sidekick',
'french conversational lady',
'french narrator lady',
'german reporter woman',
'indian lady',
'british reading lady',
'british narration lady',
'japanese children book',
'japanese woman conversational',
'japanese male conversational',
'reading lady',
'newsman',
'child',
'meditation lady',
'maria',
"1920's radioman",
'newslady',
'calm lady',
'helpful woman',
'mexican woman',
'korean narrator woman',
'russian calm lady',
'russian narrator man 1',
'russian narrator man 2',
'russian narrator woman',
'hinglish speaking lady',
'italian narrator woman',
'polish narrator woman',
'chinese female conversational',
'pilot over intercom',
'chinese commercial man',
'french narrator man',
'spanish narrator man',
'reading man',
'new york man',
'friendly french man',
'barbershop man',
'indian man',
'australian customer support man',
'friendly australian man',
'wise man',
'friendly reading man',
'customer support man',
'dutch confident man',
'dutch man',
'hindi reporter man',
'italian calm man',
'italian narrator man',
'swedish narrator man',
'polish confident man',
'spanish-speaking storyteller man',
'kentucky woman',
'chinese commercial woman',
'middle eastern woman',
'hindi narrator woman',
'sarah',
'sarah curious',
'laidback woman',
'reflective woman',
'helpful french lady',
'pleasant brazilian lady',
'customer support lady',
'british lady',
'wise lady',
'australian narrator lady',
'indian customer support lady',
'swedish calm lady',
'spanish narrator lady',
'salesman',
'yogaman',
'movieman',
'wizardman',
'australian woman',
'korean calm woman',
'friendly german man',
'announcer man',
'wise guide man',
'midwestern man',
'kentucky man',
'brazilian young man',
'chinese call center man',
'german reporter man',
'confident british man',
'southern man',
'classy british man',
'polite man',
'mexican man',
'korean narrator man',
'turkish narrator man',
'turkish calm man',
'hindi calm man',
'hindi narrator man',
'polish narrator man',
'polish young man',
'alabama male',
'australian male',
'anime girl',
'japanese man book',
'sweet lady',
'commercial lady',
'teacher lady',
'princess',
'commercial man',
'asmr lady',
'professional woman',
'tutorial man',
'calm french woman',
'new york woman',
'spanish-speaking lady',
'midwestern woman',
'sportsman',
'storyteller lady',
'spanish-speaking man',
'doctor mischief',
'spanish-speaking reporter man',
'young spanish-speaking woman',
'the merchant',
'stern french man',
'madame mischief',
'german storyteller man',
'female nurse',
'german conversation man',
'friendly brazilian man',
'german woman',
'southern woman',
'british customer support lady',
'chinese woman narrator',
'pleasant man',
'california girl',
'john',
'anna'
```

**Rime Mist v2 Model:**

```text Text theme={null}
'cove'
'eucalyptus'
'lagoon'
'mari'
'marlu'
'mesa_extra'
'moon'
'moraine'
'peak'
'summit'
'talon'
'thunder'
'tundra'
'wildflower'
```

**Rime Arcana v2 Model:**

```text Text theme={null}
'albion'
'arcade'
'astra'
'atrium'
'bond'
'cupola'
'eliphas'
'estelle'
'eucalyptus'
'fern'
'lintel'
'luna'
'lyra'
'marlu'
'masonry'
'moss'
'oculus'
'parapet'
'pilaster'
'sirius'
'stucco'
'transom'
'truss'
'vashti'
'vespera'
'walnut'
```

**Minimax Speech 2.6 Turbo Model:**

Sample voices include:

```text Text theme={null}
'English_DeterminedMan'
'English_Diligent_Man'
'English_expressive_narrator'
'English_FriendlyNeighbor'
'English_Graceful_Lady'
'Japanese_GentleButler'
```

For a complete list of Minimax voices, query the `/v1/voices` endpoint with the model parameter:

```bash  theme={null}
curl -X GET "https://api.together.ai/v1/voices?model=minimax/speech-2.6-turbo" \
     -H "Authorization: Bearer $TOGETHER_API_KEY"
```

## Pricing

| Model            | Price                         |
| :--------------- | :---------------------------- |
| Orpheus 3B       | \$15 per 1 Million characters |
| Kokoro           | \$4 per 1 Million characters  |
| Cartesia Sonic 2 | \$65 per 1 Million characters |
