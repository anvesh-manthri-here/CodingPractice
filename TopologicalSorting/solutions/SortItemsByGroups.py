"""
Sort Items by Groups Respecting Dependencies (Hard) — LeetCode 1203
https://leetcode.com/problems/sort-items-by-groups-respecting-dependencies/
Pattern: two-level topo sort (groups, then items within groups)

PROBLEM
-------
You have `n` items, numbered 0..n-1. Each item belongs to a group given by
`group[i]` (or -1 if ungrouped — treat each ungrouped item as its own
singleton group). `beforeItems[i]` is a list of items that must come before
item i in the final ordering.

Return a valid ordering of ALL items that respects every beforeItems
constraint, or [] if no valid ordering exists.

WHY THIS IS A TOPO SORT PROBLEM (TWICE)
-----------------------------------------
There are two interleaved constraints:
  1. Items within the same group must respect their beforeItems edges.
  2. If item A (group G1) must come before item B (group G2 != G1), then
     the ENTIRE group G1 must be scheduled before ANY of group G2 appears
     — i.e. there's an implicit dependency G1 -> G2 at the group level.

So we build TWO graphs and topo-sort both:
  - An item-level graph using every beforeItems edge (regardless of group).
  - A group-level graph, adding an edge group[pre] -> group[item] whenever
    pre and item are in different groups.

If either topo sort fails (cycle), the whole thing is impossible -> [].
Otherwise: topo-sort items to get a valid item order; topo-sort groups to
get a valid group order; then output items bucketed by group, visiting
groups in group-order and, within each group, keeping the relative order
from the item-level topo sort (which already respects intra-group edges).

APPROACH
--------
1. Assign fresh unique group ids to every item with group[i] == -1.
2. Build item_graph/indegree from ALL beforeItems edges.
3. Build group_graph/indegree: for every beforeItems edge (pre -> item)
   where group[pre] != group[item], add edge group[pre] -> group[item]
   (deduped, so multiple items don't inflate indegree).
4. Kahn's topo sort on items; Kahn's topo sort on groups. Bail to [] if
   either doesn't cover all nodes (cycle detected).
5. Bucket the item-topo-order by group, then concatenate buckets in
   group-topo-order.

Time:  O(V + E) for both graphs combined.
Space: O(V + E)

TEST CASES
----------
1) n=8, m=2, group=[-1,-1,1,0,0,1,0,-1]
   beforeItems=[[],[6],[5],[6],[3,6],[],[],[]]
   -> must be a valid ordering (LC accepts several). We validate the
      RESULT against the original constraints instead of a fixed expected
      list, since multiple valid answers exist.

2) n=3, m=2, group=[-1,-1,1], beforeItems=[[],[],[0]]  -> valid ordering
   exists (item 0 before item 2; item1 independent)

3) n=3, m=2, group=[0,0,1], beforeItems=[[],[0],[1]]
   -> [0,1,2] is forced (chain 0 -> 1 -> 2, groups happen to already align)

4) Impossible case: n=3, m=2, group=[0,0,1], beforeItems=[[2],[],[0]]
   -> item 0 needs 2 first, but item 2 needs 0 first -> cycle -> []
"""

from collections import deque, defaultdict
from typing import List


class Solution:
    def sortItems(self, n: int, m: int, group: List[int], beforeItems: List[List[int]]) -> List[int]:
        group = list(group)  # don't mutate caller's list
        next_group_id = m
        for i in range(n):
            if group[i] == -1:
                group[i] = next_group_id
                next_group_id += 1
        total_groups = next_group_id

        item_graph = defaultdict(list)
        item_indegree = [0] * n
        group_graph = defaultdict(list)
        group_indegree = [0] * total_groups
        group_edges_seen = set()

        for item in range(n):
            for pre in beforeItems[item]:
                item_graph[pre].append(item)
                item_indegree[item] += 1

                if group[pre] != group[item]:
                    edge = (group[pre], group[item])
                    if edge not in group_edges_seen:
                        group_edges_seen.add(edge)
                        group_graph[group[pre]].append(group[item])
                        group_indegree[group[item]] += 1

        def topo(node_count, graph, indegree):
            queue = deque([node for node in range(node_count) if indegree[node] == 0])
            order = []
            while queue:
                node = queue.popleft()
                order.append(node)
                for nxt in graph[node]:
                    indegree[nxt] -= 1
                    if indegree[nxt] == 0:
                        queue.append(nxt)
            return order if len(order) == node_count else []

        item_order = topo(n, item_graph, item_indegree)
        group_order = topo(total_groups, group_graph, group_indegree)

        if not item_order or not group_order:
            return []

        items_in_group = defaultdict(list)
        for item in item_order:
            items_in_group[group[item]].append(item)

        result = []
        for g in group_order:
            result.extend(items_in_group[g])
        return result


def _respects_before_items(n, beforeItems, result):
    """Helper: confirms `result` is a permutation of 0..n-1 that respects
    every beforeItems[item] -> item ordering constraint."""
    if sorted(result) != list(range(n)):
        return False
    position = {item: i for i, item in enumerate(result)}
    for item in range(n):
        for pre in beforeItems[item]:
            if position[pre] > position[item]:
                return False
    return True


if __name__ == "__main__":
    sol = Solution()

    group1 = [-1, -1, 1, 0, 0, 1, 0, -1]
    before1 = [[], [6], [5], [6], [3, 6], [], [], []]
    res1 = sol.sortItems(8, 2, group1, before1)
    assert _respects_before_items(8, before1, res1), "case 1 should find a valid ordering"

    group2 = [-1, -1, 1]
    before2 = [[], [], [0]]
    res2 = sol.sortItems(3, 2, group2, before2)
    assert res2 != []
    assert res2.index(0) < res2.index(2)

    group3 = [0, 0, 1]
    before3 = [[], [0], [1]]
    res3 = sol.sortItems(3, 2, group3, before3)
    assert res3 == [0, 1, 2]

    group4 = [0, 0, 1]
    before4 = [[2], [], [0]]
    res4 = sol.sortItems(3, 2, group4, before4)
    assert res4 == []  # impossible: 0 needs 2, 2 needs 0

    print("All Sort Items by Groups Respecting Dependencies tests passed!")
