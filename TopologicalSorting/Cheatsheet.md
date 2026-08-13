# Topological Sort — One-Page Cheatsheet

## Recognize the pattern
Look for phrases like: *"prerequisite", "must be done before", "depends on", "build
order", "compile order", "course schedule", "dependency resolution", "scheduling",
"can all X be completed"* → 90% of the time this is topo sort on a directed graph.

## Decision tree
```
Is the graph directed?
 ├─ No  → topo sort does NOT apply (consider MST / BFS / union-find instead)
 └─ Yes
     ├─ Just need feasibility (yes/no)?          → Kahn's, check seen == V
     ├─ Need an actual valid order?              → Kahn's or DFS, return the order
     ├─ Need lexicographically smallest order?    → Kahn's + min-heap instead of queue
     ├─ Need longest/shortest path in a DAG?      → topo sort, then DP relax in order
     ├─ Need "safe" nodes (no cycle reachable)?   → reverse graph + Kahn's from sinks,
     │                                                or 3-color DFS
     └─ Need parallel "levels" / min time?        → Kahn's BFS, track layer number
```

## Kahn's Algorithm — 5-line mental model
1. Count indegree of every node.
2. Queue up all indegree-0 nodes.
3. Pop, add to result, decrement neighbors' indegree.
4. Neighbor hits 0 → push it.
5. `len(result) < V` → cycle exists.

## DFS-based — 5-line mental model
1. 3 states: WHITE (unvisited), GRAY (on current path), BLACK (done).
2. DFS(u): mark GRAY.
3. Recurse into neighbors; neighbor GRAY → cycle!
4. After all neighbors done: mark BLACK, push u to stack.
5. Reverse the stack at the end → topo order.

## Common bugs to check when stuck
- [ ] Did you get edge direction backwards? (`[a,b]` meaning `b before a` vs `a before b`)
- [ ] Did you loop over **every** node to start DFS/seed the queue (not just node 0)?
      Graph may be disconnected.
- [ ] Self-loop `u -> u` — does your code correctly flag it as a cycle?
- [ ] Off-by-one in indegree counting when parsing edges from strings/pairs?
- [ ] For "smallest lexicographic order" — did you use a heap, not a plain queue/deque?
- [ ] For DAG longest path — did you relax edges **in topo order**, not any order?
- [ ] Recursion depth exceeded on DFS for large inputs → switch to Kahn's or iterative DFS.

## Complexity
Both algorithms: **O(V + E) time, O(V) extra space.**

## Verifying your own output
Given order `pos[]` (index of each node in the result):
```python
def is_valid_topo_order(order, edges):
    pos = {node: i for i, node in enumerate(order)}
    return all(pos[u] < pos[v] for u, v in edges)
```
