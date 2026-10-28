import './spark-logo.css'

/**
 * Spark, the round assistant with an antenna and signal arcs, as drawn in the Spark films (yoa-launch-film/src/spark.tsx).
 * A static vector with CSS motion: it blinks, the signal pulses and the orbit ring turns. `still` and reduced motion stop all of it.
 * Drawn in a 400×460 box; the body circle sits at (200, 250), radius 150.
 */
export function SparkLogo({
  size = 40,
  still = false,
  orbit = true,
  label,
  className = '',
}: {
  size?: number
  still?: boolean
  orbit?: boolean
  /** Accessible name; decorative when omitted */
  label?: string
  className?: string
}) {
  return (
    <svg
      className={`spark-logo${still ? ' is-still' : ''} ${className}`}
      width={size}
      height={(size * 460) / 400}
      viewBox="0 -10 400 470"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      overflow="visible"
    >
      <g className="spark-logo__body">
        <ellipse cx={158} cy={420} rx={40} ry={15} className="spark-logo__ink" />
        <ellipse cx={242} cy={420} rx={40} ry={15} className="spark-logo__ink" />
        <circle
          cx={200}
          cy={250}
          r={150}
          fill="#fff"
          className="spark-logo__outline"
          strokeWidth={8}
        />
        <path
          d="M 78.4 302 A 132 132 0 0 0 321.6 302"
          fill="none"
          className="spark-logo__teal-stroke"
          strokeWidth={15}
          strokeLinecap="round"
        />
        <g className="spark-logo__eyes">
          {[150, 250].map((x) => (
            <g key={x}>
              <circle cx={x} cy={225} r={30} fill="#ededed" />
              <circle cx={x} cy={225} r={12} className="spark-logo__ink" />
              <circle cx={x + 4} cy={221} r={3.5} fill="#fff" />
            </g>
          ))}
        </g>
        <path
          d="M 158 298 Q 200 346 242 298 Q 200 310 158 298 Z"
          fill="#fff"
          className="spark-logo__outline"
          strokeWidth={6}
          strokeLinejoin="round"
        />
        {orbit ? (
          <ellipse
            className="spark-logo__orbit"
            cx={200}
            cy={268}
            rx={198}
            ry={44}
            fill="none"
            strokeWidth={5}
            strokeDasharray="14 11"
            transform="rotate(-9 200 268)"
          />
        ) : null}
        <circle cx={200} cy={95} r={17} className="spark-logo__bead" strokeWidth={6} />
        <path
          className="spark-logo__arc spark-logo__arc--1"
          d="M 170.5 63.4 A 36 36 0 0 1 229.5 63.4"
          fill="none"
          strokeWidth={9}
          strokeLinecap="round"
        />
        <path
          className="spark-logo__arc spark-logo__arc--2"
          d="M 145.9 46.1 A 66 66 0 0 1 254.1 46.1"
          fill="none"
          strokeWidth={9}
          strokeLinecap="round"
        />
      </g>
    </svg>
  )
}
