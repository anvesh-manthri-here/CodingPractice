# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Intersection of Linked Lists
# From: daily@techseries.dev  |  Sent: 2019-09-18  |  Asked by: Apple
#
# You are given two singly linked lists. The lists intersect at some node. Find, and return the node. Note: the lists are non-cyclical.
#
# Example:
# A = 1 -> 2 -> 3 -> 4
# B = 6 -> 3 -> 4
#
# This should return 3 (you may assume that any nodes with the same value are the same node).
#
# def intersection(a, b):
#   # fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d44cb4eb42959e

# Intersection of Linked Lists
# You are given two singly linked lists. The lists intersect at some node. Find, and return the node. Note: the lists are non-cyclical.

def intersection(a, b):
    len_a = 0
    temp = a
    while temp is not None:
        len_a += 1
        temp = temp.next

    len_b = 0
    temp = b
    while temp is not None:
        len_b += 1
        temp = temp.next

    if len_a > len_b:
        for i in range(len_a - len_b):
            a = a.next
    elif len_b > len_a:
        for i in range(len_b - len_a):
            b = b.next

    while a is not None and b is not None and a.val is not b.val:
        a = a.next
        b = b.next

    start = None
    end = None
    while a is not None:
        if start is None:
            start = end = Node(a.val)
        end.next = Node(a.val)
        a = a.next
    return start

class Node(object):
    def __init__(self, val):
        self.val = val
        self.next = None
    def prettyPrint(self):
        c = self
        while c:
            print c.val,
            c = c.next

a = Node(1)
a.next = Node(2)
a.next.next = Node(3)
a.next.next.next = Node(4)

b = Node(6)
b.next = a.next.next

c = intersection(a, b)
c.prettyPrint()
# 3 4
