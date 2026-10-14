# Two Sum problem.
arr = [1, 2, 4, 8, 6, 10]


def two_sum(arr, n, target):
  result = []
  for i in range(n):
    for j in range(i + 1, n):
      if arr[i] + arr[j] == target:
        result.append([i, j])
                
  return result

print(two_sum(arr, len(arr), 14))
