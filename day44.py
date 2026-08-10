# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Longest Substring With K Distinct Characters
# From: daily@techseries.dev  |  Sent: 2019-10-11  |  Asked by: Amazon
#
# You are given a string s, and an integer k. Return the length of the longest substring in s that contains at most k distinct characters.
#
# For instance, given the string:
# aabcdefff and k = 3, then the longest substring with 3 distinct characters would be defff. The answer should be 5.
#
# def longest_substring_with_k_distinct_characters(s, k):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16dbb5e0e5fbb41d

# Longest Substring With K Distinct Characters

#You are given a string s, and an integer k. Return the length of the longest substring in s that contains at most k distinct characters.

#For instance, given the string:
#aabcdefff and k = 3, then the longest substring with 3 distinct characters would be defff. The answer should be 5.

def longest_substring_with_k_distinct_characters(s, k):
    hash = {}
    max_len = 0
    cur_len = 0
    front = 0
    end = 0
    while(end < len(s)):
        if s[end] not in hash:
            while len(hash) is k:
                hash[s[front]] -= 1
                if hash[s[front]] is 0:
                    del hash[s[front]]
                cur_len -= 1
                front += 1
        if s[end] not in hash:
            hash[s[end]] = 0
        hash[s[end]] += 1
        cur_len += 1
        max_len = max(max_len, cur_len)
        end += 1
    return max_len

print longest_substring_with_k_distinct_characters('aabcdefff', 3)
# 5 (because 'defff' has length 5 with 3 characters)
