"""
Find Eventual Safe States (Medium) — LeetCode 802
https://leetcode.com/problems/find-eventual-safe-states/
Pattern: reverse graph + Kahn's from sinks

PROBLEM
-------
Given a directed graph as an adjacency list `graph` (graph[i] = list of
nodes reachable from i in one edge), a node is "safe" if starting from it
every possible path eventually leads to a terminal node (a node with no
outgoing edges) — i.e. the node can never get stuck in a cycle.

Return all safe nodes, sorted in ascending order.

WHY THIS IS A TOPO SORT PROBLEM
--------------------------------
A node is safe iff it CANNOT reach a cycle. Terminal nodes (outdegree 0) are
trivially safe. A node is safe if ALL of its outgoing edges lead only to
safe nodes. This is the mirror image of Kahn's algorithm:

  - Normal Kahn's: peel nodes with INDEGREE 0 (no unresolved prerequisites),
    working forward from sources.
  - Here: peel nodes with OUTDEGREE 0 (no unresolved "must reach a safe node
    first" obligations), working backward from sinks.

To reuse Kahn's machinery directly, reverse every edge. In the reversed
graph, "outdegree 0 in original" becomes "indegree 0 in reversed" — so we
seed the BFS queue with original terminal (sink) nodes, and peel inward:
whenever ALL of a node's original out-edges have been "satisfied" (i.e. all
its successors have already been proven safe), it becomes safe too and gets
enqueued. Any node still stuck when the queue empties can reach a cycle and
is unsafe.

APPROACH
--------
- Build reverse graph: for edge u -> v (original), add v -> u (reversed).
- outdeg[u] = len(graph[u]) in the ORIGINAL graph.
- queue = all nodes with outdeg == 0 (terminal nodes).
- BFS: pop node, mark safe. For each predecessor p in the reversed graph
  (i.e. p had an original edge p -> node), decrement outdeg[p]; if it hits
  0, all of p's original out-edges now point to safe nodes -> p is safe too
  -> enqueue p.
- Return sorted list of safe nodes.

Time:  O(V + E)
Space: O(V + E)

TEST CASES
----------
1) graph = [[1,2],[2,3],[5],[0],[5],[],[]]         -> [2,4,5,6]
   (0->1->2->5 has a path from 1 back to 0 via 3? let's trust LC's example:
    node 0 can reach node 1 which can reach node 3 which points back to 0 ->
    0,1,3 are on/reach a cycle, so only 2,4,5,6 are safe)
2) graph = [[1,2,3,4],[1,2],[3,4],[0,4],[]]         -> [4]
3) graph = [[],[0,2,3,4],[3],[4],[]]                -> [0,1,2,3,4]
   (no cycles at all -> every node is safe)
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def eventualSafeNodes(self, graph: List[List[int]]) -> List[int]:
        n = len(graph)
        reverse_graph = defaultdict(list)
        outdegree = [0] * n

        for u in range(n):
            outdegree[u] = len(graph[u])
            for v in graph[u]:
                reverse_graph[v].append(u)

        queue = deque([u for u in range(n) if outdegree[u] == 0])
        safe = [False] * n

        while queue:
            node = queue.popleft()
            safe[node] = True
            for pred in reverse_graph[node]:
                outdegree[pred] -= 1
                if outdegree[pred] == 0:
                    queue.append(pred)

        return [i for i in range(n) if safe[i]]


if __name__ == "__main__":
    sol = Solution()

    assert sol.eventualSafeNodes([[1, 2], [2, 3], [5], [0], [5], [], []]) == [2, 4, 5, 6]
    assert sol.eventualSafeNodes([[1, 2, 3, 4], [1, 2], [3, 4], [0, 4], []]) == [4]
    assert sol.eventualSafeNodes([[], [0, 2, 3, 4], [3], [4], []]) == [0, 1, 2, 3, 4]

    print("All Find Eventual Safe States tests passed!")
