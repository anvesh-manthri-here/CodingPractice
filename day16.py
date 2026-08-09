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
