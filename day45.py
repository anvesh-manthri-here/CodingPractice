# Count Number of Unival Subtrees
#A unival tree is a tree where all the nodes have the same value. Given a binary tree, return the number of unival subtrees in the tree.

#For example, the following tree should return 5:
#     0
#    / \
#   1   0
#      / \
#    1   0
#   / \
#  1   1

#The 5 trees are:
#- The three single '1' leaf nodes. (+3)
#- The single '0' leaf node. (+1)
#- The [1, 1, 1] tree at the bottom. (+1)


class Node(object):
    def __init__(self, val):
        self.value = val
        self.left = None
        self.right = None


def count_unival_subtrees(root):
    if root is None:
        return True, 0
    left = count_unival_subtrees(root.left)
    right = count_unival_subtrees(root.right)
    if left[0] and right[0] and (not root.left or root.left.value is root.value) and (not root.right or root.right.value is root.value):
        return True, left[1] +right[1] + 1
    return False, left[1] + right[1]



a = Node(2)
a.left = Node(1)
a.right = Node(2)
a.right.left = Node(1)
a.right.right = Node(2)
a.right.left.left = Node(1)
a.right.left.right = Node(1)

print count_unival_subtrees(a)[1]
# 5
