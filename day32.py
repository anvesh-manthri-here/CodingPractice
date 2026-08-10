# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Maximum Profit From Stocks
# From: daily@techseries.dev  |  Sent: 2019-09-29  |  Asked by: Apple
#
# You are given an array. Each element represents the price of a stock on that particular day. Calculate and return the maximum profit you can make from buying and selling that stock only once.
#
# For example: [9, 11, 8, 5, 7, 10]
#
# Here, the optimal trade is to buy when the price is 5, and sell when it is 10, so the return value should be 5 (profit = 10 - 5 = 5).
#
# def buy_and_sell(arr):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d7d704e7d0d14b

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
