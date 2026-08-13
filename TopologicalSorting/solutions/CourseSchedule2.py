# **Course Schedule II** (Medium) — pattern: *produce an order*
#   https://leetcode.com/problems/course-schedule-ii/
#   Hint: Same as above, but return the collected `order` list; return `[]` if a cycle exists.

class Solution:
    def findOrder(self, numCourses: int, prerequisites: List[List[int]]) -> List[int]:
        courses = {i:[] for i in range(numCourses)}
        inbound = [0] * numCourses

        for u, v in prerequisites:
            if u == v:
                return False
            courses[v].append(u)
            inbound[u] += 1
        
        visiting = []
        for i in range(numCourses):
            if inbound[i] == 0:
                visiting.append(i)
        
        ordering = []
        while visiting:
            v = visiting.pop(0)
            for u in courses[v]:
                inbound[u] -= 1
                if inbound[u] == 0:
                    visiting.append(u)
            ordering.append(v)
            
        return ordering if len(ordering) == numCourses else [] 