#Rearrange elements by sign

arr = [3, 1, -2, -5, 2, -4]

def rearrange(arr, n):
  pos = 0
  neg = 1
  ans = [0] * n
  for i in range(n):
    if arr[i] < 0:
      ans[neg] = arr[i]
      neg += 2
    else:
      ans[pos] = arr[i]
      pos += 2
      
  return ans
  
print(rearrange(arr, len(arr)))