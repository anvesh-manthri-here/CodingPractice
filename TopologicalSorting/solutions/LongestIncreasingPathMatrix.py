"""
Longest Increasing Path in a Matrix (Hard) — LeetCode 329
https://leetcode.com/problems/longest-increasing-path-in-a-matrix/
Pattern: implicit DAG + longest path (memoized DFS = DFS-based topo sort)

PROBLEM
-------
Given an m x n integer matrix, find the length of the longest strictly
increasing path, moving in any of the 4 cardinal directions (no diagonals,
no wraparound).

WHY THIS IS A TOPO SORT PROBLEM
--------------------------------
Draw an edge from cell A to cell B if B is a 4-directional neighbor of A and
matrix[B] > matrix[A]. Because values only ever increase along an edge, this
graph is guaranteed acyclic (a cycle would require values to increase and
come back down to the same cell — impossible). We're asked for the LONGEST
PATH in this DAG.

"Longest path in a DAG" is a textbook application of topological order: you
process nodes in topo order and do DP (`longest[v] = 1 + max(longest[u] for
u in predecessors)`). Here we take the equivalent and more natural route:
memoized DFS. Memoized DFS *is* a DFS-based topological sort under the hood
— the recursion only "finishes" (returns) a node after all of its
reachable-and-greater neighbors have finished, exactly like the post-order
stack used in DFS topo sort. We just fold the DP computation into the
recursion instead of doing a separate pass afterward.

APPROACH (memoized DFS)
------------------------
- memo[r][c] = length of the longest increasing path STARTING at (r, c).
- dfs(r, c):
    if memo[r][c] is already computed, return it.
    best = 1 (the cell itself)
    for each of the 4 neighbors with a strictly greater value:
        best = max(best, 1 + dfs(neighbor))
    memo[r][c] = best
    return best
- Answer = max(dfs(r, c) for every cell).
- Because each cell is computed once and cached, total work is O(rows*cols)
  despite the recursive branching.

Time:  O(rows * cols)  — each cell visited/computed once.
Space: O(rows * cols)  — memo table + recursion stack.

TEST CASES
----------
1) matrix = [[9,9,4],
             [6,6,8],
             [2,1,1]]                                -> 4
   (path: 1 -> 2 -> 6 -> 9)

2) matrix = [[3,4,5],
             [3,2,6],
             [2,2,1]]                                -> 4
   (path: 3 -> 4 -> 5 -> 6)

3) matrix = [[1]]                                    -> 1  (single cell)

4) matrix = [[1,2],
             [2,1]]                                  -> 2 (e.g. 1 -> 2, no
   longer strictly increasing chain exists across 4 equal-ish cells here)
"""

from typing import List


class Solution:
    def longestIncreasingPath(self, matrix: List[List[int]]) -> int:
        if not matrix or not matrix[0]:
            return 0

        rows, cols = len(matrix), len(matrix[0])
        memo = [[0] * cols for _ in range(rows)]

        def dfs(r: int, c: int) -> int:
            if memo[r][c]:
                return memo[r][c]

            best = 1
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and matrix[nr][nc] > matrix[r][c]:
                    best = max(best, 1 + dfs(nr, nc))

            memo[r][c] = best
            return best

        return max(dfs(r, c) for r in range(rows) for c in range(cols))


if __name__ == "__main__":
    sol = Solution()

    assert sol.longestIncreasingPath([[9, 9, 4], [6, 6, 8], [2, 1, 1]]) == 4
    assert sol.longestIncreasingPath([[3, 4, 5], [3, 2, 6], [2, 2, 1]]) == 4
    assert sol.longestIncreasingPath([[1]]) == 1
    assert sol.longestIncreasingPath([[1, 2], [2, 1]]) == 2

    print("All Longest Increasing Path in a Matrix tests passed!")
