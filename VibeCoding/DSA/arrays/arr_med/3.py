#Majority element
arr = [7, 1, 1, 7, 7, 7, 7, 3, 1]

def majority_brute(arr, n):
  for i in range(n):
    count = 0
    for j in range(n):
      if arr[j] == arr[i]:
        count += 1
    if count >= n / 2:
      return arr[i]
  return -1
  
print(majority_brute(arr, len(arr)))


def majority_better(arr, n):
  count = {}
  for x in arr:
    if x in count:
      count[x] += 1
    else:
      count[x] = 1
      
  for x in arr:
    if count[x] > n / 2:
      return x
      
print(majority_better(arr, len(arr)))

#Moore's Voting Algorithm
def majority_optimal(arr, n):
  count = 0
  element = None
  for i in range(n):
    if count == 0:
      element = arr[i]
      count = 1
      
    elif arr[i] == element:
      count += 1
      
    elif arr[i] != element:
      count -= 1
      
  if arr.count(element) > n / 2:
    return element
  else:
    return -1
      
print(majority_optimal(arr, len(arr)))
