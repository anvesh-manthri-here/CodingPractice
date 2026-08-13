# **Alien Dictionary** (Hard, LeetCode Premium / on many other judges too) —
#   pattern: *build graph from string comparisons, then topo sort*
#   https://leetcode.com/problems/alien-dictionary/
#   Hint: Compare each pair of adjacent words; the first differing character gives an edge
#   `word1[i] -> word2[i]`. If `word1` is longer than `word2` AND is a prefix of it → invalid
#   input (return `""`). Topo sort the 26 letters that actually appear.


from collections import deque, defaultdict

class Solution:
    def foreignDictionary(self, words: List[str]) -> str:

        if len(words) == 1:
            return words[0]

        graph = defaultdict(list)
        inbound = defaultdict(int)

        chars = set()
        for w in range(1, len(words)):
            word1 = words[w-1]
            word2 = words[w]

            for k in word1: chars.add(k)
            for k in word2: chars.add(k)

            all_same = True
            same_ind = -1
            for i in range(min(len(word1), len(word2))):
                # chars.add(word1[i])
                if word1[i] is not word2[i]:
                    all_same = False
                    same_ind = i
                    if word2[i] not in graph[word1[i]]:
                        graph[word1[i]].append(word2[i])
                        inbound[word2[i]] += 1
                        # chars.add(word2[i])
                    break
            if all_same and len(word1) > len(word2):
                print(word1, word2)
                return ""

        for ch in chars:
            if ch not in graph:
                graph[ch] = []
            if ch not in inbound:
                inbound[ch] = 0

        print(graph, inbound, chars)
        order = deque([ch for ch in inbound if inbound[ch]==0])
        result = []
        while order:
            ch = order.popleft()
            for v in graph[ch]:
                inbound[v] -= 1
                if inbound[v] == 0:
                    order.append(v)
            result.append(ch)
        
        if len(result) == len(chars):
            return "".join(result)
        return ""

   








        