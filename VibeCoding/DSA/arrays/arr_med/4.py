#Maximum sum of subarray
arr = [-2, -3, 4, -1, -2, 1, 5, -3]

def brute(arr, n):
  answer = float('-inf')
  for i in range(n):
    current_sum = 0    
    for j in range(i, n):
      current_sum += arr[j]
      answer = max(answer, current_sum)
  
  return answer
  

def kadene(arr, n):
  current_sum = 0
  maximum = float('-inf')
  start = 0
  end = 0
  temp_start = 0
  
  for i in range(n):
    current_sum += arr[i]
    
    if current_sum > maximum:
      maximum = current_sum
      start = temp_start
      end = i
    
    if current_sum < 0:
      current_sum = 0
      temp_start += 1
  
  if maximum > 0:
    return [maximum, start, end]
  else:
    return -1
  
print(brute(arr, len(arr)))
print(kadene(arr, len(arr)))