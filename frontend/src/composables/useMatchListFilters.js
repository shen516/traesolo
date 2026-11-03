import { ref, computed } from 'vue'
import { getCategoryLabel } from '@/utils/matchMeta'
import { useFollowsStore } from '@/stores/follows'
import { useUserStore } from '@/stores/user'

/**
 * 赛事列表共用的筛选 / 分页 / 联赛级联状态
 * @param {{ initialDate?: string, densityKey?: string }} opts
 */
export function useMatchListFilters(opts = {}) {
  const followsStore = useFollowsStore()
  const userStore = useUserStore()
  const followedOnly = ref(!userStore.isAdmin)
  const selectedCategory = ref('all')
  const selectedCountry = ref('all')
  const selectedLeague = ref('all')
  const selectedDate = ref(opts.initialDate ?? '')
  const searchKeyword = ref('')
  const predictFilter = ref('all')
  const filtersExpanded = ref(false)
  const cardDensity = ref(localStorage.getItem(opts.densityKey || 'matchCardDensity') || 'compact')

  const currentPage = ref(1)
  const pageSize = ref(20)
  const total = ref(0)
  const totalPages = ref(0)

  const leagues = ref([])
  const categories = ref(['international', 'domestic'])

  const allCountries = computed(() => {
    const set = new Set(leagues.value.map((l) => l.country).filter(Boolean))
    return Array.from(set).sort()
  })

  const filteredCountries = computed(() => {
    if (selectedCategory.value === 'all' || selectedCategory.value === 'international') {
      return allCountries.value
    }
    const cats = leagues.value.filter((l) => l.category === selectedCategory.value)
    const set = new Set(cats.map((l) => l.country).filter(Boolean))
    return Array.from(set).sort()
  })

  const filteredLeagues = computed(() => {
    let result = leagues.value
    if (followedOnly.value && followsStore.ids.length) {
      result = result.filter((l) => followsStore.queryIdSet.has(l.id))
    }
    if (selectedCategory.value !== 'all') {
      result = result.filter((l) => l.category === selectedCategory.value)
    }
    if (selectedCountry.value !== 'all') {
      result = result.filter((l) => l.country === selectedCountry.value)
    }
    return result
  })

  const skipFollowedQuery = computed(() => followedOnly.value && !followsStore.ids.length)

  const visiblePages = computed(() => {
    const pages = []
    const maxVisible = 5
    let start = Math.max(1, currentPage.value - Math.floor(maxVisible / 2))
    let end = Math.min(totalPages.value, start + maxVisible - 1)
    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1)
    }
    for (let i = start; i <= end; i++) pages.push(i)
    return pages
  })

  function applyPagination(matchesRes, fallbackLen) {
    if (matchesRes?.pagination) {
      total.value = matchesRes.pagination.total || 0
      totalPages.value = matchesRes.pagination.pages || 0
    } else {
      total.value = fallbackLen
      totalPages.value = 1
    }
  }

  function listQueryParams(extra = {}) {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      league_id: selectedLeague.value === 'all' ? undefined : selectedLeague.value,
      keyword: searchKeyword.value.trim() || undefined,
      view: cardDensity.value === 'compact' ? 'summary' : 'full',
      ...extra,
    }
    if (followedOnly.value) {
      params.league_ids = followsStore.queryIds.join(',')
    }
    return params
  }

  function getLeague(id) {
    return leagues.value.find((l) => l.id === id) || { name: '未知联赛', icon: '⚽', logo: '' }
  }

  return {
    followedOnly,
    skipFollowedQuery,
    selectedCategory,
    selectedCountry,
    selectedLeague,
    selectedDate,
    searchKeyword,
    predictFilter,
    filtersExpanded,
    cardDensity,
    currentPage,
    pageSize,
    total,
    totalPages,
    leagues,
    categories,
    filteredCountries,
    filteredLeagues,
    visiblePages,
    getCategoryLabel,
    getLeague,
    applyPagination,
    listQueryParams,
  }
}
