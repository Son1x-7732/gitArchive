arr1 = [1, 1, 2, 3, 4, 6]
arr2 = [2, 3, 4, 4, 5, 6]

def intersection(arr1, arr2):
    result = []
    for x in arr1:
        for y in arr2:
            if x == y and x not in result:
                result.append(x)
    return result
    
print(intersection(arr1, arr2))
    
    