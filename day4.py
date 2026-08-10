# Daily Interview Pro email (full content)
# Subject: [Daily Problem] First and Last Indices of an Element in a Sorted Array
# From: daily@techseries.dev  |  Sent: 2019-08-31  |  Asked by: AirBNB
#
# Given a sorted array, A, with possibly duplicated elements, find the indices of the first and last occurrences of a target element, x. Return -1 if the target is not found.
#
# Example:
# Input: A = [1,3,3,5,7,8,9,9,9,15], target = 9
# Output: [6,8]
#
# Input: A = [100, 150, 150, 153], target = 150
# Output: [1,2]
#
# Input: A = [1,2,3,4,5,6,10], target = 9
# Output: [-1, -1]
#
# class Solution:
#   def getRange(self, arr, target):
#     # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16ce7e21b7d49972

# First and Last Indices of an Element in a Sorted Array



class Solution: 
	def getRange(self, arr, target):
		return [self.first(arr, target), self.last(arr, target)]
	
	def first(self, arr, target):
		l = len(arr)
		f = 0
		e = l
		
		while not e<f:
			h=int((f+e)/2)
			if (h==0 or arr[h-1]<target) and arr[h]==target:
				return h
			elif arr[h] < target:
				f = h + 1
			else:
				e = h - 1
		return -1

	def last(self, arr, target):
		l = len(arr)
		f = 0
		e = l
		
		while not e<f:
			h=int((f+e)/2)
			if (h==l-1 or arr[h+1]>target) and arr[h]==target:
				return h
			elif arr[h] > target:
				e = h - 1
			else:
				f = h + 1
		return -1











# Test program 
arr = [1, 2, 2, 2, 2, 3, 4, 7, 8, 8] 
x = 2
print(Solution().getRange(arr, x))
# [1, 4]






# another solution:
# def getRange(self, arr, target):
	# l = len(arr)
	# f = 0
	# e = l - 1
	
	# while not e<f:
		# h = int((f+e)/2)
		# if arr[h] == target:
			# a = h
			# b = h
			# while a>=0 and arr[a] == target:
				# a-=1
			# while b<l and arr[b] == target:
				# b+=1
			# return [a+1, b-1]
		# elif arr[h] > target:
			# e = h - 1
		# elif arr[h] < target:
			# f = h + 1
	# return -1
