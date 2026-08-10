# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Longest Substring Without Repeating Characters
# From: daily@techseries.dev  |  Sent: 2019-08-28  |  Asked by: Microsoft
#
# Given a string, find the length of the longest substring without repeating characters.
#
# class Solution:
#   def lengthOfLongestSubstring(self, s):
#     # Fill this in.
#
# print Solution().lengthOfLongestSubstring('abrkaabcdefghijjxxx')
# # 10
#
# Can you find a solution in linear time?
#
# Original email: https://mail.google.com/mail/u/0/#all/16cd8b569e7adf49

# Longest Substring Without Repeating Characters

class Solution:
	def lengthOfLongestSubstring(self, s):
		li = {}
		ind = 0
		last = -1
		max_len = 0
		cur_len = 0
		for ch in s:
			try:
				last = li[ch]
			except:
				last = -1
			li[ch] = ind
			cur_len += 1
			
			if last != -1 and ind-cur_len+1 <= last:
				cur_len = ind - last
			
			if max_len < cur_len:
				max_len = cur_len
			print(s[ind-cur_len+1:ind+1])
			ind+=1
		return max_len

print(Solution().lengthOfLongestSubstring('abrkaabcdefghijjxxx'))
# 10
