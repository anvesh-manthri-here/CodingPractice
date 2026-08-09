# Minimum Size Subarray Sum
# Given an array of n positive integers and a positive integer s, find the minimal length of a contiguous subarray of which the sum >= s. If there isn't one, return 0 instead.

class Solution:
    def minSubArrayLen(self, nums, s):
        min_len = 9999999 # use sys.maxint if required.
        front = end = 0
        current_sum = nums[0]
        while True:
            if current_sum < s:
                if len(nums) == end + 1:
                    break
                end += 1
                current_sum += nums[end]
            else:
                while current_sum >= s and front <= end:
                    if min_len > end - front + 1:
                        min_len = end - front + 1
                    current_sum -= nums[front]
                    front += 1
        return min_len if min_len != 9999999 else 0

print Solution().minSubArrayLen([2, 3, 1, 2, 4, 3], 7)
# 2
print Solution().minSubArrayLen([1, 0, 0, 1, 7, 1], 7)
# 1
print Solution().minSubArrayLen([1, 0, 0, 1, 0, 1], 7)
# 0

