# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Add two numbers as a linked list
# From: daily@techseries.dev  |  Sent: 2019-08-27  |  Asked by: Microsoft
#
# You are given two linked-lists representing two non-negative integers. The digits are stored in reverse order and each of their nodes contain a single digit. Add the two numbers and return it as a linked list.
#
# Example:
# Input: (2 -> 4 -> 3) + (5 -> 6 -> 4)
# Output: 7 -> 0 -> 8
# Explanation: 342 + 465 = 807.
#
# Starting point:
# # Definition for singly-linked list.
# class ListNode(object):
#   def __init__(self, x):
#     self.val = x
#     self.next = None
#
# class Solution:
#   def addTwoNumbers(self, l1, l2, c = 0):
#     # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16cd38ef7e107a25

#Sum of two numbers given in reverse linked list.


# Definition for singly-linked list.
class ListNode(object):
  def __init__(self, x):
    self.val = x
    self.next = None

class Solution:
  def addTwoNumbers(self, l1, l2, c = 0):
    # Fill this in.
    head = None
    tail = None
    value = 0;
    while l1!=None or l2!=None:
        if l1!=None:
            value += l1.val
            l1 = l1.next
        if l2!=None:
            value += l2.val
            l2 = l2.next
        temp = ListNode(value%10)
        value = int(value/10)
        if head:
            tail.next = temp
            tail = tail.next
        else:
            head = temp
            tail = temp
        
    if value:
        tail.next = ListNode(value)

    return head

l1 = ListNode(2)
l1.next = ListNode(4)
l1.next.next = ListNode(3)
l1.next.next.next = ListNode(5)

l2 = ListNode(5)
l2.next = ListNode(6)
l2.next.next = ListNode(4)

#l1 = ListNode(9)
#l1.next = ListNode(9)
#l1.next.next = ListNode(9)
#l1.next.next.next = ListNode(9)

#l2 = ListNode(9)
#l2.next = ListNode(9)
#l2.next.next = ListNode(9)

result = Solution().addTwoNumbers(l1, l2)
while result:
  print(result.val)
  result = result.next
# 7 0 8