# cython: language_level=3, boundscheck=False, wraparound=False, cdivision=True, infer_types=True
"""A* 搜索核的 C 实现（等价候选，代际戳版）。

语义逐条照抄 `ec_layout.astar`。调用方负责按 astar 的规则算好 `pref`，并预建位图。

# 为什么有代际戳

第一版每次调用 malloc 608k doubles + 608k longs 并逐个初始化，实测**比 Python 慢 8 倍**：
本板 143 次检索里中位数只有 16 ms，固定开销完全主导。
现在缓冲区跨调用复用，`gen` 判断"本轮是否访问过"，**零初始化**。
"""
from cpython.bytes cimport PyBytes_AS_STRING, PyBytes_GET_SIZE
from libc.stdlib cimport free, malloc, realloc

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


cdef int _ensure(long n) except -1:
    global _best, _best_gen, _came, _came_gen, _buf_n, _gen
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
            _best_gen[i] = 0
            _came_gen[i] = 0
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
    _best[start_idx] = 0.0
    _best_gen[start_idx] = gen
    _came[start_idx] = -1
    _came_gen[start_idx] = gen

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
        if gv > _best[cur] + DEF_EPS:
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
                if _came_gen[cur] != gen or _came[cur] < 0:
                    break
                cur = _came[cur]
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
            if _best_gen[n_idx] != gen:
                _best[n_idx] = DEF_INF
                _best_gen[n_idx] = gen
            if ng < _best[n_idx] - DEF_EPS:
                _best[n_idx] = ng
                _came[n_idx] = cur
                _came_gen[n_idx] = gen
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
            if _best_gen[n_idx] != gen:
                _best[n_idx] = DEF_INF
                _best_gen[n_idx] = gen
            if ng < _best[n_idx] - DEF_EPS:
                _best[n_idx] = ng
                _came[n_idx] = cur
                _came_gen[n_idx] = gen
                nf = ng + <double>(abs(x - goal_x) + abs(y - goal_y))
                _heap.push(nf, ng, n_idx)

    free(lok)
    if have_cost:
        _cost_clear()
    if have_vp:
        free(vp_arr)
    return None
