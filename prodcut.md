# Realtime Multilingual Voice Assistant — System Design & Product Report

**Goal.** Build a robust, low‑latency, multilingual conversational AI that (1) listens continuously, (2) records queries with user consent, (3) answers back as natural speech in the user's language, and (4) predicts likely intents to **speculatively prefetch** answers and start speaking faster than traditional pipelines.

---

## 0) Executive Summary

This report provides a complete blueprint—product scope, architecture, data flows, models, APIs, infra, security, QA, and a staged roadmap—to deliver a production‑ready realtime voice assistant with **predict‑before‑they‑finish** behavior. It assumes a budget‑conscious stack using open‑source components where possible, with optional hooks to commercial APIs.

**Key Outcomes**

* Sub‑second time‑to‑first‑audio (TTFA \~300–900 ms) via streaming ASR + speculative prefetch + TTS warmup.
* Natural, multilingual speech with code‑switch handling (e.g., Nepali ↔ English).
* On‑device/offline friendly edge features: wake‑word, VAD, AEC (echo cancel), privacy controls.
* Modular services (LLM, RAG, ASR, TTS, Intent, Speculation) connected through a realtime orchestration layer.

---

## 1) Product Scope & UX

### 1.1 Personas & Use Cases

* **Student/Professional**: “What’s my schedule?” “Summarize this PDF.” “Explain PM2.5 trends in Dhulikhel.”
* **Home user**: “Set a reminder.” “What’s the weather?” “Translate this into Nepali.”
* **Developer**: “Run test suite.” “Deploy service.”

### 1.2 Core User Stories

1. As a user, I press‑to‑talk or say the wake word, and the assistant starts listening with a **recording consent toggle**.
2. While I’m speaking, the assistant infers my intent from **partial transcripts** and prefetches likely results.
3. As soon as the first sentence is ready, the assistant **speaks back** in my language while completing the rest.
4. I can interrupt (barge‑in), switch languages mid‑utterance, and get concise follow‑ups.

### 1.3 Non‑Goals (v1)

* Complex multi‑speaker diarization.
* Long document ingestion at runtime (handled via offline ingestion jobs instead).

---

## 2) Requirements

### 2.1 Functional

* Continuous/streaming capture with VAD + endpointing.
* Streaming ASR with partial hypotheses (50–150 ms cadence) + timestamps.
* Language identification + code‑switch detection.
* Fast intent/slot extraction on partials for speculative execution.
* LLM reasoning with tool/function‑calling and RAG.
* Streaming TTS with SSML for prosody; per‑session voice/locale.
* Consent‑based recording, export/delete endpoints.

### 2.2 Non‑Functional

* **Latency**: TTFA ≤ 900 ms; P95 end‑to‑audio ≤ 2.5 s for typical queries.
* **Availability**: 99.9% monthly; graceful degradation offline/low‑connectivity.
* **Privacy/Security**: PII redaction in logs; data retention TTLs; encryption in transit/at rest.
* **Cost**: Favor CPU‑friendly models (quantized) and caching.

---

## 3) Reference Architecture (Service‑Oriented)

```
Client (Web/Mobile)
 ├── Mic capture → WebRTC/WS (Opus/PCM frames)
 ├── Local VAD + Wake‑word + AEC (echo cancel)
 └── Audio playback (jitter buffer, barge‑in aware)

Edge/API Gateway
 └── Session broker (WebRTC/WS) • Auth • Rate limit • Tracing

Speech Frontend Service
 ├── VAD + endpointing
 ├── Streaming ASR (faster‑whisper/onnx) → partials
 └── LangID + code‑switch

Intent Service (Fast)
 ├── Tiny transformer classifier (6–24M params)
 ├── Slot/Entity extractor (regex+NER)
 └── Next‑turn Predictor (speculation)

Orchestrator (Realtime)
 ├── Speculative Execution Manager (cancellable futures)
 ├── Tool Router (weather/news/db/search)
 ├── RAG Gateway (vector store)
 └── LLM (streaming tokens + tool calls)

Response Service
 ├── NLG post‑processor (JSON → SSML)
 └── Streaming TTS (XTTS/Piper) → Opus chunks

Observability & Storage
 ├── Metrics/Traces/Logs (Prometheus+Loki+OTel)
 ├── Session store (Redis) • Cache (Redis/QCache)
 └── Object store for opt‑in audio/text (S3‑compatible)
```

**Why this split?** Independent scaling (ASR and TTS are heavy), simpler failure isolation, and flexible deployment (single box for dev → k8s for prod).

---

## 4) Component Responsibilities

* **Client**: mic → encoded frames; playback; barge‑in; consent UI; transcript view.
* **Gateway**: auth (JWT), session tokens, per‑session limits, trace IDs.
* **Speech Frontend**: timestamped partials; endpointing; language ID; ASR confidence.
* **Intent Service**: early intent on partials; slots; stability smoothing; emit **speculation events**.
* **Orchestrator**: launches cancellable tasks based on speculation; fuses final ASR + tool results; ensures time budgets.
* **RAG Gateway**: top‑k retrieval with query rewriting; caches by (intent, locale, profile, recency).
* **LLM**: tool selection and reasoning; always returns a structured payload `{language, intent, slots, answer, ssml}`.
* **TTS**: stream audio as soon as first sentence available; pre‑warm voice.

---

## 5) Data Flow (Happy Path)

1. Client sends audio frames → Gateway → Speech Frontend.
2. Frontend yields partial transcripts (every \~100 ms) + confidences.
3. Intent Service runs on partials → emits `(intent, p, slots)`.
4. Orchestrator sees p>τ → issues speculative RAG/API calls & **pre‑warms TTS**.
5. Endpointing fires → final transcript dispatched to LLM + tools.
6. Response Service starts **streaming TTS** immediately; client plays.
7. Orchestrator cancels mismatched speculations; logs metrics.

**Edge cases**: barge‑in interrupts TTS; confidence dips → filler SSML or clarification; network jitter → adaptive packet size.

---

## 6) Models & Intelligence

### 6.1 ASR

* **Model**: faster‑whisper (multilingual) with VAD‑guided chunking; ONNX‑runtime/Int4 quant for CPU.
* **Endpointing**: combo of silence timeout + token‑stability heuristics.
* **Confidence**: word‑level; send with timestamps for alignment/barge‑in.

### 6.2 Language ID & Code‑Switch

* Chunk‑level LangID (fasttext‑style or tiny transformer). If code‑switch detected, maintain **answer language = last dominant user language** unless user preference overrides.

### 6.3 Fast Intent & Slots

* **Architecture**: Distil/ALBERT‑size transformer fine‑tuned on labels (weather, reminder, search, small‑talk, navigation, Q\&A‑RAG…).
* **Inputs**: partial transcript n‑grams, preceding turn, device context.
* **Stabilization**: temporal smoothing (HMM‑like) across partials; only emit speculation when p>τ for `X ms`.

### 6.4 Next‑Turn Predictor (Speculation)

* **Objective**: predict top‑k intents before final ASR; kick off prefetch.
* **Features**: partial tokens; phoneme rate; VAD energy; time since last turn; user profile; recency features (hour/day); last‑k intents; RAG cache hits.
* **Training**: Cross‑entropy on next‑intent; **distill** logits from larger LLM’s intent labels for better generalization.
* **Serving**: 2–3 ms/batch on CPU with ONNX; sliding window state.
* **Metrics**: Hit‑rate\@k, wasted compute, net latency saved.

### 6.5 LLM + Tools + RAG

* **LLM**: open‑source instruct model (7–8B) with tool calling; quantized GGUF ok.
* **RAG**: E5‑small‑v2 or Instructor embeddings; Chroma/Qdrant; top‑k = 6–12 with MMR; recency bias.
* **Tools**: weather, news, calendar, search, DB. Enforce strict JSON schema.

### 6.6 TTS

* **Model**: Coqui XTTS v2 (multilingual) or Piper for ultra‑fast CPU.
* **Streaming**: synth first sentence immediately; SSML prosody and breaks; pre‑load speaker.

---

## 7) APIs & Protocols

### 7.1 Realtime WebSocket (binary + JSON envelopes)

```json
// Client → Server (audio frame)
{
  "t": "audio_frame",
  "session_id": "...",
  "seq": 1287,
  "codec": "opus",
  "sample_rate": 16000,
  "payload": "<bytes>"
}

// Server → Client (ASR partial)
{
  "t": "asr_partial",
  "text": "what is weat...",
  "ts": [{"w":"what","start":0.12,"end":0.28,"conf":0.91}],
  "lang": "en",
  "final": false
}

// Server → Client (speculation)
{
  "t": "speculation",
  "intent": "weather",
  "p": 0.83,
  "slots": {"city": "Dhulikhel"}
}

// Server → Client (TTS chunk)
{
  "t": "tts_chunk",
  "seq": 412,
  "payload": "<bytes>",
  "eos": false
}
```

### 7.2 REST (control plane)

* `POST /session` → token, voice/locale, consent flags.
* `POST /ingest` → documents to index (offline).
* `GET /export/{session}` → transcripts/audio if consented.

---

## 8) Data Schemas

**Session** `{id, user_id, lang_pref, voice_id, consent:{audio:boolean,text:boolean}, created_at}`

**Transcript** `{id, session_id, text, words:[{w,start,end,conf}], lang, created_at}`

**SpeculationEvent** `{id, session_id, intent, p, slots, started_at, canceled_at?}`

**ToolCall** `{id, session_id, tool, args, latency_ms, success, cached}`

**TTSChunk** `{session_id, seq, bytes_len, produced_at}`

---

## 9) Caching & Performance Strategy

* **LRU per session**: last tool results, last RAG chunks.
* **LFU global**: public data (weather for popular cities, headlines).
* **Speculation TTL**: 60–180 s; invalidate on context change.
* **Warmups**: pre‑load TTS voice; JIT compile ONNX graphs; open DB cursors with short keep‑alive.
* **Backpressure**: if ASR lag > 250 ms, reduce frame rate/size; suspend speculation when CPU>85%.

---

## 10) Security, Privacy & Compliance

* **Consent‑first** recording (separate toggles for audio/text). Default OFF.
* **PII redaction**: phone, email, IDs in logs; hashing for analytics.
* **Encryption**: TLS; KMS‑managed keys for storage; signed URLs for exports.
* **Retention**: default 7–30 days; user‑driven delete/export (GDPR‑style rights).
* **Abuse/Safety**: toxicity filter before TTS; jailbreak guardrails on LLM.

---

## 11) Observability & QA

* **Metrics**: TTFA, WER, Intent‑F1 (partial vs final), Speculation Hit‑rate, Tool latency, TTS underruns, Barge‑in frequency, CPU/GPU util.
* **Tracing**: per session span tree (ASR→Intent→Speculation→RAG→LLM→TTS).
* **Logging**: structured JSON with trace\_id, no raw audio unless consented.
* **Testing**:

  * Unit: VAD, endpointing, intent classifier, tool schemas.
  * Integration: ASR↔Intent↔Speculation loop; RAG correctness.
  * E2E: scripted audio fixtures; language/code‑switch scenarios.
  * Load: soak tests with synthetic speech; chaos (kill ASR pod).

---

## 12) Dev Workflow & Best Practices

* **Repo layout**

```
/voice-assistant
  /client     # Web/mobile app
  /gateway    # Auth, sessions, WS
  /speech     # VAD, ASR, LangID
  /intent     # Fast intent + next-turn
  /orchestrator
  /rag        # indexers + query gateway
  /tts        # streaming synthesis
  /common     # protobuf/JSON schemas, utils
  /infra      # docker, k8s, terraform
  /tests      # unit, e2e, fixtures
```

* **Coding standards**: type hints (mypy), lint (ruff/eslint), docstrings; small modules; functional cores; DI for models.
* **Reliability**: timeouts, retries with jitter, circuit breakers, idempotency keys.
* **Interfaces**: spec‑first OpenAPI; JSON schema validation; versioned endpoints (v1,v2).
* **CI/CD**: build → unit → integration (docker‑compose) → e2e harness with audio fixtures → security scan → deploy.
* **Dependencies**: lockfiles; semantic versioning; reproducible builds.

---

## 13) Deployment Topologies

* **Single‑node dev**: docker‑compose; CPU only; quantized models.
* **Small prod**: 1 GPU node for ASR+TTS; CPU nodes for intent, LLM(7B‑q), RAG.
* **Kubernetes**: HPA on ASR/TTS; node affinities for GPU; pod disruption budgets; rolling updates.
* **Edge**: optional on‑device VAD/wake‑word; WebRTC TURN servers.

---

## 14) Performance Tuning Cheatsheet

* ONNX‑runtime for ASR/Intent; int8/int4 quantization; batch partials across sessions.
* Keep audio frames small (20–40 ms) for smoother partials; Opus at 16 kHz for speech.
* Pre‑split responses into sentence chunks for TTS; stream as soon as 1st chunk ready.
* Cache embeddings; use MMR to avoid near‑duplicates; cap RAG token budget.
* Use **cancellable futures**: cancel prefetch immediately when intent flips.

---

## 15) Rollout Plan (Fast, Optimized Development)

**Phase 0 – Week 1: Foundations**

* Stand up mono‑repo & CI; define JSON/Proto schemas; stub services; local docker‑compose.
* Implement VAD + streaming WebSocket; play back loopback audio.

**Phase 1 – Week 2–3: Core Realtime**

* Add streaming ASR partials + endpointing; display live transcript.
* Implement fast Intent on partials; emit speculation events.
* Wire Orchestrator to launch cancellable RAG/weather/search calls.
* Add streaming TTS; sentence‑by‑sentence playback; barge‑in handling.

**Phase 2 – Week 4–5: Intelligence & RAG**

* Train Next‑Turn predictor; measure hit‑rate and net latency saved.
* Build ingestion pipeline for docs; add query rewriting; eval retrieval quality.

**Phase 3 – Week 6: Privacy & Observability**

* Consent flows, redaction, export/delete endpoints.
* Full tracing and dashboards; SLO alerts.

**Phase 4 – Week 7+: Hardening & Beta**

* Chaos tests; load tests; fallback modes; localization polish (Nepali default voices).

---

## 16) Risks & Mitigations

* **ASR drift in noisy rooms** → AEC on client, noise suppression, confidence‑aware clarifications.
* **Speculation wastes compute** → strict thresholds; budget guard; adaptive enable under load.
* **TTS underruns/stutter** → jitter buffer; pre‑roll 200–300 ms; avoid GC pauses.
* **Code‑switch mis‑detections** → chunk‑wise LangID; fallback to user preference.
* **PII leakage** → redaction + minimization; review pipelines regularly.

---

## 17) Quick Start (Local Dev)

1. **Clone & bootstrap**

   * `make bootstrap` → creates venvs, installs deps, pre‑downloads models.
2. **Run stack**

   * `docker compose up` launches gateway, speech, intent, orchestrator, tts, rag.
3. **Open client**

   * Web app: press‑to‑talk; see partial ASR; hear TTS.
4. **Speculation demo**

   * Speak “what’s the weath…” → observe prefetch weather call and fast audio start.

---

## 18) Sample Pseudocode (Server Skeleton)

```python
# FastAPI WS handler (trimmed)
@app.websocket("/realtime")
async def realtime(ws):
    sess = new_session(ws)
    asr = StreamingASR()
    intent = FastIntent()
    spec = SpecExecManager()
    tts = StreamingTTS()

    async for msg in ws_iter_frames(ws):
        if msg.type == 'audio_frame':
            partial = asr.feed(msg.bytes)
            if partial:
                await ws.send_json(partial.to_json())
                guess = intent.update(partial.text)
                if guess.p > 0.75 and spec.idle_or_new(guess.intent):
                    spec.spawn(guess, sess.context)
        if asr.endpointed:
            final = asr.finalize()
            result = await reason_with_tools(final.text, spec)
            async for chunk in tts.stream(result.ssml, lang=result.language):
                await ws.send_bytes(chunk)
            spec.cancel_others(result.intent)
```

---

## 19) Configuration Defaults

* **Audio**: Opus 16 kHz, 20 ms frames, max 60 kbps.
* **ASR**: beam size 1–2; temperature fallback only when conf < 0.55.
* **Intent**: τ=0.75; dwell=120 ms; top‑k=2; cooldown=800 ms after cancel.
* **RAG**: k=8; MMR λ=0.5; max 800 retrieved tokens.
* **TTS**: pre‑roll 240 ms; buffer low‑watermark 120 ms.

---

## 20) Appendix A — Docker Compose (sketch)

```yaml
services:
  gateway:
    image: app/gateway
    ports: ["8080:8080"]
  speech:
    image: app/speech
    deploy:
      resources:
        limits: {cpus: "2"}
  intent:
    image: app/intent
  orchestrator:
    image: app/orchestrator
  tts:
    image: app/tts
  rag:
    image: app/rag
  redis:
    image: redis:7
```

---

## 21) Appendix B — Checklist (Be Careful About)

* Don’t start TTS without confirming intent stability or you’ll speak the wrong thing.
* Always send timestamps/conf from ASR; barge‑in depends on them.
* Cancel speculative calls immediately to free connections.
* Limit tool calls to a strict budget (e.g., ≤1.2 s) to avoid tail latency.
* Never log raw audio/text without consent; scrub PII.
* Enforce WS backpressure; drop frames gracefully on overload.
* Add A/B guardrails: turn off speculation automatically when CPU>85%.

---

## 22) Appendix C — Roadmap & KPIs

* **KPIs**: TTFA, P95 E2E latency, Speculation hit‑rate, WER, Intent‑F1, Barge‑in success, Cost/1k turns.
* **Quarterly Targets**: TTFA < 600 ms; Hit‑rate\@1 > 65%; P95 E2E < 2.0 s.

---

**End of Report**
