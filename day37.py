# Trapping Rainwater
#You have a landscape, in which puddles can form. You are given an array of non-negative integers representing the elevation at each location. Return the amount of water that would accumulate if it rains.
#For example: [0,1,0,2,1,0,1,3,2,1,2,1] should return 6 because 6 units of water can get trapped here.

# time : O(n) & space : O(n)
def capacity(arr):
    h = arr[0]
    l_max = []
    for i in arr:
        h = max(h, i)
        l_max.append(h)

    h = arr[-1]
    r_max = []
    for i in reversed(arr):
        h = max(h, i)
        r_max.insert(0, h)

    water = 0
    for i in range(0, len(arr)):
        water += min(l_max[i], r_max[i]) - arr[i]
    return water

# time : O(n) & space : O(1)
def capacity_eff(arr):
    water = 0
    low = 0
    high = len(arr) - 1
    l_max = arr[low]
    r_max = arr[high]

    while low <= high:
        if arr[low] <= arr[high]:
            if arr[low] > l_max:
                l_max = arr[low]
            water += l_max - arr[low]
            low += 1
        else:
            if arr[high] > r_max:
                r_max = arr[high]
            water += r_max - arr[high]
            high -= 1
    return water

print capacity([0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1])
# 6
print capacity_eff([0, 1, 0, 2, 1, 0, 1, 3, 2, 1, 2, 1])
# 6
