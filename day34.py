# Contiguous Subarray with Maximum Sum
#You are given an array of integers. Find the maximum sum of all possible contiguous subarrays of the array.

#Example:
#[34, -50, 42, 14, -5, 86]
#Given this input array, the output should be 137. The contiguous subarray with the largest sum is [42, 14, -5, 86].

#Your solution should run in linear time.


def max_subarray_sum(arr):
    max_sum = 0
    sum = 0
    for i in arr:
        if sum + i > 0:
            sum += i
            if sum > max_sum:
                max_sum = sum
        else:
            sum = 0
    return max_sum

print max_subarray_sum([34, -50, 42, 14, -5, 86])
# 137
