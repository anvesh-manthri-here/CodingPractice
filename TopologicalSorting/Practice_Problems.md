# Topological Sort — Practice Problem Set

Work top to bottom. Each problem lists: difficulty, the core pattern it drills, a link
(LeetCode unless noted), and a hint (collapsed mentally — try not to read it until stuck).
Track your progress with the checkboxes.

> Tip: implement each solution in this folder, e.g. `solutions/course_schedule.py`,
> and re-run against the examples in the problem statement before checking LeetCode.

---

## Tier 1 — Foundations (cycle detection & basic ordering)

- [ ] **Course Schedule** (Medium) — pattern: *feasibility / cycle detection*
  https://leetcode.com/problems/course-schedule/
  Hint: Build graph `prereq -> course`. Run Kahn's. Answer = `count(visited) == numCourses`.

- [ ] **Course Schedule II** (Medium) — pattern: *produce an order*
  https://leetcode.com/problems/course-schedule-ii/
  Hint: Same as above, but return the collected `order` list; return `[]` if a cycle exists.

- [ ] **Find the Town Judge** (Easy, indirect) — pattern: *indegree/outdegree reasoning*
  https://leetcode.com/problems/find-the-town-judge/
  Hint: Not a full topo sort, but great warm-up for indegree/outdegree bookkeeping which
  underlies Kahn's algorithm.

- [ ] **Minimum Height Trees** (Medium) — pattern: *leaf-peeling (Kahn's on an undirected tree)*
  https://leetcode.com/problems/minimum-height-trees/
  Hint: Repeatedly strip degree-1 leaves (like Kahn's but undirected). Last 1-2 remaining
  nodes are the answer.

---

## Tier 2 — Core Interview Staples

- [ ] **Alien Dictionary** (Hard, LeetCode Premium / on many other judges too) —
  pattern: *build graph from string comparisons, then topo sort*
  https://leetcode.com/problems/alien-dictionary/
  Hint: Compare each pair of adjacent words; the first differing character gives an edge
  `word1[i] -> word2[i]`. If `word1` is longer than `word2` AND is a prefix of it → invalid
  input (return `""`). Topo sort the 26 letters that actually appear.

- [ ] **Sequence Reconstruction** (Medium) — pattern: *uniqueness of topo order*
  https://leetcode.com/problems/sequence-reconstruction/
  Hint: Build graph from the given sequences. The reconstruction is unique iff, at every
  step of Kahn's BFS, the queue has exactly one candidate node.

- [ ] **Course Schedule III** (Hard, different technique but good contrast) —
  pattern: *greedy + heap, NOT topo sort* — solve this to learn when topo sort does
  **not** apply (no prerequisite chain here, just deadlines).
  https://leetcode.com/problems/course-schedule-iii/

- [ ] **Parallel Courses** (Medium) — pattern: *BFS layers = minimum semesters*
  https://leetcode.com/problems/parallel-courses/
  Hint: Run Kahn's level-by-level (process the whole queue per iteration); each full queue
  drain = one semester. Answer = number of layers if all courses processed, else `-1`.

- [ ] **Parallel Courses III** (Hard) — pattern: *DAG DP with weighted "durations"*
  https://leetcode.com/problems/parallel-courses-iii/
  Hint: Topo sort, then `finishTime[v] = max(finishTime[v], finishTime[u] + time[v])` for
  each edge `u -> v` processed in topo order. Answer = `max(finishTime)`.

---

## Tier 3 — Applying Topo Sort Inside a Bigger Problem

- [ ] **Longest Increasing Path in a Matrix** (Hard) — pattern: *implicit DAG + longest path*
  https://leetcode.com/problems/longest-increasing-path-in-a-matrix/
  Hint: Each cell has an edge to a strictly-greater neighbor. This is a DAG (values only
  increase). You can topo-sort conceptually via memoized DFS (equivalent to DFS-based
  topo sort) instead of building an explicit graph.

- [ ] **Evaluate Division** (Medium, graph not strictly DAG but related traversal skill) —
  optional side-quest, not core topo sort — skip if short on time.

- [ ] **Find Eventual Safe States** (Medium) — pattern: *reverse graph + Kahn's from sinks*
  https://leetcode.com/problems/find-eventual-safe-states/
  Hint: A node is "safe" iff it cannot reach a cycle. Reverse all edges, seed Kahn's queue
  with original **sink** nodes (outdegree 0 in original graph = indegree 0 in reversed
  graph), and peel inward. Nodes processed by the time the queue empties are safe.

- [ ] **Sort Items by Groups Respecting Dependencies** (Hard) — pattern: *two-level topo sort*
  https://leetcode.com/problems/sort-items-by-groups-respecting-dependencies/
  Hint: Topo sort the groups first, then topo sort items **within** each group, respecting
  cross edges to decide group order. Assign ungrouped items (`group[i] == -1`) their own
  unique group id first.

- [ ] **Build a Matrix With Conditions** (Hard) — pattern: *two independent topo sorts
  (row order + column order) combined*
  https://leetcode.com/problems/build-a-matrix-with-conditions/
  Hint: Topo sort `rowConditions` to get each value's row; topo sort `colConditions`
  separately to get each value's column; place values in the matrix accordingly. If
  either topo sort fails (cycle), return `[]`.

- [ ] **Loud and Rich** (Medium) — pattern: *DFS/topo propagation over a DAG*
  https://leetcode.com/problems/loud-and-rich/
  Hint: Edge `richer[i] = [a, b]` means `a` is richer than `b`, i.e., `a -> b` in the DAG.
  Topo sort (or memoized DFS) from richest-unknown roots down, propagating the "quietest
  person among all who are >= as rich" forward.

---

## Tier 4 — Stretch / Advanced

- [ ] **Strange Printer II** (Hard) — pattern: *cycle detection between "printing layers"*
  https://leetcode.com/problems/strange-printer-ii/
  Hint: For every pair of colors that overlap in the grid where one doesn't fully contain
  the other in bounding-box order, you can't determine ordering → build a "must be printed
  before" graph and check for a cycle.

- [ ] **Minimum Number of Vertices to Reach All Nodes** (Medium) — pattern: *indegree-0 roots*
  https://leetcode.com/problems/minimum-number-of-vertices-to-reach-all-nodes/
  Hint: In a DAG, the answer is simply all nodes with indegree 0 — no full sort needed,
  but understanding *why* reinforces Kahn's core idea.

- [ ] **Count All Possible Routes** / **Number of ways to arrive** (optional, DAG DP flavor,
  not strictly topo sort but same "process in dependency order" mental model).

- [ ] **Design a general-purpose task scheduler** (own exercise, no LeetCode link) —
  Write a small library: given a dict of `task -> [dependencies]`, return either a valid
  execution order or raise a clear "circular dependency involving: X -> Y -> Z -> X" error
  message naming the actual cycle (not just "cycle detected"). This forces you to track
  **parent pointers** during DFS to reconstruct the cycle path — a common follow-up
  interview question.

---

## Suggested order of attack

1. Tier 1 fully (get the mechanics automatic).
2. Course Schedule II + Alien Dictionary + Parallel Courses from Tier 2 (the "big three"
   most commonly asked in interviews).
3. Find Eventual Safe States + Sort Items by Groups (Tier 3) — these show topo sort
   composed with other techniques.
4. Pick 1-2 from Tier 4 if you want extra depth, especially the custom scheduler exercise
   for the "explain the cycle" follow-up question.

## Self-check after each problem
- Could I explain *why* my chosen algorithm (Kahn's vs DFS) fit this problem better than
  the other one?
- Did I correctly handle disconnected components / multiple independent chains?
- Did I correctly detect and report cycles instead of silently returning a wrong order?
- What's the time/space complexity of my solution, and does it match `O(V + E)`?
