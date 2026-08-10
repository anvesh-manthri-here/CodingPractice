# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Witness of The Tall People
# From: daily@techseries.dev  |  Sent: 2019-09-22  |  Asked by: Google
#
# There are n people lined up, and each have a height represented as an integer. A murder has happened right in front of them, and only people who are taller than everyone in front of them are able to see what has happened. How many witnesses are there?
#
# Example:
# Input: [3, 6, 3, 4, 1]
# Output: 3
#
# Explanation: Only [6, 4, 1] were able to see in front of them.
#
# def witnesses(heights):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d59643b32b7228

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
