<template>
  <section class="admin-users-page">
    <header class="page-head">
      <div class="head-text">
        <h2 class="page-title">用户管理</h2>
        <p class="page-sub">查看全部注册用户的在线状态、作文批改记录与学情情况</p>
      </div>
      <button type="button" class="ui-btn" :disabled="usersLoading" @click="refreshAll">
        <Loader2 v-if="usersLoading" :size="14" class="spin" />
        <RefreshCw v-else :size="14" />
        <span>刷新</span>
      </button>
    </header>

    <div v-if="usersError" class="error-bar">
      <span class="error-text">{{ usersError }}</span>
      <button type="button" class="retry-btn" @click="refreshAll">重试</button>
    </div>

    <div class="admin-layout">
      <!-- 左栏：用户列表（本地过滤 + 管理员置顶 + 在线优先） -->
      <aside class="user-panel">
        <label class="search-box">
          <Search :size="14" class="search-icon" />
          <input v-model="keyword" type="text" class="search-input" placeholder="按账号搜索" />
        </label>

        <div v-if="usersLoading && !users.length" class="panel-state">
          <Loader2 :size="18" class="spin" />
          <span>正在加载用户…</span>
        </div>
        <div v-else-if="!filteredUsers.length" class="panel-state">
          <Users :size="18" />
          <span>{{ users.length ? '没有匹配的账号' : '暂无注册用户' }}</span>
        </div>
        <ul v-else class="user-list">
          <li v-for="u in filteredUsers" :key="u.account">
            <button
              type="button"
              class="user-row"
              :class="{ 'is-active': u.account === selectedAccount }"
              @click="selectUser(u.account)"
            >
              <span class="avatar">{{ initial(u.account) }}</span>
              <span class="user-main">
                <span class="user-line">
                  <span class="user-name">{{ u.account }}</span>
                  <span class="role-badge" :class="isAdmin(u) ? 'role-badge--admin' : 'role-badge--student'">
                    {{ roleText(u) }}
                  </span>
                </span>
                <span class="user-meta">
                  <span class="online-dot" :class="{ 'is-online': u.online === true }"></span>
                  <span :class="u.online ? 'online-text' : 'offline-text'">{{ u.online ? '在线' : '离线' }}</span>
                  <span class="meta-sep">·</span>
                  <span>最近活跃 {{ timeOrDash(u.last_active_at) }}</span>
                </span>
              </span>
            </button>
          </li>
        </ul>
      </aside>

      <!-- 右栏：选中用户的统计、学情与批改记录 -->
      <section class="detail-panel">
        <div v-if="!selectedAccount" class="panel-state panel-state--detail">
          <Users :size="20" />
          <span>请选择左侧用户查看批改记录与学情</span>
        </div>
        <div v-else-if="detailLoading && !reviews.length && !profile" class="panel-state panel-state--detail">
          <Loader2 :size="20" class="spin" />
          <span>正在加载用户详情…</span>
        </div>

        <template v-else>
          <div class="detail-head">
            <div class="detail-title">
              <span class="avatar avatar--lg">{{ initial(selectedAccount) }}</span>
              <div>
                <h3 class="detail-account">{{ selectedAccount }}</h3>
                <div class="detail-meta">
                  <span class="role-badge" :class="isAdmin(selectedUser) ? 'role-badge--admin' : 'role-badge--student'">
                    {{ roleText(selectedUser) }}
                  </span>
                  <span class="status-text">
                    <span class="online-dot" :class="{ 'is-online': selectedUser?.online === true }"></span>
                    {{ selectedUser?.online ? '在线' : '离线' }}
                  </span>
                  <span>最近活跃 {{ timeOrDash(selectedUser?.last_active_at) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-if="detailError" class="error-bar">
            <span class="error-text">{{ detailError }}</span>
            <button type="button" class="retry-btn" @click="loadDetail">重试</button>
          </div>

          <div class="stat-grid">
            <div class="stat-card">
              <span class="stat-label">批改篇数</span>
              <span class="stat-value">{{ reviewCount }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">已完成</span>
              <span class="stat-value">{{ doneCount }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">平均分</span>
              <span class="stat-value">{{ formatScore(avgScore) }}</span>
            </div>
            <div class="stat-card">
              <span class="stat-label">最近得分</span>
              <span class="stat-value">{{ formatScore(latestScore) }}</span>
            </div>
          </div>

          <!-- 详情接口失败时不展示「暂无数据」，避免把加载失败误读成真的没有记录 -->
          <template v-if="!detailError">
            <div class="card-block">
              <span class="block-title">学情摘要</span>
              <div v-if="!hasProfile" class="block-empty">该用户暂无可用于生成学情的已完成批改</div>
              <template v-else>
                <p v-if="profile?.trend" class="trend-line">
                  <template v-if="profile.trend.direction === '样本不足'">{{ profile.trend.note }}</template>
                  <template v-else>
                    最近 {{ (profile.trend.recent || []).length }} 次较此前<span class="trend-dir">{{ trendLabel }}</span>{{ trendDelta }}
                  </template>
                </p>

                <div v-if="orderedDims.length" class="dim-list">
                  <div v-for="dim in orderedDims" :key="dim.name" class="dim-row">
                    <span class="dim-name">{{ dim.name }}</span>
                    <div class="dim-bar"><div class="dim-bar-fill" :style="{ width: dimWidth(dim.rate) }"></div></div>
                    <span class="dim-meta">{{ dim.avg_score }}分 · {{ dim.n }}篇 · {{ dimPercent(dim.rate) }}%</span>
                  </div>
                </div>

                <p v-if="profile?.weak_dims?.length || profile?.strong_dims?.length" class="dim-tags">
                  <template v-if="profile?.strong_dims?.length">
                    <span class="tag ok">优势：{{ profile.strong_dims.join('、') }}</span>
                  </template>
                  <template v-if="profile?.weak_dims?.length">
                    <span class="tag warn">薄弱：{{ profile.weak_dims.join('、') }}</span>
                  </template>
                </p>

                <ul v-if="profile?.recurring_issues?.length" class="plain-list recurring-list">
                  <li v-for="(item, i) in profile.recurring_issues" :key="i">
                    {{ item.aspect }}（{{ item.count }} 篇提到）
                  </li>
                </ul>
              </template>
            </div>

            <div v-if="hasProfile && recentScores.length" class="card-block">
              <span class="block-title">近期篇章</span>
              <ul class="score-list">
                <li v-for="(s, i) in recentScores" :key="i">
                  <span class="score-date">{{ s.date || '—' }}</span>
                  <span class="score-title">《{{ s.title || '未命题' }}》</span>
                  <span class="score-score">{{ s.score }}分{{ s.rating ? ' · ' + s.rating : '' }}</span>
                </li>
              </ul>
            </div>

            <div class="card-block">
              <span class="block-title">批改记录</span>
              <div v-if="!reviews.length" class="block-empty">暂无批改记录</div>
              <div v-else class="table-wrap">
                <table class="review-table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>题目</th>
                      <th>年级 / 体裁</th>
                      <th>状态</th>
                      <th>分数 / 等级</th>
                      <th class="col-action">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in reviews" :key="r.id">
                      <td class="cell-time">{{ timeOrDash(r.created_at) }}</td>
                      <td class="cell-title" :title="r.input?.title || ''">{{ r.input?.title || '未命题' }}</td>
                      <td>{{ inputMeta(r.input) }}</td>
                      <td>
                        <span class="ui-badge" :class="statusClass(r.status)">{{ statusText(r.status) }}</span>
                      </td>
                      <td>{{ reviewScoreText(r) }}</td>
                      <td class="col-action">
                        <button type="button" class="link-btn" @click="openReview(r)">查看</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </template>
      </section>
    </div>

    <!-- 批改详情弹层 -->
    <div v-if="detailOpen" class="modal-overlay" @click.self="closeReview">
      <div class="modal" role="dialog" aria-modal="true" aria-label="批改详情">
        <header class="modal-head">
          <div class="modal-head-text">
            <h3 class="modal-title">{{ detail?.input?.title || '批改详情' }}</h3>
            <p class="modal-sub">
              <span>{{ selectedAccount }}</span>
              <span v-if="detail?.input?.grade"> · {{ detail.input.grade }}</span>
              <span v-if="detail?.input?.essay_type"> · {{ detail.input.essay_type }}</span>
              <span> · {{ timeOrDash(detail?.created_at) }}</span>
            </p>
          </div>
          <button type="button" class="ui-icon-btn" title="关闭" @click="closeReview">
            <X :size="16" />
          </button>
        </header>

        <div class="modal-body">
          <div v-if="detailFetching" class="panel-state">
            <Loader2 :size="18" class="spin" />
            <span>正在加载批改详情…</span>
          </div>

          <div v-else-if="detailFetchError" class="modal-error">
            <p class="error-text">{{ detailFetchError }}</p>
            <button type="button" class="ui-btn" @click="fetchDetail">重试</button>
          </div>

          <template v-else-if="detail">
            <div v-if="detail.status === 'failed'" class="status-box status-box--error">
              <strong>批改失败</strong>
              <p class="error-detail">{{ detail.error || '后端未返回具体错误信息' }}</p>
            </div>
            <div v-else-if="detail.status !== 'done'" class="status-box status-box--pending">
              <strong>批改进行中</strong>
              <p>当前状态：{{ statusText(detail.status) }}，完成后可查看完整评语与维度评分。</p>
            </div>

            <div v-if="detailPages.length" class="page-scroll">
              <figure v-for="(p, i) in detailPages" :key="p.file || i" class="page-thumb">
                <img :src="pageUrl(p.file)" :alt="`第${i + 1}页`" loading="lazy" />
                <figcaption>{{ i + 1 }}</figcaption>
              </figure>
            </div>
            <p v-else class="block-empty">该记录暂无可展示的页面图片</p>

            <div class="detail-score-row">
              <span class="detail-score">{{ formatScore(detailScore) }}</span>
              <span v-if="detailRating" class="ui-badge ui-badge--muted">{{ detailRating }}</span>
            </div>

            <div v-if="detailDims.length" class="detail-block">
              <span class="block-title">五维评分</span>
              <div v-for="dim in detailDims" :key="dim.name" class="dim-row">
                <span class="dim-name">{{ dim.name }}</span>
                <div class="dim-bar">
                  <div class="dim-bar-fill" :style="{ width: dimWidth(dimRatio(dim)) }"></div>
                </div>
                <span class="dim-meta">{{ dim.score ?? '—' }} / {{ dim.max_score ?? '—' }}</span>
              </div>
            </div>

            <div v-if="detail?.result?.overall_comment" class="detail-block">
              <span class="block-title">总评</span>
              <p class="comment-text">{{ detail.result.overall_comment }}</p>
            </div>

            <div v-if="improvements.length" class="detail-block">
              <span class="block-title">改进建议</span>
              <ul class="plain-list">
                <li v-for="(tip, i) in improvements" :key="i">{{ tip }}</li>
              </ul>
            </div>
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
/**
 * 用户管理（管理员）
 * 展示全部注册用户的在线状态、批改记录与学情；数据全部来自 /api/admin/users* 接口，
 * 不含任何模拟数据，接口异常时降级为空列表并给出可重试的提示。
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { Loader2, RefreshCw, Search, Users, X } from 'lucide-vue-next';
import request from '../../api/request.js';
import { reviewPageUrl } from '../../utils/reviewUrl.js';
import { formatRecordTime } from '../../utils/format.js';

// 请求头由 request 拦截器统一注入，这里声明 username 只是为了与主界面接入约定保持一致
defineProps({ username: { type: String, default: '' } });

const REFRESH_INTERVAL = 30000;

const users = ref([]);
const usersLoading = ref(false);
const usersError = ref('');
const keyword = ref('');
const selectedAccount = ref('');

const reviews = ref([]);
const profile = ref(null);
const detailLoading = ref(false);
const detailError = ref('');

const detailOpen = ref(false);
const detailId = ref(null);
const detail = ref(null);
const detailFetching = ref(false);
const detailFetchError = ref('');

const apiError = (e, fallback) => e?.response?.data?.message || e?.response?.data?.error || e?.message || fallback;

// 管理员账号置顶并单独标识；其余账号一律按学生展示
const isAdmin = (user) => user?.role === 'admin' || user?.role_label === '管理员';

const roleText = (user) => (isAdmin(user) ? '管理员' : (user?.role_label || '学生'));

const initial = (account) => (account ? String(account).trim().charAt(0).toUpperCase() : '?');

const timeOrDash = (iso) => formatRecordTime(iso) || '—';

const formatScore = (v) => (v === null || v === undefined || v === '' ? '—' : `${v}分`);

const dimPercent = (rate) => {
  const n = Number(rate);
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
};
const dimWidth = (rate) => {
  const n = Number(rate);
  return `${Number.isFinite(n) ? Math.max(0, Math.min(100, n * 100)) : 0}%`;
};

const inputMeta = (input) => {
  const parts = [input?.grade, input?.essay_type].filter(Boolean);
  return parts.length ? parts.join(' · ') : '—';
};

const reviewScoreText = (r) => {
  if (!r) return '—';
  const hasScore = r.score !== null && r.score !== undefined && r.score !== '';
  if (hasScore) return r.rating ? `${r.score}分 · ${r.rating}` : `${r.score}分`;
  return r.rating || '—';
};

const statusText = (status) => ({
  queued: '排队中',
  recognizing: '识别中',
  grading: '批改中',
  done: '已完成',
  failed: '失败'
}[status] || status || '未知');

const statusClass = (status) => ({
  queued: 'ui-badge--pending',
  recognizing: 'ui-badge--running',
  grading: 'ui-badge--running',
  done: 'ui-badge--done',
  failed: 'ui-badge--failed'
}[status] || 'ui-badge--muted');

/** 管理员置顶；其余维持后端返回顺序（Array.sort 在现代引擎中稳定） */
const sortedUsers = computed(() => {
  return [...users.value].sort((a, b) => (isAdmin(b) ? 1 : 0) - (isAdmin(a) ? 1 : 0));
});

const filteredUsers = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  if (!kw) return sortedUsers.value;
  return sortedUsers.value.filter((u) => String(u?.account || '').toLowerCase().includes(kw));
});

const selectedUser = computed(() => users.value.find((u) => u?.account === selectedAccount.value) || null);

const reviewCount = computed(() => selectedUser.value?.review_count ?? profile.value?.n_reviews ?? reviews.value.length);

const doneCount = computed(() => {
  const n = selectedUser.value?.done_count;
  if (n !== null && n !== undefined) return n;
  return reviews.value.filter((r) => r?.status === 'done').length;
});

const avgScore = computed(() => selectedUser.value?.avg_score ?? profile.value?.avg_score ?? null);
const latestScore = computed(() => selectedUser.value?.latest_score ?? profile.value?.latest_score ?? null);

const hasProfile = computed(() => profile.value?.has_data === true);

/**
 * 维度得分率。
 *
 * 必须摊平成带 name 字段的对象数组：v-for 在数组上会把第二个变量当作下标，
 * 直接遍历 Object.entries() 的二元组会导致维度名显示成数字、数值全是 NaN。
 * 排序按得分率由低到高，最该补的维度排在最上面（与学情报告口径一致）。
 */
const orderedDims = computed(() => {
  const map = profile.value?.dim_rates;
  if (!map || typeof map !== 'object') return [];
  return Object.entries(map)
    .map(([name, info]) => ({ name, ...(info || {}) }))
    .sort((a, b) => (Number(a.rate) || 0) - (Number(b.rate) || 0));
});

const recentScores = computed(() => {
  const list = profile.value?.scores;
  return Array.isArray(list) ? list.slice().reverse() : [];
});

const trendLabel = computed(() => {
  const dir = profile.value?.trend?.direction;
  return dir === '上升' ? '成绩有所上升' : dir === '下降' ? '成绩有所下滑' : '保持平稳';
});

const trendDelta = computed(() => {
  const t = profile.value?.trend;
  if (!t || t.direction === '样本不足' || t.delta === null || t.delta === undefined) return '';
  return `（${Math.abs(t.delta)}分）`;
});

const detailPages = computed(() => {
  const pages = detail.value?.pages;
  return Array.isArray(pages) ? pages.filter((p) => p && p.file) : [];
});

const detailDims = computed(() => {
  const dims = detail.value?.result?.dimensions;
  return Array.isArray(dims) ? dims.filter((d) => d && typeof d === 'object') : [];
});

const detailScore = computed(() => detail.value?.result?.score ?? detail.value?.score ?? null);
const detailRating = computed(() => detail.value?.result?.rating || detail.value?.rating || '');

const improvements = computed(() => {
  const list = detail.value?.result?.improvements;
  return Array.isArray(list) ? list.filter((s) => typeof s === 'string' && s.trim()).map((s) => s.trim()) : [];
});

/** 维度条宽度：兼容 max_score 缺失或为 0 的情况，避免出现 NaN% */
const dimRatio = (dim) => {
  const max = Number(dim?.max_score) || 0;
  const score = Number(dim?.score) || 0;
  return max > 0 ? score / max : 0;
};

// <img> 无法携带请求头，必须把当前账号拼进 owner 参数，否则后端判为 anonymous 而 404
const pageUrl = (file) => reviewPageUrl(detailId.value, file, selectedAccount.value);

/** 拉取用户列表；silent 用于 30 秒轮询，不闪加载态 */
const loadUsers = async ({ silent = false, forceDetail = false } = {}) => {
  if (!silent) usersLoading.value = true;
  try {
    const res = await request.get('/api/admin/users');
    const payload = res?.data;
    if (payload?.success && Array.isArray(payload.data)) {
      users.value = payload.data;
      usersError.value = '';
    } else {
      usersError.value = payload?.message || payload?.error || '用户列表返回结构异常';
    }
  } catch (e) {
    usersError.value = apiError(e, '加载用户列表失败');
  } finally {
    if (!silent) usersLoading.value = false;
  }

  const changed = syncSelection();
  if (!changed && forceDetail && selectedAccount.value) await loadDetail();
};

/** 选中项仍存在时保持不变；否则优先在线用户，其次列表第一项 */
const syncSelection = () => {
  if (users.value.some((u) => u?.account === selectedAccount.value)) return false;
  const next = sortedUsers.value.find((u) => u?.online === true) || sortedUsers.value[0];
  if (!next) {
    selectedAccount.value = '';
    reviews.value = [];
    profile.value = null;
    detailError.value = '';
    return false;
  }
  selectUser(next.account);
  return true;
};

const selectUser = (account) => {
  if (!account || account === selectedAccount.value) return;
  selectedAccount.value = account;
  reviews.value = [];
  profile.value = null;
  detailError.value = '';
  closeReview();
  loadDetail();
};

const loadDetail = async () => {
  const account = selectedAccount.value;
  if (!account) return;
  detailLoading.value = true;
  detailError.value = '';
  try {
    // 两个接口互不依赖：用 allSettled，任一失败仍能展示另一部分数据
    const [reviewsRes, profileRes] = await Promise.allSettled([
      request.get(`/api/admin/users/${encodeURIComponent(account)}/reviews`),
      request.get(`/api/admin/users/${encodeURIComponent(account)}/profile`)
    ]);

    // 期间切换到别的用户则丢弃旧响应，防止串号
    if (account !== selectedAccount.value) return;

    const messages = [];

    if (reviewsRes.status === 'fulfilled') {
      const payload = reviewsRes.value?.data;
      if (payload?.success && Array.isArray(payload.data)) {
        reviews.value = payload.data;
      } else {
        reviews.value = [];
        messages.push(payload?.message || payload?.error || '批改记录返回结构异常');
      }
    } else {
      reviews.value = [];
      messages.push(apiError(reviewsRes.reason, '加载批改记录失败'));
    }

    if (profileRes.status === 'fulfilled') {
      const payload = profileRes.value?.data;
      if (payload?.success && payload.data && typeof payload.data === 'object') {
        profile.value = payload.data;
      } else {
        profile.value = { has_data: false };
        messages.push(payload?.message || payload?.error || '学情数据返回结构异常');
      }
    } else {
      profile.value = { has_data: false };
      messages.push(apiError(profileRes.reason, '加载学情失败'));
    }

    detailError.value = [...new Set(messages)].join('；');
  } finally {
    if (account === selectedAccount.value) detailLoading.value = false;
  }
};

const openReview = async (review) => {
  if (!review?.id) return;
  detailId.value = review.id;
  detail.value = null;
  detailFetchError.value = '';
  detailOpen.value = true;
  await fetchDetail();
};

const fetchDetail = async () => {
  const account = selectedAccount.value;
  const id = detailId.value;
  if (!account || !id) {
    detailFetchError.value = '该记录缺少编号，无法查看详情';
    return;
  }
  detailFetching.value = true;
  detailFetchError.value = '';
  try {
    const res = await request.get(`/api/admin/users/${encodeURIComponent(account)}/reviews/${encodeURIComponent(id)}`);
    if (detailId.value !== id || !detailOpen.value) return; // 已关闭或切换了记录
    const payload = res?.data;
    if (payload?.success && payload.data && typeof payload.data === 'object') {
      detail.value = payload.data;
    } else {
      detailFetchError.value = payload?.message || payload?.error || '批改详情返回结构异常';
    }
  } catch (e) {
    if (detailId.value !== id || !detailOpen.value) return;
    detailFetchError.value = apiError(e, '加载批改详情失败');
  } finally {
    if (detailId.value === id) detailFetching.value = false;
  }
};

const closeReview = () => {
  detailOpen.value = false;
  detailId.value = null;
  detail.value = null;
  detailFetchError.value = '';
  detailFetching.value = false;
};

const refreshAll = async () => {
  await loadUsers({ forceDetail: true });
};

const onKeydown = (e) => {
  if (e.key === 'Escape' && detailOpen.value) closeReview();
};

let timer = null;

onMounted(() => {
  loadUsers();
  // 在线状态依赖后端心跳，定时轮询保持展示新鲜；只刷列表，不动当前详情
  timer = setInterval(() => loadUsers({ silent: true }), REFRESH_INTERVAL);
  window.addEventListener('keydown', onKeydown);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
  window.removeEventListener('keydown', onKeydown);
});
</script>

<style scoped>
.admin-users-page { max-width: 1080px; margin: 0 auto; padding: 24px 28px 48px; overflow-y: auto; height: 100%; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.page-title { font-size: var(--fs-xl); font-weight: 700; color: var(--c-text); margin-bottom: 4px; }
.page-sub { font-size: var(--fs-sm); color: var(--c-text-secondary); margin: 0; }

.error-bar { display: flex; align-items: center; gap: 12px; padding: 8px 12px; margin-bottom: 12px; font-size: var(--fs-sm); color: var(--c-error); background: var(--c-error-soft); border: 1px solid var(--c-border); border-radius: var(--r-md); }
.error-text { flex: 1; min-width: 0; word-break: break-word; }
.retry-btn { flex-shrink: 0; padding: 0; font-family: inherit; font-size: var(--fs-sm); color: inherit; background: none; border: none; text-decoration: underline; cursor: pointer; }

.admin-layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: start; }

/* ---- 左栏：用户列表 ---- */
.user-panel { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); padding: 12px; min-width: 0; }
.search-box { display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px; margin-bottom: 10px; background: var(--c-bg-muted); border: 1px solid var(--c-border); border-radius: var(--r-md); }
.search-icon { flex-shrink: 0; color: var(--c-text-muted); }
.search-input { flex: 1; min-width: 0; font-family: inherit; font-size: var(--fs-sm); color: var(--c-text); background: transparent; border: none; outline: none; }

.user-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.user-row { display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; text-align: left; font-family: inherit; background: transparent; border: 1px solid transparent; border-radius: var(--r-md); cursor: pointer; transition: background-color .15s, border-color .15s; }
.user-row:hover { background: var(--c-bg-muted); }
.user-row.is-active { background: var(--c-primary-soft); border-color: rgba(15, 119, 255, .22); }

.avatar { display: flex; align-items: center; justify-content: center; flex-shrink: 0; width: 32px; height: 32px; font-size: var(--fs-sm); font-weight: 600; color: #fff; background: var(--c-primary); border-radius: 50%; }
.avatar--lg { width: 40px; height: 40px; font-size: var(--fs-md); }

.user-main { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.user-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
.user-name { overflow: hidden; font-size: var(--fs-md); font-weight: 600; color: var(--c-text); text-overflow: ellipsis; white-space: nowrap; }
.user-meta { display: flex; align-items: center; gap: 5px; overflow: hidden; font-size: var(--fs-xs); color: var(--c-text-muted); white-space: nowrap; text-overflow: ellipsis; }
.meta-sep { color: var(--c-border-strong); }

.role-badge { flex-shrink: 0; padding: 1px 7px; font-size: 11px; font-weight: 600; border-radius: var(--r-pill); }
.role-badge--admin { color: var(--c-primary); background: var(--c-primary-soft); }
.role-badge--student { color: var(--c-text-secondary); background: var(--c-bg-muted); }

.online-dot { flex-shrink: 0; width: 7px; height: 7px; background: var(--c-text-muted); border-radius: 50%; }
.online-dot.is-online { background: var(--c-ok); box-shadow: 0 0 0 3px var(--c-ok-soft); }
.online-text { color: var(--c-ok); }
.offline-text { color: var(--c-text-muted); }

.panel-state { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 36px 16px; font-size: var(--fs-sm); color: var(--c-text-muted); text-align: center; }
.panel-state--detail { padding: 80px 16px; }

/* ---- 右栏：用户详情 ---- */
.detail-panel { min-width: 0; }
.detail-head { margin-bottom: 14px; }
.detail-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
.detail-account { margin: 0 0 5px; font-size: var(--fs-lg); font-weight: 700; color: var(--c-text); }
.detail-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; font-size: var(--fs-xs); color: var(--c-text-muted); }
.status-text { display: inline-flex; align-items: center; gap: 4px; }

.stat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { display: flex; flex-direction: column; gap: 6px; padding: 16px 14px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); }
.stat-label { font-size: var(--fs-xs); color: var(--c-text-secondary); }
.stat-value { font-size: var(--fs-lg); font-weight: 700; color: var(--c-primary); }

.card-block { margin-bottom: 14px; padding: 16px 18px; background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--r-lg); }
.block-title { display: block; margin-bottom: 10px; font-size: var(--fs-md); font-weight: 600; color: var(--c-text); }
.block-empty { padding: 6px 0; font-size: var(--fs-sm); color: var(--c-text-muted); }

.trend-line { margin: 0; font-size: var(--fs-sm); color: var(--c-text); }
.trend-dir { margin: 0 2px; font-weight: 600; color: var(--c-primary); }

.dim-row { display: grid; grid-template-columns: 56px 1fr 118px; align-items: center; gap: 12px; margin-bottom: 8px; }
.dim-name { overflow: hidden; font-size: var(--fs-xs); color: var(--c-text-secondary); white-space: nowrap; text-overflow: ellipsis; }
.dim-bar { height: 10px; overflow: hidden; background: var(--c-bg-muted); border-radius: var(--r-pill); }
.dim-bar-fill { height: 100%; background: var(--c-primary); border-radius: var(--r-pill); }
.dim-meta { font-size: 12px; color: var(--c-text-muted); text-align: right; }

.dim-tags { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 0; }
.tag { padding: 3px 10px; font-size: var(--fs-xs); border-radius: var(--r-pill); }
.tag.ok { color: var(--c-ok); background: var(--c-ok-soft); }
.tag.warn { color: var(--c-warn); background: var(--c-warn-soft); }

.plain-list { margin: 0; padding-left: 18px; font-size: var(--fs-sm); color: var(--c-text); }
.recurring-list { margin-top: 10px; }

.score-list { list-style: none; margin: 0; padding: 0; font-size: var(--fs-sm); }
.score-list li { display: flex; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--c-border); }
.score-list li:last-child { border-bottom: none; }
.score-date { flex-shrink: 0; color: var(--c-text-muted); }
.score-title { flex: 1; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.score-score { flex-shrink: 0; font-weight: 600; color: var(--c-primary); }

/* ---- 批改记录表 ---- */
.table-wrap { overflow-x: auto; }
.review-table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
.review-table th { padding: 8px 10px; font-size: var(--fs-xs); font-weight: 600; color: var(--c-text-secondary); text-align: left; white-space: nowrap; background: var(--c-bg-subtle); border-bottom: 1px solid var(--c-border); }
.review-table td { padding: 9px 10px; color: var(--c-text); vertical-align: middle; border-bottom: 1px solid var(--c-border); }
.review-table tbody tr:last-child td { border-bottom: none; }
.review-table tbody tr:hover { background: var(--c-bg-subtle); }
.cell-time { white-space: nowrap; color: var(--c-text-muted); }
.cell-title { max-width: 220px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.col-action { width: 60px; text-align: right; }
.link-btn { padding: 0; font-family: inherit; font-size: var(--fs-sm); color: var(--c-primary); background: none; border: none; cursor: pointer; }
.link-btn:hover { text-decoration: underline; }

/* ---- 批改详情弹层 ---- */
.modal-overlay { position: fixed; inset: 0; z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 24px; background: rgba(9, 17, 53, .38); }
.modal { display: flex; flex-direction: column; width: min(760px, 100%); max-height: calc(100vh - 48px); overflow: hidden; background: var(--c-surface); border-radius: var(--r-lg); box-shadow: var(--shadow-3); }
.modal-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 16px 20px; border-bottom: 1px solid var(--c-border); }
.modal-head-text { min-width: 0; }
.modal-title { margin: 0 0 4px; font-size: var(--fs-lg); font-weight: 700; color: var(--c-text); }
.modal-sub { margin: 0; font-size: var(--fs-xs); color: var(--c-text-muted); }
.modal-body { padding: 16px 20px 22px; overflow-y: auto; }

.modal-error { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; font-size: var(--fs-sm); color: var(--c-error); }

.status-box { padding: 10px 14px; margin-bottom: 14px; font-size: var(--fs-sm); border-radius: var(--r-md); }
.status-box strong { display: block; margin-bottom: 4px; }
.status-box p { margin: 0; }
.status-box--error { color: var(--c-error); background: var(--c-error-soft); }
.status-box--pending { color: var(--c-warn); background: var(--c-warn-soft); }
.error-detail { white-space: pre-wrap; word-break: break-word; }

.page-scroll { display: flex; gap: 10px; margin-bottom: 14px; padding-bottom: 6px; overflow-x: auto; }
.page-thumb { position: relative; flex: 0 0 auto; width: 132px; margin: 0; overflow: hidden; background: var(--c-bg-muted); border: 1px solid var(--c-border); border-radius: var(--r-sm); }
.page-thumb img { display: block; width: 100%; height: 172px; object-fit: cover; object-position: top; }
.page-thumb figcaption { position: absolute; right: 6px; bottom: 6px; padding: 0 6px; font-size: 11px; color: #fff; background: rgba(9, 17, 53, .55); border-radius: var(--r-pill); }

.detail-score-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.detail-score { font-size: 24px; font-weight: 700; color: var(--c-primary); }
.detail-block { margin-bottom: 16px; }
.detail-block:last-child { margin-bottom: 0; }
.comment-text { margin: 0; font-size: var(--fs-sm); line-height: 1.75; color: var(--c-text); white-space: pre-wrap; }

.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .admin-layout { grid-template-columns: 1fr; }
  .user-list { max-height: 320px; overflow-y: auto; }
  .stat-grid { grid-template-columns: repeat(2, 1fr); }
  .dim-row { grid-template-columns: 48px 1fr 104px; }
  .modal-overlay { padding: 12px; }
}
</style>
