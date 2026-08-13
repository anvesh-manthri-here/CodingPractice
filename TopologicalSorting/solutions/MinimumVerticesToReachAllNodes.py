"""
Minimum Number of Vertices to Reach All Nodes (Medium) — LeetCode 1557
https://leetcode.com/problems/minimum-number-of-vertices-to-reach-all-nodes/
Pattern: indegree-0 roots

PROBLEM
-------
Given a directed acyclic graph (DAG) with `n` nodes (0..n-1) and edge list
`edges`, find the SMALLEST set of nodes such that every node in the graph is
reachable from at least one node in that set. It's guaranteed the answer is
unique.

WHY THIS CONNECTS TO TOPO SORT / KAHN'S
------------------------------------------
This doesn't need a full topological sort — but understanding *why* is a
great reinforcement of what indegree means in Kahn's algorithm:

  - Any node with indegree 0 (no incoming edges) can ONLY be reached by
    starting AT that node — nothing else in the graph points to it. So it
    MUST be included in any valid "reach everything" set.
  - Any node with indegree > 0 has at least one predecessor; because the
    graph is a DAG (no cycles) and finite, that predecessor chain must
    bottom out at some indegree-0 node, which already reaches this node.
    So indegree > 0 nodes never need to be added explicitly.

Therefore the unique minimal answer is EXACTLY the set of indegree-0 nodes.
No BFS/DFS/queue needed — just count incoming edges per node.

APPROACH
--------
- has_incoming[v] = True for every v that appears as a destination in edges.
- Return every node with has_incoming[node] == False.

Time:  O(V + E)
Space: O(V)

TEST CASES
----------
1) n=6, edges=[[0,1],[0,2],[2,5],[3,4],[4,2]]     -> [0,3]
   (0 reaches 1,2,5 via 2; 3 reaches 4 then 2 then 5 — nothing else reaches
   0 or 3, and everything else is reachable from one of them)
2) n=5, edges=[[0,1],[2,1],[3,1],[1,4],[2,4]]     -> [0,2,3]
   (1 and 4 both have incoming edges from elsewhere; 0,2,3 have none)
3) n=1, edges=[]                                    -> [0]  (single isolated node)
"""

from typing import List


class Solution:
    def findSmallestSetOfVertices(self, n: int, edges: List[List[int]]) -> List[int]:
        has_incoming = [False] * n
        for _, v in edges:
            has_incoming[v] = True
        return [node for node in range(n) if not has_incoming[node]]


if __name__ == "__main__":
    sol = Solution()

    assert sol.findSmallestSetOfVertices(6, [[0, 1], [0, 2], [2, 5], [3, 4], [4, 2]]) == [0, 3]
    assert sol.findSmallestSetOfVertices(5, [[0, 1], [2, 1], [3, 1], [1, 4], [2, 4]]) == [0, 2, 3]
    assert sol.findSmallestSetOfVertices(1, []) == [0]

    print("All Minimum Number of Vertices to Reach All Nodes tests passed!")
