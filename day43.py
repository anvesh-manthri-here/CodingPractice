# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Get all Values at a Certain Height in a Binary Tree
# From: daily@techseries.dev  |  Sent: 2019-10-10  |  Asked by: Amazon
#
# Given a binary tree, return all values given a certain height h.
#
# class Node():
#   def __init__(self, value, left=None, right=None):
#     self.value = value
#     self.left = left
#     self.right = right
#
# def valuesAtHeight(root, height):
#   # Fill this in.
#
# #     1
# #    / \
# #   2   3
# #  / \   \
# # 4   5   7
# # valuesAtHeight(a, 3) -> [4, 5, 7]
#
# Original email: https://mail.google.com/mail/u/0/#all/16db63806b341291

# Get all Values at a Certain Height in a Binary Tree
# Given a binary tree, return all values given a certain height h.

class Node():
    def __init__(self, value, left=None, right=None):
        self.value = value
        self.left = left
        self.right = right

def valuesAtHeight(root, height, cur_height):
    if root is None:
        return []
    cur_height += 1
    if cur_height is height:
        return [root.value]
    return valuesAtHeight(root.left, height, cur_height) + valuesAtHeight(root.right, height, cur_height)


#     1
#    / \
#   2   3
#  / \   \
# 4   5   7

a = Node(1)
a.left = Node(2)
a.right = Node(3)
a.left.left = Node(4)
a.left.right = Node(5)
a.right.right = Node(7)
print valuesAtHeight(a, 3, 0)
# [4, 5, 7]
