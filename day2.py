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
