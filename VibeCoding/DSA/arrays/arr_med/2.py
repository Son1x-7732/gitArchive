#Sort 0's 1's and 2's

arr = [2, 1, 0, 0, 2, 1, 1, 0, 2, 1, 0]

def sort(arr, n):
  low = 0
  mid = 0
  high = n - 1  
  
  while mid <= high:
    if arr[mid] == 0:
      arr[mid], arr[low] = arr[low], arr[mid]
      low += 1
      mid += 1
      
    elif arr[mid] == 1:
      mid += 1
      
    elif arr[mid] == 2:
      arr[mid], arr[high] = arr[high], arr[mid]
      high -= 1
      
  return arr
    
print(sort(arr, len(arr)))