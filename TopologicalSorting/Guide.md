# Topological Sorting — Complete Guide

## 1. What is it?

A **topological sort** (topo sort) of a **Directed Acyclic Graph (DAG)** is a linear ordering
of its vertices such that for every directed edge `u -> v`, `u` comes before `v` in the
ordering.

Think of it as: *"if task B depends on task A, do A before B."*

**Key facts**
- Only defined for **directed** graphs.
- Only exists if the graph is **acyclic** (no directed cycles). If a cycle exists, no valid
  ordering can satisfy all edge constraints — this is how topo sort doubles as a
  **cycle detection** technique.
- A DAG can have **more than one** valid topological order (unless the graph is a single
  chain). Any algorithm just needs to produce *one* valid order.
- Undirected graphs, and directed graphs with cycles, have **no** topological order.

**Real-world analogies**
- Course prerequisites → order in which you can take courses.
- Build systems (Makefiles, npm/yarn, Bazel) → order to compile/link targets.
- Task scheduling with dependencies (CI pipelines, workflow engines).
- Spreadsheet formula recalculation order.
- Package manager dependency resolution (apt, pip).
- Symbol resolution / import order in compilers.

https://www.youtube.com/watch?v=3tkcfvCNtM8&t=344s
https://www.youtube.com/watch?v=96owfLr89Lk

---

## 2. The Two Core Algorithms

### A) Kahn's Algorithm (BFS-based, using in-degrees)

**Idea:** Repeatedly remove nodes that have no incoming edges (in-degree 0). Removing a
node "frees up" its neighbors, decreasing their in-degree. If they hit 0, they become
eligible.

**Steps**
1. Compute `indegree[v]` for every vertex (number of incoming edges).
2. Push all vertices with `indegree == 0` into a queue.
3. While the queue is not empty:
   - Pop a vertex `u`, append it to the result order.
   - For each neighbor `v` of `u`: decrement `indegree[v]`. If it becomes `0`, push `v`.
4. If the result order contains all `V` vertices → valid topo order.
   If it contains **fewer** than `V` vertices → the graph has a **cycle** (the remaining
   nodes are stuck in a cycle and never reach indegree 0).

```python
from collections import deque, defaultdict

def topo_sort_kahn(num_nodes, edges):
    """edges: list of (u, v) meaning u -> v (u must come before v)."""
    adj = defaultdict(list)
    indegree = [0] * num_nodes

    for u, v in edges:
        adj[u].append(v)
        indegree[v] += 1

    queue = deque(node for node in range(num_nodes) if indegree[node] == 0)
    order = []

    while queue:
        u = queue.popleft()
        order.append(u)
        for v in adj[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                queue.append(v)

    if len(order) != num_nodes:
        raise ValueError("Graph has a cycle — no topological order exists")

    return order
```

**Complexity:** `O(V + E)` time, `O(V + E)` space.

**When to prefer Kahn's:**
- You need to detect a cycle cleanly (compare `len(order)` to `V`).
- You want an **iterative** solution (no recursion depth worries on huge graphs).
- You need "levels" of parallel work (BFS layers = tasks that can run in parallel).
- Multi-source BFS problems (see "Course Schedule", "Alien Dictionary").

---

### B) DFS-based Algorithm (using a stack / post-order)

**Idea:** Do a DFS. When you finish exploring **all** of a node's descendants (i.e., you're
about to pop out of its recursive call — "post-order"), push it onto a stack. At the end,
pop the stack (or reverse the list) to get the topological order.

**Why this works:** A node is only marked "finished" after everything reachable from it is
finished. So finished-first (post-order reversed) guarantees dependencies come first.

**Steps**
1. Maintain `visited` (fully done) and `visiting` (currently on the recursion stack, for
   cycle detection).
2. For each unvisited node, run DFS.
3. In DFS(u): mark `visiting`; recurse into all unvisited neighbors; if a neighbor is
   currently `visiting` → **cycle detected**; after all neighbors are processed, mark `u`
   as `visited` and push `u` onto a stack.
4. Reverse the stack (or pop it) → topological order.

```python
def topo_sort_dfs(num_nodes, edges):
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)

    WHITE, GRAY, BLACK = 0, 1, 2       # unvisited, in-progress, done
    state = [WHITE] * num_nodes
    stack = []
    has_cycle = False

    def dfs(u):
        nonlocal has_cycle
        state[u] = GRAY
        for v in adj[u]:
            if state[v] == GRAY:
                has_cycle = True
                return
            if state[v] == WHITE:
                dfs(v)
                if has_cycle:
                    return
        state[u] = BLACK
        stack.append(u)

    for node in range(num_nodes):
        if state[node] == WHITE:
            dfs(node)
        if has_cycle:
            raise ValueError("Graph has a cycle — no topological order exists")

    return stack[::-1]
```

**Complexity:** `O(V + E)` time, `O(V)` extra space (recursion stack + state array).

**When to prefer DFS-based:**
- You're already doing DFS for something else (e.g., Strongly Connected Components,
  `Tarjan`'s / `Kosaraju`'s algorithm building blocks).
- Recursive style feels natural for the problem (e.g., "eventual safe states").
- Watch out for recursion depth on very large/deep graphs (Python default limit ~1000;
  bump with `sys.setrecursionlimit` or convert to iterative DFS with an explicit stack).

---

## 3. Kahn's vs DFS — Cheat Comparison

| Aspect | Kahn's (BFS) | DFS-based |
|---|---|---|
| Style | Iterative | Recursive (or iterative w/ explicit stack) |
| Cycle detection | `len(order) != V` | 3-color / gray-node revisit |
| Extra info for free | "Levels" = parallelizable batches | Natural fit with SCC algorithms |
| Stack overflow risk | None | Possible on deep graphs |
| Ease of getting **lexicographically smallest** order | Use a min-heap instead of queue | Harder — needs reverse-order tricks |

---

## 4. Common Problem Patterns

1. **Course Schedule (feasibility)** — "Can all tasks be finished given prerequisites?"
   → Just detect a cycle. Kahn's: check `len(order) == V`. DFS: check `has_cycle`.

2. **Course Schedule II (produce an order)** — Return an actual valid order, or `[]` if
   impossible.

3. **All valid orders / lexicographically smallest order** — Kahn's algorithm with a
   **min-heap** instead of a plain queue (always pick the smallest available indegree-0
   node next).

4. **Alien Dictionary** — Build a graph from **adjacent word-pair comparisons** (first
   differing character defines an edge `c1 -> c2`), then topo sort the alphabet. Watch
   edge cases: a word that's a *prefix* of an earlier word (`"abc"` before `"ab"`) makes
   the input invalid.

5. **Parallel Courses / Minimum time to finish all tasks** — Kahn's BFS layer-by-layer;
   answer = number of BFS layers (or max path length in DAG if tasks have weights/durations).

6. **Longest / Shortest Path in a DAG** — Topo sort first, then do a single relaxation pass
   over vertices **in topological order** (DP over a DAG). This is `O(V + E)`, much faster
   than Dijkstra/Bellman-Ford for DAGs.

7. **Eventual Safe States** — A node is "safe" if every path from it eventually terminates
   (no cycle reachable). Reverse the graph and run Kahn's from *terminal* nodes, OR do
   3-color DFS and mark nodes as safe when they never touch a `GRAY` node.

8. **Build/Task Scheduler with grouping** — Sometimes you need **two-level** topo sort
   (e.g., group order, then item order within group) — LeetCode "Sort Items by Groups
   Respecting Dependencies".

9. **Counting number of valid topological orders** — Usually needs DP + bitmasking
   (small `V`) since the general count is #P-hard.

10. **Minimum Height Trees / peeling leaves** — A "reverse" flavor of Kahn's: repeatedly
    strip leaf nodes from an **undirected tree** to find its center(s).

---

## 5. Building the Graph — Common Gotchas

- **Direction of edges matters.** "Course A is a prerequisite for B" means edge `A -> B`
  (A before B). Read problem statements carefully — some phrase pairs as `[a, b]` meaning
  "b is prerequisite of a" (edge `b -> a`). Always double check with the examples given.
- **Self-loops** (`u -> u`) are cycles of length 1 — handle or reject them.
- **Duplicate edges** usually don't break correctness but can double-count indegree if
  you're not careful — dedupe if the problem allows multi-edges but you only care about
  reachability.
- **Disconnected graphs** are fine — topo sort still works; just make sure your loop
  starts DFS/Kahn's from *every* unvisited node, not just node 0.
- **Multiple valid answers**: most judges accept any valid order — verify by checking
  each edge `u -> v` has `pos[u] < pos[v]` in your output.

---

## 6. Complexity Summary

| Operation | Time | Space |
|---|---|---|
| Build adjacency list + indegree | O(V + E) | O(V + E) |
| Kahn's BFS topo sort | O(V + E) | O(V) |
| DFS-based topo sort | O(V + E) | O(V) (+ recursion stack) |
| Cycle detection (either method) | O(V + E) | O(V) |
| Longest path in DAG via topo order | O(V + E) | O(V) |

---

## 7. Templates Quick-Reference (Python)

**Cycle check only (Kahn's):**
```python
def can_finish(num_nodes, edges):
    adj = defaultdict(list)
    indegree = [0] * num_nodes
    for u, v in edges:
        adj[u].append(v)
        indegree[v] += 1
    q = deque(n for n in range(num_nodes) if indegree[n] == 0)
    seen = 0
    while q:
        u = q.popleft()
        seen += 1
        for v in adj[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                q.append(v)
    return seen == num_nodes
```

**Lexicographically smallest topo order (min-heap variant):**
```python
import heapq

def topo_sort_lexicographic(num_nodes, edges):
    adj = defaultdict(list)
    indegree = [0] * num_nodes
    for u, v in edges:
        adj[u].append(v)
        indegree[v] += 1

    heap = [n for n in range(num_nodes) if indegree[n] == 0]
    heapq.heapify(heap)
    order = []

    while heap:
        u = heapq.heappop(heap)
        order.append(u)
        for v in adj[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                heapq.heappush(heap, v)

    return order if len(order) == num_nodes else []
```

**Longest path in a DAG (after topo sort):**
```python
def longest_path(num_nodes, edges, weights=None):
    # weights[(u, v)] defaults to 1 if not provided
    adj = defaultdict(list)
    for u, v in edges:
        adj[u].append(v)

    order = topo_sort_kahn(num_nodes, edges)   # raises if cyclic
    dist = [0] * num_nodes

    for u in order:
        for v in adj[u]:
            w = weights[(u, v)] if weights else 1
            if dist[u] + w > dist[v]:
                dist[v] = dist[u] + w

    return dist
```

---

## 8. How to Practice

1. Start with **feasibility** problems (just cycle detection) — builds intuition for
   graph construction and indegree bookkeeping.
2. Move to **producing an order** — same algorithm, just collect the result.
3. Try **min-heap variant** for "smallest lexicographic order" problems.
4. Try the **string-derived graph** pattern (Alien Dictionary) — the hardest part is
   building the graph correctly, not the sort itself.
5. Finish with **DP-over-DAG** problems (longest/shortest path, counting paths,
   parallel task scheduling) to see topo sort as a *building block*, not just an
   end in itself.

See `Practice_Problems.md` in this folder for a curated problem set organized by
difficulty, and `Cheatsheet.md` for a one-page quick reference while solving.
