"""
Strange Printer II (Hard) — LeetCode 1591
https://leetcode.com/problems/strange-printer-2/
Pattern: cycle detection between "printing layers"

PROBLEM
-------
There's a strange printer with the following rules:
  - On each turn, the printer picks a rectangle of cells (any size) and a
    color, and paints EVERY cell in that rectangle that color.
  - The printer can only make each print ONCE per color: all cells of a
    given color must be covered by exactly one print operation for that
    color (that single rectangle may later be partially painted over by
    other colors printed afterward).

Given the final `targetGrid`, determine if it's possible to print it this
way.

WHY THIS IS A TOPO SORT PROBLEM
--------------------------------
Each color must be printed as one solid rectangle at some point in time.
Consider the bounding box of all cells with color C in the final grid. Since
the print for C paints the WHOLE bounding box color C, any cell inside that
bounding box that ends up a DIFFERENT color D in the final grid must have
been printed AFTER C (D's print happened later, painting over part of C's
rectangle). That gives a "C must be printed before D" edge: C -> D.

If this "before" relationship has a cycle (C must print before D, but D must
also print before C), it's impossible — you can't order the prints. So:
build the graph of these "must print before" edges among colors, and check
for a cycle via topological sort. Printable iff the graph has no cycle
(topo sort visits every color).

APPROACH
--------
1. For every color, compute its bounding box (min/max row, min/max col)
   over all cells with that color in targetGrid.
2. For every color C, scan every cell inside C's bounding box. If a cell
   there has a different color D, add edge C -> D (dedup with a set so we
   don't inflate indegree).
3. Kahn's topo sort over the colors. If we can process every color (no
   colors stuck with indegree > 0 forever), it's printable -> True.
   Otherwise a cycle exists -> False.

Time:  O(rows * cols * numColors) worst case (bounding-box rescan per
       color), which is fine given color values are bounded to 1..60 and
       grid <= 20x20 in LC's constraints.
Space: O(numColors^2) worst case for edges.

TEST CASES
----------
1) targetGrid = [[1,1,1,1],
                  [1,2,2,1],
                  [1,2,2,1],
                  [1,1,1,1]]                          -> True
   (print 1 first as the full 4x4, then 2 as the inner 2x2 on top)

2) targetGrid = [[1,1,1,1],
                  [1,1,3,3],
                  [1,1,3,4],
                  [5,5,1,4]]                          -> True

3) targetGrid = [[1,2,1],
                  [2,1,2],
                  [1,2,1]]                              -> False
   (1's bounding box spans the whole grid and contains 2's cells, AND 2's
   bounding box spans the whole grid and contains 1's cells -> 1 must print
   before 2 AND after 2 -> cycle -> impossible)
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def isPrintable(self, targetGrid: List[List[int]]) -> bool:
        rows, cols = len(targetGrid), len(targetGrid[0])
        colors = {val for row in targetGrid for val in row}

        # bounds[c] = [minRow, minCol, maxRow, maxCol]
        bounds = {c: [rows, cols, -1, -1] for c in colors}
        for r in range(rows):
            for c in range(cols):
                color = targetGrid[r][c]
                b = bounds[color]
                b[0] = min(b[0], r)
                b[1] = min(b[1], c)
                b[2] = max(b[2], r)
                b[3] = max(b[3], c)

        graph = defaultdict(set)
        indegree = {c: 0 for c in colors}

        for color in colors:
            min_r, min_c, max_r, max_c = bounds[color]
            for r in range(min_r, max_r + 1):
                for c in range(min_c, max_c + 1):
                    other = targetGrid[r][c]
                    if other != color and other not in graph[color]:
                        graph[color].add(other)
                        indegree[other] += 1

        queue = deque([c for c in colors if indegree[c] == 0])
        processed = 0
        while queue:
            node = queue.popleft()
            processed += 1
            for nxt in graph[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        return processed == len(colors)


if __name__ == "__main__":
    sol = Solution()

    assert sol.isPrintable([[1, 1, 1, 1], [1, 2, 2, 1], [1, 2, 2, 1], [1, 1, 1, 1]]) is True
    assert sol.isPrintable([[1, 1, 1, 1], [1, 1, 3, 3], [1, 1, 3, 4], [5, 5, 1, 4]]) is True
    assert sol.isPrintable([[1, 2, 1], [2, 1, 2], [1, 2, 1]]) is False

    print("All Strange Printer II tests passed!")
