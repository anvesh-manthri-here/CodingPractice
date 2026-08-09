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
