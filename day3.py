# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Validate Balanced Parentheses
# From: daily@techseries.dev  |  Sent: 2019-08-30  |  Asked by: Uber
#
# Imagine you are building a compiler. Before running any code, the compiler must check that the parentheses in the program are balanced. Every opening bracket must have a corresponding closing bracket. We can approximate this using strings.
#
# Given a string containing just the characters '(', ')', '{', '}', '[' and ']', determine if the input string is valid.
# An input string is valid if:
# - Open brackets are closed by the same type of brackets.
# - Open brackets are closed in the correct order.
# - Note that an empty string is also considered valid.
#
# Example:
# Input: "((()))"
# Output: True
#
# Input: "[()]{}"
# Output: True
#
# Input: "({[)]"
# Output: False
#
# class Solution:
#   def isValid(self, s):
#     # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16ce2f40a0503dd4

# Validate Balanced Parentheses

class Solution:
	def isValid(self, s):
		st = []
		for ch in s:
			try:
				if ch in ['(','{','[']:
					st.append(ch)
				elif ch is ')':
					if st.pop() is not '(':
						return False
				elif ch is '}':
					if st.pop() is not '{':
						return False
				elif ch is ']':
					if st.pop() is not '[':
						return False
			except:
				return False
		if len(st) == 0:
			return True
		return False


# Test Program
s = "()(){(())" 
# should return False
print(Solution().isValid(s))

s = ""
# should return True
print(Solution().isValid(s))

s = "([{}])()"
# should return True
print(Solution().isValid(s))
