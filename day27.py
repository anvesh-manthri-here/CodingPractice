# Move Zeros
# Given an array nums, write a function to move all 0's to the end of it while maintaining the relative order of the non-zero elements.

# You must do this in-place without making a copy of the array.
# Minimize the total number of operations.

class Solution:
    def moveZeros(self, nums):
        current = 0
        for i in range(len(nums)):
            if nums[i]:
                nums[current] = nums[i]
                nums[i] = 0
                current += 1



nums = [0, 0, 0, 2, 0, 1, 3, 4, 0, 0]
Solution().moveZeros(nums)
print(nums)
# [2, 1, 3, 4, 0, 0, 0, 0, 0, 0]
