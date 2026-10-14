def mn_brute(arr, n):
    
    for i in range(0, n):
        if arr[i] != i + 1:
            return i + 1
    return len(arr) + 1


arr = [1, 2, 4, 5]
print(mn_brute(arr, len(arr)))


def missing_number_hash(arr, n):
    freq = {}
    
    for num in arr:
        freq[num] = 1
        
    for i in range (1, n + 2):
        if i not in freq:
            return i
            
print(missing_number_hash(arr, len(arr)))
    
def missing_number_optimal(arr, n):
    expected = (n + 1) * (n + 2) // 2
    actual = sum(arr)
    return expected - actual
    
print(missing_number_optimal(arr, len(arr)))
    