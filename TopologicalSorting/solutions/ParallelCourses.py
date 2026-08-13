"""
Parallel Courses (Medium) — LeetCode 1136 (Premium)
https://leetcode.com/problems/parallel-courses/
Free mirror: https://walkccc.me/LeetCode/problems/1136/
Pattern: BFS layers = minimum semesters

PROBLEM
-------
There are `n` courses, labeled 1..n. You are given `relations`, where
relations[i] = [prevCourse, nextCourse] means prevCourse must be taken
before nextCourse. In one semester you can take ANY NUMBER of courses, as
long as all of their prerequisites were taken in previous semesters.

Return the minimum number of semesters needed to take all courses. If it's
impossible (a cycle exists), return -1.

WHY THIS IS A TOPO SORT PROBLEM
--------------------------------
"Take all courses whose prereqs are satisfied, all at once" is exactly one
full "layer" of Kahn's BFS: every node currently in the queue has indegree 0
right now, so they can all be processed simultaneously (= same semester).
Draining the whole queue once = one semester. The number of times you drain
the queue = the answer. If some courses never reach indegree 0 (cycle),
return -1.

APPROACH (Kahn's BFS, level-by-level)
--------------------------------------
- Build graph prereq -> course, indegree per course.
- Seed queue with indegree-0 courses (no prerequisites).
- While queue not empty:
    - semesters += 1
    - process EVERY node currently in the queue (a full "layer"), not just
      one — this is the key difference from plain Kahn's.
    - for each processed node, decrement neighbors' indegree; if 0, enqueue.
- If total processed courses == n, return semesters, else return -1.

Time:  O(V + E)
Space: O(V + E)

TEST CASES
----------
1) n = 3, relations = [[1,3],[2,3]]              -> 2
   (semester 1: courses 1,2; semester 2: course 3)
2) n = 3, relations = [[1,2],[2,3],[3,1]]          -> -1  (cycle)
3) n = 1, relations = []                            -> 1  (single course, no deps)
4) n = 5, relations = [[1,2],[2,3],[3,4],[4,5]]     -> 5  (strict chain, one per semester)
5) n = 4, relations = [[2,1],[3,1],[1,4]]           -> 3
   (sem1: 2,3 ; sem2: 1 ; sem3: 4)
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def minimumSemesters(self, n: int, relations: List[List[int]]) -> int:
        graph = defaultdict(list)
        indegree = [0] * (n + 1)

        for u, v in relations:
            graph[u].append(v)
            indegree[v] += 1

        queue = deque([c for c in range(1, n + 1) if indegree[c] == 0])
        semesters = 0
        studied = 0

        while queue:
            semesters += 1
            for _ in range(len(queue)):  # drain exactly this layer
                course = queue.popleft()
                studied += 1
                for nxt in graph[course]:
                    indegree[nxt] -= 1
                    if indegree[nxt] == 0:
                        queue.append(nxt)

        return semesters if studied == n else -1


if __name__ == "__main__":
    sol = Solution()

    assert sol.minimumSemesters(3, [[1, 3], [2, 3]]) == 2
    assert sol.minimumSemesters(3, [[1, 2], [2, 3], [3, 1]]) == -1
    assert sol.minimumSemesters(1, []) == 1
    assert sol.minimumSemesters(5, [[1, 2], [2, 3], [3, 4], [4, 5]]) == 5
    assert sol.minimumSemesters(4, [[2, 1], [3, 1], [1, 4]]) == 3

    print("All Parallel Courses tests passed!")
