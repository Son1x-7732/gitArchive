#DP on stocks

prices = [7, 1, 5, 3, 6, 4]

def maxProfit(arr, n):
  minimum = arr[0]
  profit = 0
  
  for i in range(1, n):
    curr_profit = arr[i] - minimum
    profit = max(profit, curr_profit)    
    minimum = min(minimum, arr[i])
    
  return profit
  
print(maxProfit(prices, len(prices)))