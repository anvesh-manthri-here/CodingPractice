# **Course Schedule** (Medium) — pattern: *feasibility / cycle detection*
#   https://leetcode.com/problems/course-schedule/
#   Hint: Build graph `prereq -> course`. Run Kahn's. Answer = `count(visited) == numCourses`.

# Input: 
# numCourses = 2
# prerequisites = [[1,0]]
# Output : true
# Expected : true


# Input:
# numCourses = 2
# prerequisites = [[1,0],[0,1]]
# Output : false
# Expected : false

# Input :
# numCourses = 20
# prerequisites = [[0,10],[3,18],[5,5],[6,11],[11,14],[13,1],[15,1],[17,4]]
# Output : false
# Expected : false


class Solution:
    def canFinish(self, numCourses: int, prerequisites: List[List[int]]) -> bool:
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
            
        return len(ordering) == numCourses
