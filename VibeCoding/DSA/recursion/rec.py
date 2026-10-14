# def rec(n, i = 1):
#     if i > n:
#         return;
    
#     print("Shiba")
#     rec(n, i+1)

# # i = 0
# n = int(input("Enter a no: "))
# rec(n)


# def rec(i, n):
#     if i > n:
#         return;
    
#     print(i)
#     rec(i+1, n)

# # i = 0
# n = int(input("Enter a no: "))
# rec(1, n)

# def rec(i, n):
#     if i < 1:
#         return
    
#     print(i)
#     rec(i - 1, n)

# n = int(input("Enter a no: "))
# rec(n, n)

# def rec(i, n):
#     if ( i < 1):
#         return
    
#     rec(i - 1, n)
#     print(i)

# n = int(input("Enter a no: "))
# rec(n, n)

def rec(i, n):
    if i > n:
        return

    rec(i + 1, n)
    print(i)

n = int(input("Enter a no: "))
rec(1, n)
