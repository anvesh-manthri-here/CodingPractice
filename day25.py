# Witness of The Tall People
# There are n people lined up, and each have a height represented as an integer. A murder has happened right in front of them, and only people who are taller than everyone in front of them are able to see what has happened. How many witnesses are there?

def witnesses(heights):
    least = -1
    count = 0

    for c in heights[::-1]:
        if c > least:
            count += 1
            least = c
    return count

print witnesses([3, 6, 3, 4, 1])
# 3
