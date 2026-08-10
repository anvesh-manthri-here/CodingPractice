# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Invert a Binary Tree
# From: daily@techseries.dev  |  Sent: 2019-09-07  |  Asked by: Twitter
#
# You are given the root of a binary tree. Invert the binary tree in place. That is, all left children should become right children, and all right children should become left children.
#
# Example:
#     a
#    / \
#   b   c
#  / \  /
# d   e f
#
# The inverted version of this tree is as follows:
#   a
#  / \
#  c  b
#  \  / \
#   f e  d
#
# class Node:
#   def __init__(self, value):
#     self.left = None
#     self.right = None
#     self.value = value
#
# def invert(node):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d0c2609c194187

# Invert a Binary Tree
class Node:
  def __init__(self, value):
    self.left = None
    self.right = None
    self.value = value
  def preorder(self):
    print(self.value)
    if self.left: self.left.preorder()
    if self.right: self.right.preorder()

def invert(node):
	if node is None:
		return
	
	temp = node.left
	node.left = node.right
	node.right = temp
	
	invert(node.left)
	invert(node.right)

root = Node('a') 
root.left = Node('b') 
root.right = Node('c') 
root.left.left = Node('d') 
root.left.right = Node('e') 
root.right.left = Node('f') 

root.preorder()
# a b d e c f 
print("\n")
invert(root)
root.preorder()
# a c f b e d