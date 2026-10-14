#include<stdio.h>
#include<string.h>

int main(){
    char input[100]
    printf("Enter string")
    scanf("%s",input)
    int state = 0
    stack s ; // 0- init 2-dead 
    push(s,'z')
    for(int i =0 ; i< strlen(input);i++){
        if state == 2 break
        char c = input[i]
        char t = peek(s)

        if c == 'a' && state ==0 && (t=='a'||t=='z')
            push(s,'a')
        else if c=='c' && state == 0 && t=='a'
            state=1
        else if c=='b' && state == 1 && t=='a'
            pop(s)
        else state =2

    }

    char t = peek(s)
    if t =='z' && state =1 
        printf("Accepted")
    else
        printf("Rejected")
}