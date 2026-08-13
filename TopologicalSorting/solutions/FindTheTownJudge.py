# **Find the Town Judge** (Easy, indirect) — pattern: *indegree/outdegree reasoning*
#   https://leetcode.com/problems/find-the-town-judge/
#   Hint: Not a full topo sort, but great warm-up for indegree/outdegree bookkeeping which
#   underlies Kahn's algorithm.

class Solution:
    def findJudge(self, n: int, trust: List[List[int]]) -> int:
        judge = {i:0 for i in range(1, n+1)}
        for t in trust:
            judge[t[0]] = -1
            if judge[t[1]] is not -1:
                judge[t[1]] += 1
        ans = -1
        for j in judge:
            if judge[j] == n-1: 
                if ans is not -1:
                    break
                else:
                    ans = j
        return ans