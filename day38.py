# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Buddy Strings
# From: daily@techseries.dev  |  Sent: 2019-10-05  |  Asked by: AirBNB
#
# Given two strings A and B of lowercase letters, return true if and only if we can swap two letters in A so that the result equals B.
#
# Example 1:
# Input: A = "ab", B = "ba"
# Output: true
#
# Example 2:
# Input: A = "ab", B = "ab"
# Output: false
#
# Example 3:
# Input: A = "aa", B = "aa"
# Output: true
#
# Example 4:
# Input: A = "aaaaaaabc", B = "aaaaaaacb"
# Output: true
#
# Example 5:
# Input: A = "", B = "aa"
# Output: false
#
# class Solution:
#   def buddyStrings(self, A, B):
#     # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d9c553981b9585

# Buddy Strings
# Given two strings A and B of lowercase letters, return true if and only if we can swap two letters in A so that the result equals B.

class Solution:
    def buddyStrings(self, A, B):
        if len(A) is not len(B):
            return False
        A = 'a' + A
        B = 'b' + B
        sp1 = None
        sp2 = None

        for i in range(1, len(A)):
            if A[i] is not B[i]:
                if sp1 is None:
                    sp1 = i
                elif sp2 is None:
                    sp2 = i
                else:
                    return False

        if not sp1 and not sp2:
            return len(set(A[1:])) < len(A[1:])
        return A[sp1] is B[sp2]


print Solution().buddyStrings('ab', 'ba')
# True
print Solution().buddyStrings('ab', 'ab')
# False
print Solution().buddyStrings('aa', 'aa')
# True
print Solution().buddyStrings('', 'aa')
# False
print Solution().buddyStrings('aaaaaaabc', 'aaaaaaacb')
# True
print Solution().buddyStrings('aaaaaabbc', 'aaaaaaacb')
# False

