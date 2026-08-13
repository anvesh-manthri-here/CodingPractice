"""
Parallel Courses III (Hard) — LeetCode 2050
https://leetcode.com/problems/parallel-courses-iii/
Pattern: DAG DP with weighted "durations"

PROBLEM
-------
There are `n` courses labeled 1..n. `relations[i] = [prevCourse, nextCourse]`
means prevCourse must be completed before nextCourse can start. `time[i]` is
the number of months to complete course i+1 (1-indexed courses, 0-indexed
array). You may take multiple courses at once, but a course can only START
after ALL of its prerequisites have FINISHED (not just started).

Return the minimum number of months needed to complete all courses.

WHY THIS IS A TOPO SORT PROBLEM
--------------------------------
This is Parallel Courses I, generalized: instead of counting BFS "layers",
each course now takes a variable amount of time. The earliest a course can
start is the moment its LAST prerequisite finishes — so we need courses
processed in dependency order (topological order) to compute each course's
finish time using only already-finalized values from its prerequisites.

This is a classic "DAG dynamic programming" pattern:
    finishTime[v] = time[v] + max(finishTime[u] for all prereqs u of v)
                    (or just time[v] if v has no prerequisites)

Kahn's BFS naturally visits nodes only after all their prerequisites are
already dequeued/finalized when the graph is a DAG, so we can compute
finishTime incrementally as we go.

APPROACH
--------
- Build graph prev -> next, indegree per course.
- finish[v] initialized to time[v] for indegree-0 courses (nothing blocks
  them, they start at month 0).
- Kahn's BFS: when we pop u and relax edge u -> v:
      finish[v] = max(finish[v], finish[u] + time[v])
  (v can only start once u AND all other prereqs of v have finished, and
  Kahn's guarantees u is finalized before we ever look at v's other prereqs
  because we only enqueue v once ITS OWN indegree hits 0.)
- Answer = max(finish) over all courses.

Time:  O(V + E)
Space: O(V + E)

TEST CASES
----------
1) n=3, relations=[[1,3],[2,3]], time=[3,2,5]        -> 8
   (course 1 finishes month 3, course 2 finishes month 2 [both start at 0
   since no prereqs]; course 3 needs both done -> starts at max(3,2)=3,
   takes 5 more months -> finishes at 8)
2) n=5, relations=[[1,5],[2,5],[3,5],[3,4],[4,5]], time=[1,2,3,4,5]  -> 12
   (course 3 finishes at 3; course 4 needs course3 -> starts 3, +4 = 7;
   course 5 needs 1,2,3,4 -> starts at max(1,2,3,7)=7, +5 = 12)
3) n=1, relations=[], time=[5]                        -> 5  (single course)
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def minimumTime(self, n: int, relations: List[List[int]], time: List[int]) -> int:
        graph = defaultdict(list)
        indegree = [0] * (n + 1)

        for u, v in relations:
            graph[u].append(v)
            indegree[v] += 1

        finish = [0] * (n + 1)
        queue = deque()
        for course in range(1, n + 1):
            if indegree[course] == 0:
                finish[course] = time[course - 1]
                queue.append(course)

        while queue:
            u = queue.popleft()
            for v in graph[u]:
                finish[v] = max(finish[v], finish[u] + time[v - 1])
                indegree[v] -= 1
                if indegree[v] == 0:
                    queue.append(v)

        return max(finish[1:])


if __name__ == "__main__":
    sol = Solution()

    assert sol.minimumTime(3, [[1, 3], [2, 3]], [3, 2, 5]) == 8
    assert sol.minimumTime(5, [[1, 5], [2, 5], [3, 5], [3, 4], [4, 5]], [1, 2, 3, 4, 5]) == 12
    assert sol.minimumTime(1, [], [5]) == 5

    print("All Parallel Courses III tests passed!")
