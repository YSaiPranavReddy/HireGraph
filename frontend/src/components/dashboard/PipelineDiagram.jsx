import './PipelineDiagram.css'

// Ordered display nodes — fan-out group shown as one row
const NODES = [
  { id: 'jd_parser_node',         label: 'JD Parser',       icon: '🔍', group: null },
  { id: 'resume_screener_node',   label: 'Resume Screener', icon: '📄', group: 'parallel' },
  { id: 'bias_checker_node',      label: 'Bias Checker',    icon: '⚖️', group: 'parallel' },
  { id: 'team_gap_analyzer_node', label: 'Team Gap',        icon: '👥', group: 'parallel' },
  { id: 'ranker_node',            label: 'Ranker',          icon: '🏆', group: null },
  { id: 'critique_node',          label: 'Critique',        icon: '🧠', group: null },
  { id: 'outreach_drafter_node',  label: 'Outreach',        icon: '✉️', group: null },
]

// Which nodes should pulse "running" after a given node completes
const NEXT_RUNNING = {
  'jd_parser_node':         ['resume_screener_node', 'bias_checker_node', 'team_gap_analyzer_node'],
  'resume_screener_node':   [],   // ranker waits for ALL three — handled below
  'bias_checker_node':      [],
  'team_gap_analyzer_node': ['ranker_node'],
  'ranker_node':            ['critique_node'],
  'critique_node':          ['outreach_drafter_node'],
}

function nodeStatus(nodeId, doneSet, runningSet) {
  if (doneSet.has(nodeId))    return 'done'
  if (runningSet.has(nodeId)) return 'running'
  return 'idle'
}

export default function PipelineDiagram({ events }) {
  // Build done + running sets from event list
  const doneSet    = new Set(events.map(e => e.node))
  const runningSet = new Set()

  // Determine running nodes from the last completed node
  if (events.length > 0) {
    const lastNode = events[events.length - 1].node
    const nextNodes = NEXT_RUNNING[lastNode] || []
    nextNodes.forEach(n => { if (!doneSet.has(n)) runningSet.add(n) })

    // Special case: when all 3 parallel nodes done → ranker is next
    const parallelDone = ['resume_screener_node','bias_checker_node','team_gap_analyzer_node']
      .every(n => doneSet.has(n))
    if (parallelDone && !doneSet.has('ranker_node')) {
      runningSet.add('ranker_node')
      runningSet.delete('resume_screener_node')
      runningSet.delete('bias_checker_node')
      runningSet.delete('team_gap_analyzer_node')
    }
  } else if (events.length === 0) {
    // Pipeline just started — first node is running
    runningSet.add('jd_parser_node')
  }

  // Group parallel nodes into one row
  const rows = []
  let parallelRow = []
  for (const node of NODES) {
    if (node.group === 'parallel') {
      parallelRow.push(node)
    } else {
      if (parallelRow.length) {
        rows.push({ type: 'parallel', nodes: parallelRow })
        parallelRow = []
      }
      rows.push({ type: 'single', node })
    }
  }

  return (
    <div className="pipeline-diagram">
      {rows.map((row, ri) => (
        <div key={ri} className="diagram-row">
          {/* Connector line above (except first row) */}
          {ri > 0 && <div className="diagram-connector" />}

          {row.type === 'single' ? (
            <DiagramNode node={row.node} status={nodeStatus(row.node.id, doneSet, runningSet)}
              event={events.find(e => e.node === row.node.id)} />
          ) : (
            <div className="diagram-parallel">
              {row.nodes.map(n => (
                <DiagramNode key={n.id} node={n} status={nodeStatus(n.id, doneSet, runningSet)}
                  event={events.find(e => e.node === n.id)} />
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function DiagramNode({ node, status, event }) {
  return (
    <div className={`diagram-node diagram-node--${status}`}>
      <div className={`diagram-dot ${status === 'running' ? 'pulsing' : ''}`}>
        {status === 'done'    && <span className="dot-icon">✓</span>}
        {status === 'running' && <span className="dot-icon dot-spinner" />}
        {status === 'idle'    && <span className="dot-icon dot-idle">{node.icon}</span>}
      </div>
      <div className="diagram-label">
        <span className="diagram-name">{node.icon} {node.label}</span>
        {event?.summary && (
          <span className="diagram-summary">{event.summary}</span>
        )}
      </div>
    </div>
  )
}
