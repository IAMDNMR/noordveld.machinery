import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { sparkSpeak as synthesizeSpeech, sparkTranscribe as transcribeAudio } from '../../api/spark'

/** idle: ready. listening: the microphone is open. transcribing: the recording is being turned into text. speaking: the reply is playing. */
export type VoiceState =
  'idle' | 'listening' | 'transcribing' | 'speaking' | 'unavailable' | 'error'

const SPEECH_LEVEL = 0.02 // RMS of the microphone signal that counts as someone speaking
const END_OF_TURN_MS = 1400 // silence after speech that ends the turn
const NO_SPEECH_MS = 9000 // give up when nobody speaks
const MAX_RECORDING_MS = 60000
const BARGE_IN_LEVEL = 0.07 // louder than this for a moment while the assistant speaks = the person is interrupting
const BARGE_IN_MS = 450
const MIME_TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']

type Options = {
  /** Whether the server has a speech provider. When false the microphone is shown as unavailable with the reason; nothing pretends to work. */
  available: boolean
  unavailableReason: string
  onTranscript: (text: string, confidence: number | null) => void
  transport?: {
    transcribe: typeof transcribeAudio
    synthesize: typeof synthesizeSpeech
  }
}

const rms = (data: Uint8Array) =>
  Math.sqrt(data.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / data.length)

/** Microphone capture with end-of-speech detection, speech-to-text through the server, and spoken replies that the person can interrupt. */
export function useVoice({ available, unavailableReason, onTranscript, transport }: Options) {
  const transcribe = transport?.transcribe ?? transcribeAudio
  const synthesize = transport?.synthesize ?? synthesizeSpeech
  const [recorded, setState] = useState<VoiceState>('idle')
  const [level, setLevel] = useState(0)
  const [message, setMessage] = useState<string | null>(null)
  const [handsFree, setHandsFreeState] = useState(false)
  const [speakReplies, setSpeakReplies] = useState(false)
  const handsFreeRef = useRef(false)
  const transcriptRef = useRef(onTranscript)
  useEffect(() => {
    transcriptRef.current = onTranscript
  })
  const stateRef = useRef<VoiceState>('idle')
  const set = useCallback((next: VoiceState) => {
    stateRef.current = next
    setState(next)
  }, [])

  const stream = useRef<MediaStream | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const context = useRef<AudioContext | null>(null)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const discard = useRef(false)
  const heard = useRef(false)
  const audio = useRef<HTMLAudioElement | null>(null)
  const audioUrl = useRef<string | null>(null)
  const speechRequest = useRef<AbortController | null>(null)
  const transcribeRequest = useRef<AbortController | null>(null)
  const monitor = useRef<ReturnType<typeof setInterval> | null>(null)
  const alive = useRef(true)
  const opening = useRef(false)

  const releaseMicrophone = useCallback(() => {
    if (timer.current) clearInterval(timer.current)
    timer.current = null
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
    void context.current?.close().catch(() => undefined)
    context.current = null
    setLevel(0)
  }, [])

  const stopPlayback = useCallback(() => {
    if (monitor.current) clearInterval(monitor.current)
    monitor.current = null
    speechRequest.current?.abort()
    speechRequest.current = null
    if (audio.current) {
      audio.current.onended = null
      audio.current.onerror = null
      audio.current.pause()
      audio.current = null
    }
    if (audioUrl.current) {
      URL.revokeObjectURL(audioUrl.current)
      audioUrl.current = null
    }
  }, [])

  const finish = useCallback(async () => {
    const recording = new Blob(chunks.current, { type: recorder.current?.mimeType || 'audio/webm' })
    chunks.current = []
    releaseMicrophone()
    if (discard.current || !alive.current) {
      if (alive.current) set('idle')
      return
    }
    if (!heard.current || recording.size < 800) {
      set('idle')
      setMessage('I did not hear anything. Tap the microphone and try again, or type.')
      return
    }
    set('transcribing')
    const request = new AbortController()
    transcribeRequest.current = request
    try {
      const result = await transcribe(recording, request.signal)
      if (!alive.current || request.signal.aborted) return
      if (!result.text.trim()) {
        set('error')
        setMessage('No words were recognized. Try recording again, or type your question.')
        return
      }
      set('idle')
      setMessage(null)
      transcriptRef.current(result.text, result.confidence)
    } catch (cause) {
      if (request.signal.aborted || !alive.current) return
      set('error')
      setMessage(
        cause instanceof ApiError ? cause.message : 'Speech recognition failed. Type instead.',
      )
    }
  }, [releaseMicrophone, set, transcribe])

  const stopListening = useCallback(() => {
    if (recorder.current?.state === 'recording') recorder.current.stop()
  }, [])

  const start = useCallback(async () => {
    if (
      !available ||
      opening.current ||
      stateRef.current === 'listening' ||
      stateRef.current === 'transcribing'
    )
      return
    stopPlayback()
    setMessage(null)
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      set('error')
      setMessage('This browser cannot record audio on this page. Type instead.')
      return
    }
    let media: MediaStream
    opening.current = true
    try {
      media = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
    } catch (cause) {
      set('error')
      setMessage(
        cause instanceof DOMException &&
          (cause.name === 'NotAllowedError' || cause.name === 'SecurityError')
          ? 'Microphone access is blocked. Allow it in the address bar, or type instead.'
          : 'No microphone was found. Type instead.',
      )
      return
    } finally {
      opening.current = false
    }
    if (!alive.current) {
      media.getTracks().forEach((track) => track.stop())
      return
    }
    stream.current = media
    discard.current = false
    heard.current = false
    chunks.current = []
    try {
      const mimeType = MIME_TYPES.find(
        (type) =>
          typeof MediaRecorder.isTypeSupported === 'function' &&
          MediaRecorder.isTypeSupported(type),
      )
      const rec = new MediaRecorder(media, mimeType ? { mimeType } : undefined)
      recorder.current = rec
      rec.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data)
      }
      rec.onstop = () => {
        void finish()
      }
      rec.start(250)
      set('listening')
      const ctx = new AudioContext()
      context.current = ctx
      if (ctx.state === 'suspended') await ctx.resume()
      if (!alive.current || discard.current || rec.state !== 'recording') {
        releaseMicrophone()
        return
      }
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 1024
      ctx.createMediaStreamSource(media).connect(analyser)
      const samples = new Uint8Array(analyser.fftSize)
      const began = Date.now()
      let lastVoice = began
      timer.current = setInterval(() => {
        analyser.getByteTimeDomainData(samples)
        const volume = rms(samples)
        setLevel(Math.min(1, volume * 7))
        const now = Date.now()
        if (volume > SPEECH_LEVEL) {
          heard.current = true
          lastVoice = now
        }
        if (heard.current && now - lastVoice > END_OF_TURN_MS) stopListening()
        else if (!heard.current && now - began > NO_SPEECH_MS) stopListening()
        else if (now - began > MAX_RECORDING_MS) stopListening()
      }, 60)
    } catch {
      if (recorder.current) {
        recorder.current.onstop = null
        if (recorder.current.state === 'recording') recorder.current.stop()
      }
      releaseMicrophone()
      if (alive.current) {
        set('error')
        setMessage('The microphone could not start recording. Try again, or type your question.')
      }
    }
  }, [available, finish, releaseMicrophone, set, stopListening, stopPlayback])

  /** Stop speaking at once (the person is interrupting). */
  const interrupt = useCallback(() => {
    stopPlayback()
    if (stateRef.current === 'speaking') set('idle')
  }, [set, stopPlayback])

  /** Close the microphone and throw the recording away. */
  const cancel = useCallback(() => {
    discard.current = true
    transcribeRequest.current?.abort()
    if (recorder.current?.state === 'recording') recorder.current.stop()
    else {
      releaseMicrophone()
      if (stateRef.current === 'listening' || stateRef.current === 'transcribing') set('idle')
    }
  }, [releaseMicrophone, set])

  /** While a reply plays in hands-free mode, a sustained louder voice means the person is interrupting. */
  const listenForInterruption = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) return
    let probe: MediaStream
    try {
      probe = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      })
    } catch {
      return
    }
    if (stateRef.current !== 'speaking') {
      probe.getTracks().forEach((track) => track.stop())
      return
    }
    const ctx = new AudioContext()
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 1024
    ctx.createMediaStreamSource(probe).connect(analyser)
    const samples = new Uint8Array(analyser.fftSize)
    let since = 0
    monitor.current = setInterval(() => {
      analyser.getByteTimeDomainData(samples)
      since = rms(samples) > BARGE_IN_LEVEL ? since + 60 : 0
      if (since >= BARGE_IN_MS || stateRef.current !== 'speaking') {
        if (monitor.current) clearInterval(monitor.current)
        monitor.current = null
        probe.getTracks().forEach((track) => track.stop())
        void ctx.close().catch(() => undefined)
        if (stateRef.current === 'speaking') {
          interrupt()
          void start()
        }
      }
    }, 60)
  }, [interrupt, start])

  const speak = useCallback(
    /** `spoken`: the person asked by voice, so the reply is spoken even when "Read replies aloud" is off. Typed messages stay silent unless it is on. */
    async (text: string, spoken = false) => {
      if (!available || !(speakReplies || spoken) || !text.trim()) {
        if (handsFreeRef.current && available) void start()
        return
      }
      stopPlayback()
      const request = new AbortController()
      speechRequest.current = request
      set('speaking')
      try {
        const blob = await synthesize(text, request.signal)
        if (request.signal.aborted || !alive.current) return
        const url = URL.createObjectURL(blob)
        audioUrl.current = url
        const player = new Audio(url)
        audio.current = player
        const done = () => {
          stopPlayback()
          if (!alive.current) return
          set('idle')
          if (handsFreeRef.current) void start()
        }
        player.onended = done
        player.onerror = () => {
          stopPlayback()
          set('idle')
          setMessage('The reply could not be played.')
        }
        await player.play()
        if (handsFreeRef.current && stream.current === null) void listenForInterruption()
      } catch (cause) {
        if (request.signal.aborted || !alive.current) return
        stopPlayback()
        set('idle')
        setMessage(
          cause instanceof DOMException && cause.name === 'NotAllowedError'
            ? 'Your browser blocked audio playback. Tap the microphone once to allow it.'
            : cause instanceof ApiError
              ? cause.message
              : 'The reply could not be spoken.',
        )
      }
    },
    [available, speakReplies, set, start, stopPlayback, listenForInterruption, synthesize],
  )

  /** The microphone button: speak, send, or interrupt - whichever the moment needs. */
  const toggle = useCallback(() => {
    if (stateRef.current === 'listening') stopListening()
    else if (stateRef.current === 'speaking') {
      interrupt()
      void start()
    } else if (stateRef.current === 'transcribing') cancel()
    else void start()
  }, [cancel, interrupt, start, stopListening])

  const setHandsFree = useCallback((on: boolean) => {
    handsFreeRef.current = on
    setHandsFreeState(on)
  }, [])
  const dismiss = useCallback(() => {
    setMessage(null)
    if (stateRef.current === 'error') set('idle')
  }, [set])

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      discard.current = true
      stopPlayback()
      transcribeRequest.current?.abort()
      if (recorder.current?.state === 'recording') recorder.current.stop()
      releaseMicrophone()
    }
  }, [releaseMicrophone, stopPlayback])

  // Without a speech provider the control is unavailable, whatever it was doing, and says why.
  const state: VoiceState = available ? recorded : 'unavailable'
  return {
    state,
    level,
    message: available ? message : unavailableReason,
    handsFree,
    setHandsFree,
    speakReplies,
    setSpeakReplies,
    start,
    toggle,
    cancel,
    interrupt,
    speak,
    dismiss,
  }
}
