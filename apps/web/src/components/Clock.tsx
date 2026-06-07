import { useEffect, useState } from 'react'

function nyTime(): string {
  return (
    new Date().toLocaleTimeString('en-US', {
      hour12: false,
      timeZone: 'America/New_York',
    }) + ' EDT'
  )
}

export function Clock() {
  const [now, setNow] = useState(nyTime)
  useEffect(() => {
    const id = setInterval(() => setNow(nyTime()), 1000)
    return () => clearInterval(id)
  }, [])
  return <span className="font-mono text-[11px] tabular-nums text-txtDim">{now}</span>
}
