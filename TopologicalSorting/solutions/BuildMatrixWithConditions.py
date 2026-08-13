"""
Build a Matrix With Conditions (Hard) — LeetCode 2392
https://leetcode.com/problems/build-a-matrix-with-conditions/
Pattern: two independent topo sorts (row order + column order) combined

PROBLEM
-------
Given an integer `k`, build a k x k matrix containing each of the numbers
1..k EXACTLY ONCE, such that:
  - For every [a, b] in `rowConditions`: a must appear in a ROW strictly
    above b's row.
  - For every [a, b] in `colConditions`: a must appear in a COLUMN strictly
    left of b's column.

Return any valid matrix, or [] if it's impossible.

WHY THIS IS A TOPO SORT PROBLEM (TWICE, INDEPENDENTLY)
---------------------------------------------------------
Row and column placement are entirely independent sub-problems:
  - rowConditions only constrain relative ROW order -> topo sort the values
    1..k using rowConditions as edges to get each value's row index.
  - colConditions only constrain relative COLUMN order -> topo sort
    separately using colConditions as edges to get each value's column
    index.

If either topo sort is impossible (a cycle in that condition set), the
whole matrix is impossible.

APPROACH
--------
1. Topo-sort values 1..k using rowConditions (Kahn's). If it doesn't cover
   all k values -> cycle -> return [].
2. Topo-sort values 1..k using colConditions (Kahn's), same cycle check.
3. row_position[val] = index of val in the row-topo-order (that's literally
   its row in the final matrix). Same for col_position via col-topo-order.
4. Build a k x k zero matrix, and for each value place it at
   matrix[row_position[val]][col_position[val]] = val.

Time:  O(k + E_row + E_col + k^2) — the k^2 is just building/returning the
       output matrix itself.
Space: O(k^2) for the output matrix.

TEST CASES
----------
1) k=3, rowConditions=[[1,2],[3,2]], colConditions=[[2,1]]
   -> a valid matrix exists (1 and 3 above 2 in row order; 2 left of 1 in
      column order). We validate the OUTPUT against the constraints rather
      than asserting one fixed matrix, since multiple valid answers exist.

2) k=3, rowConditions=[[1,2],[2,3],[3,1]], colConditions=[]
   -> [] (rowConditions has a cycle: 1->2->3->1)

3) k=1, rowConditions=[], colConditions=[]
   -> [[1]]  (trivial single-cell matrix)
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def buildMatrix(
        self, k: int, rowConditions: List[List[int]], colConditions: List[List[int]]
    ) -> List[List[int]]:
        def topo_order(conditions: List[List[int]]) -> List[int]:
            graph = defaultdict(list)
            indegree = [0] * (k + 1)
            for u, v in conditions:
                graph[u].append(v)
                indegree[v] += 1

            queue = deque([val for val in range(1, k + 1) if indegree[val] == 0])
            order = []
            while queue:
                node = queue.popleft()
                order.append(node)
                for nxt in graph[node]:
                    indegree[nxt] -= 1
                    if indegree[nxt] == 0:
                        queue.append(nxt)
            return order if len(order) == k else []

        row_order = topo_order(rowConditions)
        col_order = topo_order(colConditions)
        if not row_order or not col_order:
            return []

        row_position = {val: i for i, val in enumerate(row_order)}
        col_position = {val: i for i, val in enumerate(col_order)}

        matrix = [[0] * k for _ in range(k)]
        for val in range(1, k + 1):
            matrix[row_position[val]][col_position[val]] = val
        return matrix


def _validate(k, rowConditions, colConditions, matrix):
    if not matrix:
        return False
    pos = {}
    for r in range(k):
        for c in range(k):
            if matrix[r][c] != 0:
                pos[matrix[r][c]] = (r, c)
    if set(pos.keys()) != set(range(1, k + 1)):
        return False
    for a, b in rowConditions:
        if pos[a][0] >= pos[b][0]:
            return False
    for a, b in colConditions:
        if pos[a][1] >= pos[b][1]:
            return False
    return True


if __name__ == "__main__":
    sol = Solution()

    m1 = sol.buildMatrix(3, [[1, 2], [3, 2]], [[2, 1]])
    assert _validate(3, [[1, 2], [3, 2]], [[2, 1]], m1)

    m2 = sol.buildMatrix(3, [[1, 2], [2, 3], [3, 1]], [])
    assert m2 == []

    m3 = sol.buildMatrix(1, [], [])
    assert m3 == [[1]]

    print("All Build a Matrix With Conditions tests passed!")
