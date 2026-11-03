import { leagueApi, teamApi } from '@/api'
import { adaptLeague, adaptTeam, unwrapList } from '@/utils/adapters'

const TTL_MS = 5 * 60 * 1000

let teamsPromise = null
let teamsCachedAt = 0
let teamsMap = null

let leaguesPromise = null
let leaguesCachedAt = 0
let leaguesList = null

function fresh(at) {
  return at && Date.now() - at < TTL_MS
}

/** 球队全量缓存（列表页依赖 ID→展示信息） */
export async function getTeamMap(force = false) {
  if (!force && teamsMap && fresh(teamsCachedAt)) return teamsMap
  if (!force && teamsPromise) return teamsPromise

  teamsPromise = (async () => {
    const res = await teamApi.getAll()
    const raw = unwrapList(res, 'teams')
    const map = new Map()
    raw.forEach((t) => {
      const team = adaptTeam(t)
      map.set(team.id, team)
    })
    teamsMap = map
    teamsCachedAt = Date.now()
    teamsPromise = null
    return map
  })()

  try {
    return await teamsPromise
  } catch (e) {
    teamsPromise = null
    throw e
  }
}

/** 启用联赛缓存 */
export async function getActiveLeagues(force = false) {
  if (!force && leaguesList && fresh(leaguesCachedAt)) return leaguesList
  if (!force && leaguesPromise) return leaguesPromise

  leaguesPromise = (async () => {
    const res = await leagueApi.getActive()
    const raw = unwrapList(res, 'leagues')
    leaguesList = raw.map(adaptLeague)
    leaguesCachedAt = Date.now()
    leaguesPromise = null
    return leaguesList
  })()

  try {
    return await leaguesPromise
  } catch (e) {
    leaguesPromise = null
    throw e
  }
}

export function invalidateCatalogCache() {
  teamsMap = null
  teamsCachedAt = 0
  teamsPromise = null
  leaguesList = null
  leaguesCachedAt = 0
  leaguesPromise = null
}
