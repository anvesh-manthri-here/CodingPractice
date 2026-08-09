# Create a balanced binary search tree
# Given a sorted list of numbers, change it into a balanced binary search tree. You can assume there will be no duplicate numbers in the list.

from collections import deque

class Node:
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right
        
    def __str__(self):
        # level-by-level pretty-printer
        nodes = deque([self])
        answer = ''
        while len(nodes):
            node = nodes.popleft()
            if not node:
                continue
            answer += str(node.value)
            nodes.append(node.left)
            nodes.append(node.right)
        return answer

def createBalancedBST(nums):
    n = len(nums)
    if n == 0:
        return None
    elif n == 1:
        return Node(nums[0])
    else:
        mid = n / 2
        cur = Node(nums[mid])
        cur.left = createBalancedBST(nums[:mid])
        cur.right = createBalancedBST(nums[mid+1:])
        return cur

print createBalancedBST([1, 2, 3, 4, 5, 6, 7])
# 4261357
#   4
#  / \
# 2   6
#/ \ / \
#1 3 5 7
print createBalancedBST([1, 2, 3, 4, 5, 6])
# 426135
#   4
#  / \
# 2   6
#/ \ /
#1 3 5
print createBalancedBST([1, 2, 3, 4, 5])
# 32514
#   3
#  / \
# 2   5
#/   /
#1   4
print createBalancedBST([1, 2, 3, 4])
# 3241
#   3
#  / \
# 2   4
#/
#1
print createBalancedBST([1, 2, 3])
# 213
#   2
#  / \
# 1   3
