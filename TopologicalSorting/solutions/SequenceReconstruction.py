"""
Sequence Reconstruction (Medium) — LeetCode 444
https://leetcode.com/problems/sequence-reconstruction/
Pattern: uniqueness of topo order

PROBLEM
-------
You are given an integer array `nums` of length n, which is a permutation of
[1, 2, ..., n]. You are also given a 2D array `sequences`, where each
sequences[i] is a subsequence of `nums`.

Check whether `nums` is the ONLY shortest common supersequence of the
sequences (i.e. it can be uniquely reconstructed from the given sequences).
Return True/False.

WHY THIS IS A TOPO SORT PROBLEM
--------------------------------
Each sequences[i] = [a, b, c, ...] tells us "a must come before b, which must
come before c" — exactly like course prerequisites. Build a directed graph
with edges a -> b for every adjacent pair in every sequence. Then:

  1. `nums` must be A valid topological order of that graph (sanity check).
  2. The topological order must be UNIQUE. That is only true if, at every
     step of Kahn's BFS, there is exactly one node with indegree 0 in the
     queue. If ever there are 2+ candidates, there are at least two valid
     orderings, so reconstruction is not unique -> return False.
  3. Every value 1..n must actually appear somewhere in `sequences`,
     otherwise that value's position is never constrained by any edge and
     multiple placements would be equally valid.

APPROACH (Kahn's BFS, unique-order variant)
--------------------------------------------
- Build graph + indegree from consecutive pairs in each sequence.
- Verify the set of nodes mentioned across `sequences` equals set(nums).
- Run Kahn's BFS, but at each iteration the queue must contain exactly one
  node (if len(queue) > 1 -> not unique -> False).
- The order produced must equal `nums` exactly.

Time:  O(n + sum of len(sequences[i]))  — build graph + one BFS pass.
Space: O(n + E) for the graph/indegree/queue.

TEST CASES
----------
1) nums = [1,2,3], sequences = [[1,2],[1,3],[2,3]]           -> True
   (edges 1->2, 1->3, 2->3; at every BFS step exactly one node is ready)
2) nums = [1,2,3], sequences = [[1,2]]                        -> False
   (value 3 never appears in sequences -> its position is unconstrained)
3) nums = [1,2,3], sequences = [[1,2],[1,3]]                  -> False
   (after removing 1, both 2 and 3 become ready simultaneously -> not unique)
4) nums = [4,1,5,2,3], sequences = [[5,2,6,3],[4,1,5,2]]      -> False
   (6 appears in sequences but not in nums -> mismatched node sets)
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def sequenceReconstruction(self, nums: List[int], sequences: List[List[int]]) -> bool:
        graph = defaultdict(set)
        indegree = defaultdict(int)
        nodes = set()

        for seq in sequences:
            nodes.update(seq)
            for i in range(len(seq) - 1):
                u, v = seq[i], seq[i + 1]
                if v not in graph[u]:
                    graph[u].add(v)
                    indegree[v] += 1

        if nodes != set(nums):
            return False

        for x in nums:
            indegree.setdefault(x, 0)

        queue = deque([x for x in nums if indegree[x] == 0])
        result = []

        while queue:
            if len(queue) > 1:
                return False  # more than one valid "next" node -> not unique
            node = queue.popleft()
            result.append(node)
            for nxt in graph[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)

        return result == nums


if __name__ == "__main__":
    sol = Solution()

    assert sol.sequenceReconstruction([1, 2, 3], [[1, 2], [1, 3], [2, 3]]) is True
    assert sol.sequenceReconstruction([1, 2, 3], [[1, 2]]) is False
    assert sol.sequenceReconstruction([1, 2, 3], [[1, 2], [1, 3]]) is False
    assert sol.sequenceReconstruction([4, 1, 5, 2, 3], [[5, 2, 6, 3], [4, 1, 5, 2]]) is False

    print("All Sequence Reconstruction tests passed!")
