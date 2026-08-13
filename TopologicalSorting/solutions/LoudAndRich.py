"""
Loud and Rich (Medium) — LeetCode 851
https://leetcode.com/problems/loud-and-rich/
Pattern: DFS/topo propagation over a DAG

PROBLEM
-------
There are n people, 0..n-1. `richer[i] = [a, b]` means person `a` has more
money than person `b`. (All richer relationships are consistent — no
contradictions/cycles.) `quiet[i]` is how "quiet" person i is (lower =
quieter); all quiet values are distinct.

For every person `x`, find the quietest person among everyone who has money
greater than OR EQUAL to x's money (including x itself). Return
answer[x] = that person's index.

WHY THIS IS A TOPO SORT PROBLEM
--------------------------------
Model `richer` as a DAG: edge a -> b means "a is richer than b", so
information should flow from a (richer) to b (poorer). For person b, the
"quietest among everyone at least as rich as b" is the min of:
  - b's own quiet value
  - the already-computed "quietest richer-or-equal person" for every person
    a that is directly richer than b (propagated forward along edges)

That's a forward DP over a DAG, which needs nodes processed in topological
order — richer people finalized before poorer people who depend on them —
exactly like Parallel Courses III's finish-time propagation, but with `min`
instead of `max`.

APPROACH (Kahn's BFS, forward propagation)
--------------------------------------------
- Build graph a -> b for richer[i] = [a, b] (a richer than b), indegree[b]+=1.
- ans[i] initialized to i (everyone starts as their own best answer).
- Seed queue with indegree-0 nodes (people with no one confirmed richer than
  them among the input — i.e. richest-known roots in their component).
- Kahn's BFS: when popping node u and relaxing edge u -> v:
      if quiet[ans[u]] < quiet[ans[v]]: ans[v] = ans[u]
  (propagate the best-known quietest-and-rich-enough candidate forward)
  then decrement indegree[v]; enqueue if 0.
- Return ans.

Time:  O(V + E)
Space: O(V + E)

TEST CASES
----------
1) richer = [[1,0],[2,1],[3,1],[3,7],[4,3],[5,3],[6,3]]
   quiet   = [3,2,5,4,6,1,7,0]
   -> [5,5,2,5,4,5,6,7]

2) richer = []
   quiet   = [0]
   -> [0]  (single person, no comparisons -> everyone is their own answer)

3) richer = [[0,1]]
   quiet   = [0,1]
   -> [0,0]  (0 is richer than 1 AND quieter than 1 (quiet[0]=0 < quiet[1]=1),
   so among everyone at least as rich as person 1 -- which includes person 0
   -- person 0 is the quietest, so ans[1] = 0)
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def loudAndRich(self, richer: List[List[int]], quiet: List[int]) -> List[int]:
        n = len(quiet)
        graph = defaultdict(list)
        indegree = [0] * n

        for a, b in richer:  # a richer than b
            graph[a].append(b)
            indegree[b] += 1

        ans = list(range(n))
        queue = deque([i for i in range(n) if indegree[i] == 0])

        while queue:
            node = queue.popleft()
            for nxt in graph[node]:
                if quiet[ans[node]] < quiet[ans[nxt]]:
                    ans[nxt] = ans[node]
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        return ans


if __name__ == "__main__":
    sol = Solution()

    richer1 = [[1, 0], [2, 1], [3, 1], [3, 7], [4, 3], [5, 3], [6, 3]]
    quiet1 = [3, 2, 5, 4, 6, 1, 7, 0]
    assert sol.loudAndRich(richer1, quiet1) == [5, 5, 2, 5, 4, 5, 6, 7]

    assert sol.loudAndRich([], [0]) == [0]

    assert sol.loudAndRich([[0, 1]], [0, 1]) == [0, 0]

    print("All Loud and Rich tests passed!")
