# Maximum Profit From Stocks
# You are given an array. Each element represents the price of a stock on that particular day. Calculate and return the maximum profit you can make from buying and selling that stock only once.
#For example: [9, 11, 8, 5, 7, 10]
#Here, the optimal trade is to buy when the price is 5, and sell when it is 10, so the return value should be 5 (profit = 10 - 5 = 5).

def buy_and_sell(arr):
    best = 0
    buy = arr[0]
    sell = arr[0]

    for cur in arr[1:]:
        if cur > sell:
            sell = cur
            if sell - buy > best:
                best = sell - buy
        elif cur < buy:
            buy = cur
            sell = cur
    return best

print buy_and_sell([9, 11, 8, 5, 7, 10])
# 5

print buy_and_sell([100, 180, 260, 310, 40, 535, 695])
