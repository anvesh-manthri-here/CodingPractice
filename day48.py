# Word Ordering in a Different Alphabetical Order

#Given a list of words, and an arbitrary alphabetical order, verify that the words are in order of the alphabetical order.

#Example:
#Input:
#words = ["abcd", "efgh"], order="zyxwvutsrqponmlkjihgfedcba"
#Output: False
#Explanation: 'e' comes before 'a' so 'efgh' should come before 'abcd'

#Example 2:
#Input:
#words = ["zyx", "zyxw", "zyxwy"],
#order="zyxwvutsrqponmlkjihgfedcba"
#Output: True
#Explanation: The words are in increasing alphabetical order

def isSorted(words, order):
    order_dict = {}
    for i in range(0, len(order)):
        order_dict[order[i]] = i

    ind = 0
    while len(words):
        last = -1
        cur = 0
        while cur < len(words):
            if order_dict[words[cur][ind]] < last:
                return False
            last = order_dict[words[cur][ind]]
            if len(words[cur]) is ind+1:
                del(words[cur])
            else:
                cur += 1
        ind += 1
    return True

print isSorted(["abcd", "efgh"], "zyxwvutsrqponmlkjihgfedcba")
# False
print isSorted(["zyx", "zyxw", "zyxwy"],
               "zyxwvutsrqponmlkjihgfedcba")
# True
