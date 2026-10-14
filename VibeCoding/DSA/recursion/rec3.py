#sum of n numbers parameterised recursion

# def f(i, sum):
#     if i < 1:
#         print(sum)
#         return;
    
#     f(i - 1, sum + i)

# f(10, 0)

#sum of n numbers using functional recursion

# def f(n):
#     if n == 0:
#         return 0

#     return n + f(n - 1)

# value = f(10)
# print(value)

#factorial of n numbers

def fact(n):
    if n == 0 or n == 1:
        return 1

    return n * fact(n - 1)

value = fact(5)
print(value)