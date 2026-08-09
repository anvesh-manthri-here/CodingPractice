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