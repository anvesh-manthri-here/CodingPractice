# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Ways to Traverse a Grid
# From: daily@techseries.dev  |  Sent: 2019-09-17  |  Asked by: Microsoft
#
# You 2 integers n and m representing an n by m grid, determine the number of ways you can get from the top-left to the bottom-right of the matrix by going only right or down.
#
# Example:
# n = 2, m = 2
# This should return 2, since the only possible routes are:
# Right, down
# Down, right.
#
# def num_ways(n, m):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d3fa4ae25128c1

# Ways to Traverse a Grid
# You 2 integers n and m representing an n by m grid, determine the number of ways you can get from the top-left to the bottom-right of the matrix y going only right or down.

def num_ways(n, m):
    ans = [1 for i in range(m)]
    ans[0] = 0

    for i in range(1, n):
        prev = 1
        for j in range(1, m):
            ans[j-1] = prev
            prev = prev + ans[j]
        ans[m-1] = prev
    return ans[m-1]


print num_ways(5, 4)
# 2
