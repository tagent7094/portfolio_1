import { Fragment } from 'react'
import clsx from 'clsx'
import type { PostVariant, AgentVote } from '../../types/api'

interface Props {
  posts: PostVariant[]
  votes: Record<string, Record<string, AgentVote>>
  agentNames: Record<string, string>
}

function scoreColor(score: number): string {
  if (score >= 8) return 'bg-white/20 text-green-100'
  if (score >= 6) return 'bg-white/20 text-white'
  if (score >= 4) return 'bg-white/80 text-orange-100'
  return 'bg-white/10 text-red-100'
}

export default function VotingMatrix({ posts, votes, agentNames }: Props) {
  const agentIds = Object.keys(votes)

  if (agentIds.length === 0 || posts.length === 0) return null

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-800 bg-gray-900 p-4">
      <h3 className="mb-3 text-sm font-semibold text-gray-300">
        Audience Voting Matrix
      </h3>
      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: `140px repeat(${posts.length}, minmax(60px, 1fr))`,
        }}
      >
        {/* Header row */}
        <div className="text-xs font-medium text-gray-500 p-1">Agent</div>
        {posts.map((p) => (
          <div
            key={p.id}
            className="truncate text-xs font-medium text-gray-500 p-1 text-center"
          >
            {p.engine_name || p.engine_id}
          </div>
        ))}

        {/* Agent rows */}
        {agentIds.map((agentId) => (
          <Fragment key={agentId}>
            <div
              className="truncate text-xs text-gray-300 p-1 flex items-center"
            >
              {agentNames[agentId] || agentId}
            </div>
            {posts.map((post) => {
              const vote = votes[agentId]?.[post.id]
              return (
                <div
                  key={`${agentId}-${post.id}`}
                  className={clsx(
                    'rounded p-1 text-center text-xs font-semibold',
                    vote ? scoreColor(vote.score) : 'bg-gray-800 text-gray-600',
                  )}
                  title={vote?.feedback}
                >
                  {vote ? vote.score.toFixed(1) : '-'}
                </div>
              )
            })}
          </Fragment>
        ))}
      </div>
    </div>
  )
}
