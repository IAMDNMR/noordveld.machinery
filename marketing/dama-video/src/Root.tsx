import React from 'react'
import { AbsoluteFill, Composition, Sequence, useCurrentFrame, useVideoConfig } from 'remotion'
import '@fontsource/dm-sans/400.css'
import '@fontsource/dm-sans/500.css'
import '@fontsource/dm-sans/600.css'
import '@fontsource/dm-sans/700.css'
import '@fontsource/dm-sans/800.css'
import TL from './timeline.json'
import { C, FONT, H, W, p } from './lib'
import { Opening } from './scenes/Opening'
import { Yoa } from './scenes/Yoa'
import { Turn } from './scenes/Turn'
import { Gecko } from './scenes/Gecko'
import { Invite } from './scenes/Invite'

const SCENES: [keyof typeof TL.scenes, React.FC<{ t: number }>][] = [
  ['opening', Opening], ['yoa', Yoa], ['turn', Turn], ['gecko', Gecko], ['invite', Invite],
]

/** Feeds each scene its local time in seconds, so scenes stay pure functions of time. */
const Local: React.FC<{ C: React.FC<{ t: number }> }> = ({ C: Scene }) => {
  const frame = useCurrentFrame()
  const { fps } = useVideoConfig()
  return <Scene t={frame / fps} />
}

const Captions: React.FC = () => {
  const t = useCurrentFrame() / useVideoConfig().fps
  const cue = TL.captions.find(([a, b]) => t >= (a as number) && t < (b as number))
  if (!cue) return null
  const [a, b, text] = cue as [number, number, string]
  const k = Math.min(p(t, a, a + 0.18), 1 - p(t, b - 0.15, b))
  return (
    <div style={{ position: 'absolute', left: 60, right: 60, bottom: 200, display: 'flex', justifyContent: 'center', opacity: k }}>
      <div style={{
        fontFamily: FONT, fontSize: 40, fontWeight: 600, lineHeight: 1.25, color: C.white, textAlign: 'center',
        background: 'rgba(5,11,36,0.72)', padding: '16px 30px', borderRadius: 22, maxWidth: 900,
      }}>{text}</div>
    </div>
  )
}

const Promo: React.FC = () => {
  const { fps } = useVideoConfig()
  return (
    <AbsoluteFill style={{ background: C.deep }}>
      {SCENES.map(([id, S]) => {
        const [a, b] = TL.scenes[id]
        return (
          <Sequence key={id} from={Math.round(a * fps)} durationInFrames={Math.round((b - a) * fps)}>
            <Local C={S} />
          </Sequence>
        )
      })}
      <Captions />
    </AbsoluteFill>
  )
}

export const RemotionRoot: React.FC = () => (
  <Composition id="DamaPromo" component={Promo} durationInFrames={Math.round(TL.duration * TL.fps)} fps={TL.fps} width={W} height={H} />
)
