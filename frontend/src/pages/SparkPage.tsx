import { useSearchParams } from 'react-router-dom'
import { PartWorkspace, TABS } from '../components/intelligence/PartWorkspace'
import { SparkHome } from '../components/spark/SparkHome'
import { SPARK_CHAT_ROUTE } from '../data/content'
import { usePageMeta } from '../hooks/usePageMeta'
import '../styles/wf.css'
import '../components/intelligence/intelligence.css'

/** The Spark conversation. A bookmarked part (`?part=`) opens that part's own page. */
export default function SparkPage() {
  usePageMeta({
    title: 'Ask Spark',
    description: 'One conversation for parts intelligence, buying options and your orders.',
    path: SPARK_CHAT_ROUTE,
  })
  const [params, setParams] = useSearchParams()
  const part = params.get('part')
  if (!part) return <SparkHome />
  const tab = TABS.find((item) => item.id === params.get('tab'))?.id ?? 'overview'
  return (
    <div className="wf pi-page">
      <PartWorkspace
        key={part}
        partKey={part}
        tab={tab}
        backLabel="Back to Spark"
        onTab={(value) => {
          const next = new URLSearchParams(params)
          next.set('tab', value)
          setParams(next, { replace: true })
        }}
        onOpenPart={(key) => setParams({ part: key, tab: 'overview' })}
        onClose={() => setParams({})}
      />
    </div>
  )
}
