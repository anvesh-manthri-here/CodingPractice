# Daily Interview Pro email (full content)
# Subject: [Daily Problem] Create a Simple Calculator
# From: daily@techseries.dev  |  Sent: 2019-09-12  |  Asked by: Google
#
# Given a mathematical expression with just single digits, plus signs, negative signs, and brackets, evaluate the expression. Assume the expression is properly formed.
#
# Example:
# Input: - ( 3 + ( 2 - 1 ) )
# Output: -4
#
# def eval(expression):
#   # Fill this in.
#
# Original email: https://mail.google.com/mail/u/0/#all/16d25e544d51d784

# Create a Simple Calculator

supported_expressions = ['+','-','*','/','%']
supported_numbers = ['0','1','2','3','4','5','6','7','8','9']

def basic_arth(op1, op2, sign):
    if sign is None and op2 is None:
        return op1

    if sign is '+':
        return op1 + op2
    elif sign is '-':
        return op1 - op2
    elif sign is '*':
        return op1 * op2
    elif sign is '/':
        return op1 / op2
    elif sign is '%':
        return op1 % op2
    else:
        return 0

def next_integers(expression):
    value = int(expression[0])
    size = 1
    try:
        while expression[size] in supported_numbers:
            value = value*10 + int(expression[size])
            size+=1
    except IndexError:
        pass
    return value, size

def convert_str_to_array(expression):
    expression_array = []
    i = 0
    while i < len(expression):
        if expression[i] in supported_numbers:
            next_int_value, next_int_size = next_integers(expression[i:])
            expression_array.append(next_int_value)
            i += next_int_size - 1
        else:
            expression_array.append(expression[i])
        i += 1
    return expression_array

def solve_linear(expression_array):
    priority_order = ['*','/','%','+','-']
    for p_sign in priority_order:
            i = 0
            while p_sign in expression_array and i < len(expression_array):
                if expression_array[i] is p_sign:
                    expression_array[i-1] = basic_arth(expression_array[i-1], expression_array[i+1], expression_array[i])
                    del(expression_array[i])
                    del(expression_array[i])
                    i -= 1
                i+=1
    return expression_array[0]

def eval(expression):
    expression_array = convert_str_to_array(expression)
    evaluation_stack = [[]]
    for element in expression_array:
        if element is '(':
            evaluation_stack.append([])
        elif element is ')':
            top_level_ans = solve_linear(evaluation_stack.pop())
            evaluation_stack[len(evaluation_stack)-1].append(top_level_ans)
        else:
            evaluation_stack[len(evaluation_stack)-1].append(element)
    return solve_linear(evaluation_stack[0])

print eval('2*3+2-1')
# 7
print eval('2*(3+(2-1))')
# 8
# print eval('-1 * (3 + ( 2 - 1 ) )')
# print eval('- (3 + ( 2 - 1 ) )')
# -4
