import os
# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, infer_types=True
"""A* 搜索核的 C 实现（等价候选，代际戳版）。

语义逐条照抄 `ec_layout.astar`。调用方负责按 astar 的规则算好 `pref`，并预建位图。

# 为什么有代际戳

第一版每次调用 malloc 608k doubles + 608k longs 并逐个初始化，实测**比 Python 慢 8 倍**：
本板 143 次检索里中位数只有 16 ms，固定开销完全主导。
现在缓冲区跨调用复用，`gen` 判断"本轮是否访问过"，**零初始化**。
"""
from cpython.bytes cimport PyBytes_AS_STRING, PyBytes_GET_SIZE
from libc.stdlib cimport calloc, free, malloc, realloc

DEF_INF = 1e18
DEF_EPS = 1e-9
DEF_DIRTY = 400.0

cdef int MOVES[8][2]
cdef double MOVE_COST[8]
MOVES[0][0] = 1;   MOVES[0][1] = 0;   MOVE_COST[0] = 1.0
MOVES[1][0] = -1;  MOVES[1][1] = 0;   MOVE_COST[1] = 1.0
MOVES[2][0] = 0;   MOVES[2][1] = 1;   MOVE_COST[2] = 1.0
MOVES[3][0] = 0;   MOVES[3][1] = -1;  MOVE_COST[3] = 1.0
MOVES[4][0] = 1;   MOVES[4][1] = 1;   MOVE_COST[4] = 1.414
MOVES[5][0] = 1;   MOVES[5][1] = -1;  MOVE_COST[5] = 1.414
MOVES[6][0] = -1;  MOVES[6][1] = 1;   MOVE_COST[6] = 1.414
MOVES[7][0] = -1;  MOVES[7][1] = -1;  MOVE_COST[7] = 1.414
cdef int NMOVES = 8


cdef class _Heap:
    cdef double* f
    cdef double* g
    cdef long* idx
    cdef long n
    cdef long cap

    def __cinit__(self):
        self.cap = 8192
        self.n = 0
        self.f = <double*>malloc(self.cap * sizeof(double))
        self.g = <double*>malloc(self.cap * sizeof(double))
        self.idx = <long*>malloc(self.cap * sizeof(long))

    def __dealloc__(self):
        if self.f != NULL:
            free(self.f)
        if self.g != NULL:
            free(self.g)
        if self.idx != NULL:
            free(self.idx)

    cdef void reset(self) noexcept:
        self.n = 0

    cdef void _grow(self):
        cdef long nc = self.cap * 2
        self.f = <double*>realloc(self.f, nc * sizeof(double))
        self.g = <double*>realloc(self.g, nc * sizeof(double))
        self.idx = <long*>realloc(self.idx, nc * sizeof(long))
        self.cap = nc

    cdef int _less(self, long a, long b) noexcept:
        if self.f[a] < self.f[b]:
            return 1
        if self.f[a] > self.f[b]:
            return 0
        if self.g[a] < self.g[b]:
            return 1
        if self.g[a] > self.g[b]:
            return 0
        return 1 if self.idx[a] < self.idx[b] else 0

    cdef void _swap(self, long a, long b) noexcept:
        cdef double tf = self.f[a]
        cdef double tg = self.g[a]
        cdef long ti = self.idx[a]
        self.f[a] = self.f[b]
        self.g[a] = self.g[b]
        self.idx[a] = self.idx[b]
        self.f[b] = tf
        self.g[b] = tg
        self.idx[b] = ti

    cdef void push(self, double fv, double gv, long i):
        cdef long c, p
        if self.n >= self.cap:
            self._grow()
        c = self.n
        self.n = c + 1
        self.f[c] = fv
        self.g[c] = gv
        self.idx[c] = i
        while c > 0:
            p = (c - 1) >> 1
            if not self._less(c, p):
                break
            self._swap(c, p)
            c = p

    cdef int pop(self, double* fv, double* gv, long* i) noexcept:
        cdef long c, l, r, m
        if self.n == 0:
            return 0
        fv[0] = self.f[0]
        gv[0] = self.g[0]
        i[0] = self.idx[0]
        self.n -= 1
        if self.n == 0:
            return 1
        self.f[0] = self.f[self.n]
        self.g[0] = self.g[self.n]
        self.idx[0] = self.idx[self.n]
        c = 0
        while True:
            l = 2 * c + 1
            if l >= self.n:
                break
            r = l + 1
            m = l
            if r < self.n and self._less(r, l):
                m = r
            if not self._less(m, c):
                break
            self._swap(c, m)
            c = m
        return 1


# ── 跨调用复用（代际戳）──
# ── 缓冲后端：稠密 / 分块 ──────────────────────────────────────────────
#
# 小图走稠密（与之前逐位相同）；大图走页表，只分配真正被触碰的页。
# 搜索逻辑只通过下面的 inline 访问器读写，不感知模式。
#
# 页大小 2^_page_bits 个节点；页表项数 = ceil(nodes / 2^_page_bits)。
# 读未分配页返回"没访问过"的哨兵（best→+inf，gen→-1），**读不分配**。
#
# **默认启用分块**（阈值 8,000,000 节点）。实测它的代价是慢（同机 iters=1）：
#     x4   1,880 → 1,787 MB（省 5%）   42.9 → 46.6 s（慢 9%）
#     x8   7,027 → 6,851 MB（省 2.5%） 143.5 → 174.4 s（慢 20%）
# 原因：一次 route 的 143 次检索并集会碰到大部分页，没有稀疏性可利用，
# 只多了一层间接寻址。目标要求"超过阈值走分块"，所以它默认生效，
# 代价照实记在这里。两条路径产物已验证逐字节相同。
# 想要旧行为（全稠密、更快）：EASYCIRQ_ASTAR_DENSE_LIMIT=999999999999。
cdef bint _paged = 0
cdef long _page_bits = 12
cdef double** _best_pages = NULL
cdef long** _best_gen_pages = NULL
cdef long** _came_pages = NULL
cdef long** _came_gen_pages = NULL
cdef long _npages = 0

cdef double* _best = NULL
cdef long* _best_gen = NULL
cdef long* _came = NULL
cdef long* _came_gen = NULL
cdef long _buf_n = 0
cdef long _gen = 0
cdef _Heap _heap = None

# 代价图是稀疏的（这块板最多几百格），用持久数组 + 触碰列表：
# 调用时写进去，返回前清零，避免每次分配 L*W*H 个 double。
cdef double* _cost = NULL
cdef long* _cost_touched = NULL
cdef long _cost_cap = 0
cdef long _cost_n = 0


cdef void _cost_clear() noexcept:
    global _cost_n
    cdef long i
    for i in range(_cost_n):
        _cost[_cost_touched[i]] = 0.0
    _cost_n = 0


cdef int _cost_ensure(long n) except -1:
    global _cost, _cost_touched, _cost_cap
    if _cost != NULL and n <= _cost_cap:
        return 1
    if _cost != NULL:
        free(_cost)
        free(_cost_touched)
        _cost = NULL
        _cost_touched = NULL
        _cost_cap = 0
    _cost = <double*>malloc(n * sizeof(double))
    _cost_touched = <long*>malloc(n * sizeof(long))
    if _cost == NULL or _cost_touched == NULL:
        raise MemoryError("astar_c: cost buffer")
    for i in range(n):
        _cost[i] = 0.0
    _cost_cap = n
    _cost_n = 0
    return 1


cdef void _cost_add(long idx, double v) noexcept:
    global _cost_n
    _cost[idx] = v
    _cost_touched[_cost_n] = idx
    _cost_n += 1



cdef inline long _pagemask() noexcept:
    return (<long>1 << _page_bits) - 1


cdef int _pg_new_d(double*** tbl, long p) except -1:
    cdef double* pg = <double*>calloc(<size_t>(<long>1 << _page_bits), sizeof(double))
    if pg == NULL:
        raise MemoryError("astar_c: page allocation failed")
    tbl[0][p] = pg
    return 1


cdef int _pg_new_l(long*** tbl, long p) except -1:
    cdef long* pg = <long*>calloc(<size_t>(<long>1 << _page_bits), sizeof(long))
    if pg == NULL:
        raise MemoryError("astar_c: page allocation failed")
    tbl[0][p] = pg
    return 1


cdef inline double _bget(long i) noexcept:
    cdef long p
    if not _paged:
        return _best[i]
    p = i >> _page_bits
    if _best_pages[p] == NULL:
        return DEF_INF
    return _best_pages[p][i & _pagemask()]


cdef inline int _bset(long i, double v) except -1:
    cdef long p
    if not _paged:
        _best[i] = v
        return 1
    p = i >> _page_bits
    if _best_pages[p] == NULL:
        _pg_new_d(&_best_pages, p)
    _best_pages[p][i & _pagemask()] = v
    return 1


cdef inline long _bgen(long i) noexcept:
    cdef long p
    if not _paged:
        return _best_gen[i]
    p = i >> _page_bits
    if _best_gen_pages[p] == NULL:
        return -1
    return _best_gen_pages[p][i & _pagemask()]


cdef inline int _bsetgen(long i, long v) except -1:
    cdef long p
    if not _paged:
        _best_gen[i] = v
        return 1
    p = i >> _page_bits
    if _best_gen_pages[p] == NULL:
        _pg_new_l(&_best_gen_pages, p)
    _best_gen_pages[p][i & _pagemask()] = v
    return 1


cdef inline long _cget(long i) noexcept:
    cdef long p
    if not _paged:
        return _came[i]
    p = i >> _page_bits
    if _came_pages[p] == NULL:
        return -1
    return _came_pages[p][i & _pagemask()]


cdef inline int _cset(long i, long v) except -1:
    cdef long p
    if not _paged:
        _came[i] = v
        return 1
    p = i >> _page_bits
    if _came_pages[p] == NULL:
        _pg_new_l(&_came_pages, p)
    _came_pages[p][i & _pagemask()] = v
    return 1


cdef inline long _cgen(long i) noexcept:
    cdef long p
    if not _paged:
        return _came_gen[i]
    p = i >> _page_bits
    if _came_gen_pages[p] == NULL:
        return -1
    return _came_gen_pages[p][i & _pagemask()]


cdef inline int _csetgen(long i, long v) except -1:
    cdef long p
    if not _paged:
        _came_gen[i] = v
        return 1
    p = i >> _page_bits
    if _came_gen_pages[p] == NULL:
        _pg_new_l(&_came_gen_pages, p)
    _came_gen_pages[p][i & _pagemask()] = v
    return 1


cdef void _pages_free() noexcept:
    global _best_pages, _best_gen_pages, _came_pages, _came_gen_pages, _npages
    cdef long p
    if _best_pages != NULL:
        for p in range(_npages):
            if _best_pages[p] != NULL:
                free(_best_pages[p])
        free(_best_pages)
        _best_pages = NULL
    if _best_gen_pages != NULL:
        for p in range(_npages):
            if _best_gen_pages[p] != NULL:
                free(_best_gen_pages[p])
        free(_best_gen_pages)
        _best_gen_pages = NULL
    if _came_pages != NULL:
        for p in range(_npages):
            if _came_pages[p] != NULL:
                free(_came_pages[p])
        free(_came_pages)
        _came_pages = NULL
    if _came_gen_pages != NULL:
        for p in range(_npages):
            if _came_gen_pages[p] != NULL:
                free(_came_gen_pages[p])
        free(_came_gen_pages)
        _came_gen_pages = NULL
    _npages = 0


cdef long _dense_limit() noexcept:
    """超过这个节点数就走分块。可用 EASYCIRQ_ASTAR_DENSE_LIMIT 覆盖（测试用）。"""
    # 默认 8,000,000 节点：**超过就真的走分块**。
    #
    # 实测分块是慢的（x8 慢 20%），但目标要求"超过阈值走稀疏/分块"，
    # 所以它必须是默认行为，而不是藏在环境变量后面——否则交付的仍然
    # 是无条件稠密分配，「存了」不等于「生效了」。
    #
    # 想要旧行为（全稠密、更快）：EASYCIRQ_ASTAR_DENSE_LIMIT=very-large
    cdef bytes raw = os.environ.get("EASYCIRQ_ASTAR_DENSE_LIMIT", "").encode()
    cdef long v
    if raw == b"":
        return 8000000
    try:
        v = int(raw)
    except Exception:
        return 8000000
    return v if v >= 0 else 8000000


cdef int _ensure(long n) except -1:
    global _best, _best_gen, _came, _came_gen, _buf_n, _gen
    global _paged, _npages, _best_pages, _best_gen_pages
    global _came_pages, _came_gen_pages
    if _best != NULL and n <= _buf_n:
        return 1
    if _best != NULL:
        free(_best)
        free(_best_gen)
        free(_came)
        free(_came_gen)
        _best = NULL
        _best_gen = NULL
        _came = NULL
        _came_gen = NULL
        _buf_n = 0
    if _paged:
        _pages_free()

    # 阈值：小图逐位沿用稠密路径，大图改走页表按需分配。
    _paged = 1 if n > _dense_limit() else 0

    if _paged:
        _npages = ((n - 1) >> _page_bits) + 1
        _best_pages = <double**>calloc(<size_t>_npages, sizeof(void*))
        _best_gen_pages = <long**>calloc(<size_t>_npages, sizeof(void*))
        _came_pages = <long**>calloc(<size_t>_npages, sizeof(void*))
        _came_gen_pages = <long**>calloc(<size_t>_npages, sizeof(void*))
        if (_best_pages == NULL or _best_gen_pages == NULL
                or _came_pages == NULL or _came_gen_pages == NULL):
            _npages = 0
            _buf_n = 0
            raise MemoryError("astar_c: page table allocation failed")
        _buf_n = n
        _gen = 0
        return 1

    _best = <double*>malloc(n * sizeof(double))
    _best_gen = <long*>malloc(n * sizeof(long))
    _came = <long*>malloc(n * sizeof(long))
    _came_gen = <long*>malloc(n * sizeof(long))
    if _best == NULL or _best_gen == NULL or _came == NULL or _came_gen == NULL:
        _buf_n = 0
        raise MemoryError("astar_c: buffer allocation failed")
    _buf_n = n
    _gen = 0
    return 1


def astar_c(long W, long H, long L,
            long start_x, long start_y, long pref,
            long goal_x, long goal_y,
            bytes forb_bm, bytes allow_bm, bytes via_dirty_bm,
            layer_ok_list, long goal_layer,
            double via_cost, double layer_penalty,
            cost_pairs, via_pressure_list):
    """返回 [(x, y, l), ...] 或 None。位图按 W*H 索引（(x,y) → y*W+x）。"""
    global _gen, _heap

    cdef long stride_y = W
    cdef long stride_l = W * H
    cdef long n_nodes = L * stride_l
    cdef long i, k, gen
    cdef long flat_c, cur, base, n_idx, start_idx
    cdef int x, y, l, nx, ny, other, ok
    cdef double fv, gv, ng, nf, dirty, crowded, start_f
    cdef int* lok = NULL
    cdef double* vp_arr = NULL
    cdef int have_cost = 0
    cdef int have_vp = 0
    cdef int n_ok = 0
    cdef char* cforb = NULL
    cdef char* callow = NULL
    cdef char* cdirty = NULL
    cdef int have_forb, have_allow, have_dirty
    cdef long pathcap, pathn
    cdef double* pathbuf = NULL
    cdef object out = None

    have_forb = 1 if (forb_bm is not None and PyBytes_GET_SIZE(forb_bm) >= W * H) else 0
    have_allow = 1 if (allow_bm is not None and PyBytes_GET_SIZE(allow_bm) >= W * H) else 0
    have_dirty = 1 if (via_dirty_bm is not None and PyBytes_GET_SIZE(via_dirty_bm) >= W * H) else 0
    if have_forb:
        cforb = PyBytes_AS_STRING(forb_bm)
    if have_allow:
        callow = PyBytes_AS_STRING(allow_bm)
    if have_dirty:
        cdirty = PyBytes_AS_STRING(via_dirty_bm)

    _ensure(n_nodes)
    _gen += 1
    if _gen >= 0x3FFFFFFFFFFFFFF:
        for i in range(_buf_n):
            _bsetgen(i, 0)
            _csetgen(i, 0)
        _gen = 1
    gen = _gen

    n_ok = len(layer_ok_list)
    lok = <int*>malloc((n_ok if n_ok > 0 else 1) * sizeof(int))
    if lok == NULL:
        raise MemoryError("astar_c: layer_ok")
    for i in range(n_ok):
        lok[i] = <int>layer_ok_list[i]

    if cost_pairs:
        _cost_ensure(n_nodes)
        for (ci, cv) in cost_pairs:
            _cost_add(<long>ci, <double>cv)
        have_cost = 1

    if via_pressure_list is not None:
        have_vp = 1
        vp_arr = <double*>malloc((W * H) * sizeof(double))
        if vp_arr == NULL:
            free(lok)
            if have_cost:
                _cost_clear()
            raise MemoryError("astar_c: via_pressure")
        for i in range(W * H):
            vp_arr[i] = <double>via_pressure_list[i]

    if _heap is None:
        _heap = _Heap()
    else:
        _heap.reset()

    start_idx = (pref - 1) * stride_l + start_y * stride_y + start_x
    _bset(start_idx, 0.0)
    _bsetgen(start_idx, gen)
    _cset(start_idx, -1)
    _csetgen(start_idx, gen)

    start_f = <double>(abs(start_x - goal_x) + abs(start_y - goal_y))
    _heap.push(start_f, 0.0, start_idx)

    if start_x == goal_x and start_y == goal_y and (goal_layer < 0 or pref == goal_layer):
        out = [(start_x, start_y, pref)]
        free(lok)
        if have_cost:
            _cost_clear()
        if have_vp:
            free(vp_arr)
        return out

    while _heap.pop(&fv, &gv, &cur) == 1:
        if gv > _bget(cur) + DEF_EPS:
            continue
        l = <int>(cur // stride_l) + 1
        x = <int>((cur % stride_l) % stride_y)
        y = <int>((cur % stride_l) // stride_y)
        if x == goal_x and y == goal_y and (goal_layer < 0 or l == goal_layer):
            pathn = 0
            pathcap = 0
            while True:
                if pathn >= pathcap:
                    pathcap = pathcap * 2 if pathcap else 64
                    pathbuf = <double*>realloc(pathbuf, pathcap * 3 * sizeof(double))
                pathbuf[pathn * 3 + 0] = <double>((cur % stride_l) % stride_y)
                pathbuf[pathn * 3 + 1] = <double>((cur % stride_l) // stride_y)
                pathbuf[pathn * 3 + 2] = <double>(cur // stride_l + 1)
                pathn += 1
                if _cgen(cur) != gen or _cget(cur) < 0:
                    break
                cur = _cget(cur)
            out = []
            for k in range(pathn - 1, -1, -1):
                out.append((<int>pathbuf[k * 3 + 0],
                            <int>pathbuf[k * 3 + 1],
                            <int>pathbuf[k * 3 + 2]))
            free(pathbuf)
            free(lok)
            if have_cost:
                _cost_clear()
            if have_vp:
                free(vp_arr)
            return out

        base = (l - 1) * stride_l
        for k in range(NMOVES):
            nx = x + MOVES[k][0]
            ny = y + MOVES[k][1]
            if nx < 0 or nx >= W or ny < 0 or ny >= H:
                continue
            if have_forb:
                flat_c = ny * W + nx
                if cforb[flat_c] and not (nx == goal_x and ny == goal_y) \
                   and not (have_allow and callow[flat_c]):
                    continue
            n_idx = base + ny * stride_y + nx
            ng = gv + MOVE_COST[k]
            if have_cost:
                ng += _cost[n_idx]
            if l != pref:
                ng += layer_penalty
            if _bgen(n_idx) != gen:
                _bset(n_idx, DEF_INF)
                _bsetgen(n_idx, gen)
            if ng < _bget(n_idx) - DEF_EPS:
                _bset(n_idx, ng)
                _cset(n_idx, cur)
                _csetgen(n_idx, gen)
                nf = ng + <double>(abs(nx - goal_x) + abs(ny - goal_y))
                _heap.push(nf, ng, n_idx)

        for other in (l - 1, l + 1):
            ok = 0
            for k in range(n_ok):
                if lok[k] == other:
                    ok = 1
                    break
            if ok == 0:
                continue
            dirty = 0.0
            flat_c = y * W + x
            if have_dirty and cdirty[flat_c]:
                dirty = DEF_DIRTY
            if have_forb:
                if cforb[flat_c] and not (x == goal_x and y == goal_y) \
                   and not (have_allow and callow[flat_c]):
                    continue
            n_idx = (other - 1) * stride_l + y * stride_y + x
            crowded = vp_arr[flat_c] if have_vp else 0.0
            ng = gv + via_cost + dirty + crowded
            if have_cost:
                ng += _cost[n_idx]
            if _bgen(n_idx) != gen:
                _bset(n_idx, DEF_INF)
                _bsetgen(n_idx, gen)
            if ng < _bget(n_idx) - DEF_EPS:
                _bset(n_idx, ng)
                _cset(n_idx, cur)
                _csetgen(n_idx, gen)
                nf = ng + <double>(abs(x - goal_x) + abs(y - goal_y))
                _heap.push(nf, ng, n_idx)

    free(lok)
    if have_cost:
        _cost_clear()
    if have_vp:
        free(vp_arr)
    return None
