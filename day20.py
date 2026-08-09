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
