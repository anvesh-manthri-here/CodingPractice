# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Validate Binary Search Tree
# From: daily@techseries.dev  |  Sent: 2019-10-09  |  Asked by: Facebook
#
# You are given the root of a binary search tree. Return true if it is a valid binary search tree, and false otherwise. Recall that a binary search tree has the property that all values in the left subtree are less than or equal to the root, and all values in the right subtree are greater than or equal to the root.
#
# class TreeNode:
#   def __init__(self, key):
#     self.left = None
#     self.right = None
#     self.key = key
#
# def is_bst(root):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16db111896c2f909

# Validate Binary Search Tree
# You are given the root of a binary search tree. Return true if it is a valid binary search tree, and false otherwise. Recall that a binary search tree has the property that all values in the left subtree are less than or equal to the root, and all values in the right subtree are greater than or equal to the root.

class TreeNode:
    def __init__(self, key):
        self.left = None
        self.right = None
        self.key = key

def is_bst(root):
    if root is None:
        return True
    return min_max(root)[0]

def min_max(root):
    if root.left is None and root.right is None:
        return True, root.key, root.key
    if root.left is None:
        right = min_max(root.right)
        if right[0] and right[1] >= root.key:
            return True, root.key, right[2]
        else:
            return False, None, None
    if root.right is None:
        left = min_max(root.left)
        if left[0] and left[2] < root.key:
            return True, left[1], root.key
        else:
            return False, None, None
    left = min_max(root.left)
    right = min_max(root.right)
    if left[0] and right[0] and left[2] < root.key and right[1] >= root.key:
        return True, left[1], right[2]
    else:
        return False, None, None

a = TreeNode(5)
a.left = TreeNode(3)
a.right = TreeNode(7)
a.left.left = TreeNode(1)
a.left.right = TreeNode(4)
a.right.left = TreeNode(6)
print is_bst(a)

#    5
#   / \
#  3   7
# / \ /
#1  4 6
