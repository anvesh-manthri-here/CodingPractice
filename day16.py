# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Longest Sequence with Two Unique Numbers
# From: daily@techseries.dev  |  Sent: 2019-09-13  |  Asked by: Facebook
#
# Given a sequence of numbers, find the longest sequence that contains only 2 unique numbers.
#
# Example:
# Input: [1, 3, 5, 3, 1, 3, 1, 5]
# Output: 4
#
# The longest sequence that contains just 2 unique numbers is [3, 1, 3, 1]
#
# def findSequence(seq):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d2b0ba0de5b258

# Longest Sequence with Two Unique Numbers

def findSequence(seq):
    if len(seq) < 2:
        return None
    a = seq[0]
    b = seq[1]
    longest = size = 2

    for ele in seq[2:]:
        if a is ele or b is ele:
            size += 1
            if size > longest:
                longest = size
        else:
            size = 2
        if b is not ele:
            a = b
            b = ele
    return longest


print findSequence([1, 3, 5, 3, 1, 3, 1, 5])
# 4
print findSequence([1, 3, 3, 1, 3, 1, 5])
# 6
