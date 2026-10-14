arr1 = [1, 1, 2, 3, 4, 5]
arr2 = [2, 3, 4, 4, 5, 6]

def union(arr1, arr2):
    n = len(arr1)
    m = len(arr2)
    
    i, j = 0, 0
    unionArr = []
    
    while i < n and j < m:
        if unionArr and unionArr[-1] == arr1[i]:
            i += 1
            continue
            
        if unionArr and unionArr[-1] == arr1[j]:
            j += 1
            continue
            
        if arr1[i] < arr2[j]:
            unionArr.append(arr1[i])
            i += 1
            
        elif arr2[j] < arr1[i]:
            unionArr.append(arr2[j])
            
        else:
            unionArr.append(arr1[i])
            i += 1
            j += 1
            
    while i < n:
        if not unionArr or unionArr[-1] != arr1[i]:
            unionArr.append(arr1[i])
            i += 1
            
    while j < m:
        if not unionArr or unionArr[-1] != arr2[j]:
            unionArr.append(arr2[j])
            j += 1
            
    return unionArr

print(union(arr1, arr2))