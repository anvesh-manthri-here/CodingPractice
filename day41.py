# First Missing Positive Integer
#You are given an array of integers. Return the smallest positive integer that is not present in the array. The array may contain duplicate entries.

#For example, the input [3, 4, -1, 1] should return 2 because it is the smallest positive integer that doesn't exist in the array.

#Your solution should run in linear time and use constant space.

# using set
def first_missing_positive(nums):
    set_nums = set(nums)
    for i in range(1, len(nums)):
        if i not in set_nums:
            return i
    return None

print first_missing_positive([3, 4, -1, 1])
# 2

